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


def test_url_gate_never_exceeds_what_the_endpoint_accepts():
    """The emit gate must stay inside the /r endpoint's own accept criteria.

    These two numbers live in different modules and drifted apart once already: the gate
    sat at 8_000 (nginx's default request-line buffer, on a deployment fronted by HAProxy)
    while the endpoint accepted 16_384, so real reports that /r would have served came back
    as ~40 KB of `html` — the agent-context cost the report link exists to remove.

    Only ONE direction is a correctness bug: a gate ABOVE MAX_ENCODED emits links that /r
    refuses with a 400. A gate below merely wastes capacity, which is what this pins.
    """
    from rcsb_mcp.report import link

    assert report_tools.MAX_URL_BYTES <= link.MAX_ENCODED, (
        f"MAX_URL_BYTES ({report_tools.MAX_URL_BYTES}) exceeds the token size /r will accept "
        f"(MAX_ENCODED={link.MAX_ENCODED}); the tool would hand back links the endpoint 400s."
    )
    # And it should not be so far below that it throws away most of that capacity.
    assert report_tools.MAX_URL_BYTES >= link.MAX_ENCODED * 0.9, (
        f"MAX_URL_BYTES ({report_tools.MAX_URL_BYTES}) is far under MAX_ENCODED "
        f"({link.MAX_ENCODED}); reports the endpoint would serve fall back to html instead."
    )


# --------------------------------------------------------------------------
# The fallback markup, when returned, is duplicated across both FastMCP copies
# --------------------------------------------------------------------------


def test_fallback_html_is_emitted_in_both_content_and_structured(no_base_url):
    """When html IS returned, a context-keeping client must strip both copies."""
    content, structured = _invoke(**MINIMAL)
    in_content = any("<!DOCTYPE html>" in (getattr(c, "text", "") or "") for c in content)
    assert in_content, "html should appear in a content[] text block"
    assert structured["html"].startswith("<!DOCTYPE html>"), "and in structuredContent"


# --------------------------------------------------------------------------
# The short link is minted off the PINNED base, the fat fallback off the public one
# --------------------------------------------------------------------------
#
# mcp-beta.rcsb.org is GSLB'd across two clusters, each with its own Redis. Measured on the
# live beta: an agent resolved it to east and the token was written there (EXISTS=1), while
# the browser resolved the SAME name to west and got the expired page (EXISTS=0). The short
# id resolves only where it was minted, so it must be fetched from that cluster; the
# /r?d=<token> URL it redirects to is self-contained and renders from any of them.
#
# Hence two bases. Collapsing them back into one reintroduces the bug, which is why the
# minted host is asserted here and not just the redirect target.


@pytest.fixture
def pinned_link_base(monkeypatch):
    monkeypatch.setattr(report_tools, "REPORT_LINK_BASE_URL", "https://west.example.org")
    return "https://west.example.org"


def test_the_short_link_is_minted_off_the_PINNED_base(
    with_base_url, shared_store, pinned_link_base
):
    """The agent must receive the cluster-pinned host, NOT the public one.

    This is the assertion a "simplification" back to a single base has to fail: with both
    configured and different, the short link carries the pinned host.
    """
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"{pinned_link_base}/r/"), res["url"]
    assert not res["url"].startswith(with_base_url), (
        "the short link went to the public GSLB host — that is the split-brain bug"
    )
    assert "?d=" not in res["url"]


def test_the_fat_fallback_still_uses_the_PUBLIC_base(with_base_url, pinned_link_base):
    """No shared store ⇒ the self-contained URL, which needs no lookup and renders from any
    cluster — so it belongs on the public hostname, not the pinned one."""
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"{with_base_url}/r?d="), res["url"]
    assert "west.example.org" not in res["url"], (
        "the self-contained URL is cluster-independent; pinning it would hand users an "
        "internal hostname for no benefit"
    )


def test_with_nothing_pinned_the_short_link_uses_the_public_base(with_base_url, shared_store):
    """Single-cluster and stdio deployments need no new configuration."""
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"{with_base_url}/r/"), res["url"]


# --------------------------------------------------------------------------
# {coast} substitution: one chart value, correct in every cluster
# --------------------------------------------------------------------------
#
# Both clusters carry a `cluster-metadata` ConfigMap ({"COAST": "west"} / {"COAST": "east"}),
# which the chart injects as COAST. So RCSB_MCP_REPORT_LINK_BASE_URL ships ONE value --
# "https://mcp-beta.{coast}.k8s.rcsb.org" -- and the pod resolves it at startup, the same
# shape as {version} in RCSB_MCP_USER_AGENT. No --set at upgrade time, nothing to forget.


@pytest.fixture
def templated_link_base(monkeypatch):
    monkeypatch.setattr(
        report_tools, "REPORT_LINK_BASE_URL", "https://mcp-beta.{coast}.k8s.rcsb.org"
    )


@pytest.mark.parametrize("coast", ["west", "east"])
def test_coast_is_substituted_into_the_short_link(
    with_base_url, shared_store, templated_link_base, monkeypatch, coast
):
    monkeypatch.setattr(report_tools, "COAST", coast)
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"https://mcp-beta.{coast}.k8s.rcsb.org/r/"), res["url"]
    assert "{coast}" not in res["url"]


def test_an_unsubstituted_placeholder_never_reaches_the_user(
    with_base_url, shared_store, templated_link_base, monkeypatch
):
    """COAST missing (a namespace without the ConfigMap — it is mounted `optional`).

    Falling back to the public base loses the cluster pinning, so short links resolve only
    about half the time behind the GSLB name. Emitting "https://mcp-beta.{coast}.k8s…"
    resolves NEVER, so the degraded answer is the right one.
    """
    monkeypatch.setattr(report_tools, "COAST", "")
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"{with_base_url}/r/"), res["url"]
    assert "{coast}" not in res["url"]


@pytest.mark.parametrize("bad", ["we st", "west/../evil", "WEST", "-west", "x" * 40, "a.b"])
def test_a_malformed_coast_is_refused_rather_than_interpolated(
    with_base_url, shared_store, templated_link_base, monkeypatch, bad
):
    """COAST becomes a HOSTNAME component in a URL handed to a user, so anything outside
    [a-z0-9-] is treated as unset. A stray value must not build a link to somewhere else."""
    monkeypatch.setattr(report_tools, "COAST", bad)
    res = _structured(**MINIMAL)
    assert res["url"].startswith(f"{with_base_url}/r/"), res["url"]
    assert bad not in res["url"]


def test_a_literal_pinned_host_is_still_used_verbatim(
    with_base_url, shared_store, monkeypatch
):
    """No placeholder ⇒ no substitution, so a hand-set absolute host keeps working and
    COAST is irrelevant."""
    monkeypatch.setattr(report_tools, "REPORT_LINK_BASE_URL", "https://pinned.example.org")
    monkeypatch.setattr(report_tools, "COAST", "")
    res = _structured(**MINIMAL)
    assert res["url"].startswith("https://pinned.example.org/r/"), res["url"]
