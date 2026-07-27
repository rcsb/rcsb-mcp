"""The rcsb_render_report output contract.

The tool returns EITHER a ``url`` or ``html``, never both:

* ``url`` — the preferred path. A short ``/r/<id>`` link; opening it redirects to a
  self-contained URL that renders the report on demand (see report/link.py). The id
  maps to the packed token in a short-TTL store; if the store is down the tool emits
  the fat ``/r?d=`` URL instead. The agent relays the link and never reproduces it.
* ``html`` — the fallback, returned only when no render endpoint is configured
  (``RCSB_MCP_REPORT_BASE_URL`` unset) or the report is too big to pack into a URL.

The codec, the store, and the /r endpoints are covered in test_report_link.py and
test_report_store.py.
"""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from rcsb_mcp.report import tools as report_tools

MINIMAL = {
    "report": {
        "title": "Iron-type nitrile hydratases",
        "result_type": "entry",
        "results": [{"id": "4HHB"}, {"id": "1IRE"}],
    }
}


@pytest.fixture
def no_base_url(monkeypatch):
    """Force the html-fallback path regardless of the environment."""
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", None)


@pytest.fixture
def with_base_url(monkeypatch):
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://reports.example.org")
    return "https://reports.example.org"


@pytest.fixture
def shared_store(monkeypatch):
    """A shared store, so the tool takes the short-link path (not the fat-URL fallback)."""
    from rcsb_mcp.report.store import InMemoryReportStore

    store = InMemoryReportStore()
    store.shared = True
    monkeypatch.setattr(report_tools, "REPORT_STORE", store)
    return store


def _invoke(**params):
    """Call the registered tool, returning (content_blocks, structured_result)."""
    mcp = FastMCP("test")
    report_tools.register_report_tools(mcp)
    return asyncio.run(mcp.call_tool("rcsb_render_report", {"params": params}))


def _structured(**params) -> dict:
    return _invoke(**params)[1]


# --------------------------------------------------------------------------
# Either a url or html, never both
# --------------------------------------------------------------------------


def test_returns_a_short_link_with_a_shared_store(with_base_url, shared_store):
    res = _structured(**MINIMAL)
    assert res["url"] is not None and res["url"].startswith(f"{with_base_url}/r/")
    assert "?d=" not in res["url"], "the agent gets the short link, not the fat packed URL"
    assert res["html"] is None, "must not also ship the markup when a link is returned"


def test_short_link_id_resolves_to_the_report_token_in_the_store(with_base_url, shared_store):
    """The short link's id must map, in the store, to the exact token that renders."""
    from rcsb_mcp.report import link

    res = _structured(**MINIMAL)
    url_id = res["url"].rsplit("/", 1)[-1]
    token = shared_store.get(url_id)
    assert token is not None, "the tool must have stored the token under the id"
    # The stored token is the self-contained payload the /r?d= endpoint renders.
    assert "Iron-type nitrile hydratases" in link.decode_report(token)


def test_emits_the_fat_url_when_the_store_is_not_shared(with_base_url, monkeypatch):
    """The dead-link fix: a process-local store must NOT mint a short link that would
    410 on another replica — the tool emits the self-contained /r?d= URL instead."""
    from rcsb_mcp.report.store import InMemoryReportStore

    monkeypatch.setattr(report_tools, "REPORT_STORE", InMemoryReportStore())  # shared=False
    res = _structured(**MINIMAL)
    assert res["url"] is not None and res["url"].startswith(f"{with_base_url}/r?d=")
    assert res["html"] is None


def test_falls_back_to_fat_url_when_a_shared_store_write_fails(with_base_url, monkeypatch):
    """A shared-store write failure (e.g. Redis down) must degrade to /r?d=, not html."""

    class _DeadSharedStore:
        shared = True

        def put(self, token):  # noqa: ARG002 — simulates an unreachable shared store
            return None

    monkeypatch.setattr(report_tools, "REPORT_STORE", _DeadSharedStore())
    res = _structured(**MINIMAL)
    assert res["url"] is not None and res["url"].startswith(f"{with_base_url}/r?d=")
    assert res["html"] is None


