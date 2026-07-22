"""The rcsb_render_report output contract.

The server is stateless: it renders and returns ``html``, storing nothing. The
client owns the download. A client that keeps the result in the model's context
must strip ``html`` from BOTH copies FastMCP emits (``content[]`` and
``structuredContent``), or the ~6.5k-token document is paid for twice this turn
and again on every later turn it stays in history.
"""

from __future__ import annotations

import asyncio
import hashlib
import json

from mcp.server.fastmcp import FastMCP

from rcsb_mcp.report import build_collection_url, tools as report_tools

MINIMAL = {
    "report": {
        "title": "Iron-type nitrile hydratases",
        "columns": [{"key": "pdb_id", "label": "PDB ID", "kind": "pdb_id"}],
        "rows": [{"pdb_id": "4HHB"}, {"pdb_id": "1IRE"}],
    }
}


def _invoke(**params):
    """Call the registered tool, returning (content_blocks, structured_result)."""
    mcp = FastMCP("test")
    report_tools.register_report_tools(mcp)
    return asyncio.run(mcp.call_tool("rcsb_render_report", {"params": params}))


def _structured(**params) -> dict:
    return _invoke(**params)[1]


# --------------------------------------------------------------------------
# Stateless: always returns the markup, writes nothing
# --------------------------------------------------------------------------


def test_always_returns_the_rendered_html():
    res = _structured(**MINIMAL)
    assert res["html"].startswith("<!DOCTYPE html>")
    assert res["row_count"] == 2


def test_metadata_describes_the_returned_document():
    res = _structured(**MINIMAL)
    encoded = res["html"].encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == res["sha256"]
    assert res["bytes"] == len(encoded)


def test_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _structured(**MINIMAL)
    assert list(tmp_path.iterdir()) == []


def test_result_carries_no_file_handles():
    """The stateless contract exposes no path/url/filename surface at all."""
    res = _structured(**MINIMAL)
    assert set(res) == {"html", "sha256", "row_count", "template_version", "bytes"}

    schema = report_tools.RenderReportInput.model_json_schema()
    assert set(schema["properties"]) == {"report"}, "input must expose only `report`"


# Determinism (byte-identical renders apart from the timestamp) is covered at the
# render_report level in test_report_render.py, which pins generated_at; the tool
# wrapper cannot inject a fixed clock, so re-testing it here would only couple a
# determinism claim to a wall-clock minute boundary.


# --------------------------------------------------------------------------
# The duplication the client has to strip
# --------------------------------------------------------------------------


def test_html_is_emitted_in_both_content_and_structured():
    """Documents why a context-keeping client must strip BOTH copies.

    If this ever stops being true, the portal's strip logic can be simplified;
    until then, stripping only one copy leaves the full markup in context.
    """
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
    site. Re-nesting inflates the longest percent-encoded href in the document,
    which tokenizes at ~2.2 chars/token.
    """
    import urllib.parse

    url = build_collection_url(["101M", "1ASH"])
    query = json.loads(urllib.parse.unquote(url.split("request=", 1)[1]))["query"]
    assert query["type"] == "group"
    assert [n["type"] for n in query["nodes"]] == ["terminal"]
