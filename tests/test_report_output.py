"""The rcsb_render_report output contract.

The tool returns EITHER a ``url`` or ``html``, never both:

* ``url`` — the preferred path. A self-contained link that renders the report on
  demand from the data packed into it (see report/link.py); the server stores
  nothing. The agent relays the link and never reproduces the document.
* ``html`` — the fallback, returned only when no render endpoint is configured
  (``RCSB_MCP_REPORT_BASE_URL`` unset) or the report is too big to pack into a URL.

The codec and the /r endpoint are covered in test_report_link.py.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp.server.fastmcp import FastMCP

from rcsb_mcp.report import build_collection_url, tools as report_tools

MINIMAL = {
    "report": {
        "title": "Iron-type nitrile hydratases",
        "columns": [{"key": "pdb_id", "label": "PDB ID", "kind": "pdb_id"}],
        "rows": [{"pdb_id": "4HHB"}, {"pdb_id": "1IRE"}],
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


def test_returns_a_link_when_a_base_url_is_configured(with_base_url):
    res = _structured(**MINIMAL)
    assert res["url"] is not None and res["url"].startswith(f"{with_base_url}/r?d=")
    assert res["html"] is None, "must not also ship the markup when a link is returned"
    assert res["row_count"] == 2


def test_falls_back_to_html_when_no_base_url(no_base_url):
    res = _structured(**MINIMAL)
    assert res["url"] is None
    assert res["html"].startswith("<!DOCTYPE html>")
    assert res["row_count"] == 2


def test_result_surface_is_only_url_html_and_metadata(no_base_url):
    res = _structured(**MINIMAL)
    assert set(res) == {"url", "html", "row_count", "template_version"}
    schema = report_tools.RenderReportInput.model_json_schema()
    assert set(schema["properties"]) == {"report"}, "input must expose only `report`"


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
# Collection URL shape
# --------------------------------------------------------------------------


def test_collection_query_stays_flat():
    """One group wrapping one terminal.

    The RCSB.org query builder needs the group to render the condition but not
    the two further nested groups this used to emit; verified against the live
    site.
    """
    import urllib.parse

    url = build_collection_url(["101M", "1ASH"])
    query = json.loads(urllib.parse.unquote(url.split("request=", 1)[1]))["query"]
    assert query["type"] == "group"
    assert [n["type"] for n in query["nodes"]] == ["terminal"]