def test_falls_back_to_html_when_no_base_url(no_base_url):
    res = _structured(**MINIMAL)
    assert res["url"] is None
    assert res["html"].startswith("<!DOCTYPE html>")


def test_result_surface_is_only_url_html_and_metadata(no_base_url):
    res = _structured(**MINIMAL)
    assert set(res) == {"url", "html", "template_version"}
    schema = report_tools.RenderReportInput.model_json_schema()
    assert set(schema["properties"]) == {"report"}, "input must expose only `report`"


def test_result_type_is_required(no_base_url):
    """No default: a report whose type is omitted (or disagrees with its ids) would
    resolve nothing and render every derived value empty — so the agent MUST state it."""
    req = report_tools.RenderReportInput.model_json_schema()["$defs"]["ReportRequest"]
    assert "result_type" in req["required"], "result_type must be required, not defaulted"
    with pytest.raises(ValidationError, match="result_type"):
        report_tools.RenderReportInput.model_validate(
            {"report": {"title": "t", "results": [{"id": "4HHB"}]}}
        )


def test_writes_nothing_to_disk(tmp_path, monkeypatch, with_base_url):
    monkeypatch.chdir(tmp_path)
    _structured(**MINIMAL)
    assert list(tmp_path.iterdir()) == []


def test_oversized_report_falls_back_to_html_even_with_a_base_url(with_base_url, monkeypatch):
    """A report too big to pack into a URL must not silently drop to a broken link."""
    monkeypatch.setattr(report_tools, "MAX_URL_BYTES", 200)  # force the ceiling
    res = _structured(**MINIMAL)
    assert res["url"] is None
    assert res["html"].startswith("<!DOCTYPE html>")


def test_multibyte_report_over_the_byte_cap_falls_back_to_html(with_base_url):
    """Fix [3]: the emit gate measures UTF-8 BYTES, not characters. A multibyte report
    whose char count is UNDER MAX_DECOMPRESSED but whose byte count is OVER it must fall
    back to html — the /r endpoint bounds decompressed BYTES and would reject the link.
    (A char-length gate would wrongly emit it, so this fails if fix [3] is reverted.)"""
    from rcsb_mcp.report import link
    from rcsb_mcp.report.enrich import build_document
    from rcsb_mcp.report.models import ReportRequest

    big = {
        "title": "probe",
        "result_type": "entry",
        # 70k chars / 210k UTF-8 bytes of evidence — the agent-supplied part of a row.
        "results": [{"id": "AAAA", "evidence": {"grounds": "あ" * 70_000}}],
    }
    document = asyncio.run(build_document(ReportRequest(**big), None))
    report_json = document.model_dump_json(exclude_defaults=True)
    assert len(report_json) < link.MAX_DECOMPRESSED, "char length is under the cap (a char gate would emit)"
    assert len(report_json.encode("utf-8")) > link.MAX_DECOMPRESSED, "but byte length is over it"
    assert len(link.encode_report(report_json)) < 2000, "compresses tiny, so the fat_url gate is NOT the rejecter"

    res = _structured(report=big)
    assert res["url"] is None, "must not emit a link the endpoint would reject on decompressed bytes"
    assert res["html"].startswith("<!DOCTYPE html>")


# --------------------------------------------------------------------------
# The fallback markup, when returned, is duplicated across both FastMCP copies
# --------------------------------------------------------------------------


def test_fallback_html_is_emitted_in_both_content_and_structured(no_base_url):
    """When html IS returned, a context-keeping client must strip both copies."""
    content, structured = _invoke(**MINIMAL)
    in_content = any("<!DOCTYPE html>" in (getattr(c, "text", "") or "") for c in content)
    assert in_content, "html should appear in a content[] text block"
    assert structured["html"].startswith("<!DOCTYPE html>"), "and in structuredContent"
