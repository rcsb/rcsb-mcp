"""Tests for the deterministic report renderer.

The renderer takes a ReportDocument -- the resolved table the server builds from
the agent's identifiers -- so these construct documents directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rcsb_mcp.report import (
    ApiCall,
    Column,
    ColumnKind,
    DataUsageItem,
    EditorLink,
    Evidence,
    ReportDocument,
    render_report,
)

FIXED = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _minimal(**kw) -> ReportDocument:
    base = dict(
        title="Test report",
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="resolution", label="Resolution (Å)", kind=ColumnKind.NUMERIC),
        ],
        rows=[{"pdb_id": "4HHB", "resolution": 1.74}],
    )
    base.update(kw)
    return ReportDocument(**base)


def _with_evidence(ev: Evidence) -> ReportDocument:
    """A one-row document whose evidence cell carries the Evidence object under test."""
    return ReportDocument(
        title="t",
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="evidence", label="Evidence"),
        ],
        rows=[{"pdb_id": "2QDY", "evidence": ev}],
    )


# --------------------------------------------------------------------------
# The core guarantee
# --------------------------------------------------------------------------


def test_render_is_byte_identical_across_runs():
    req = _minimal()
    a = render_report(req, generated_at=FIXED)
    b = render_report(req, generated_at=FIXED)
    assert a == b


def test_chrome_is_stable_when_content_changes():
    """Different content must not perturb the CSS block."""
    one = render_report(_minimal(title="A"), generated_at=FIXED)
    two = render_report(_minimal(title="B different title entirely"), generated_at=FIXED)
    css_one = one[one.index("<style>") : one.index("</style>")]
    css_two = two[two.index("<style>") : two.index("</style>")]
    assert css_one == css_two


# --------------------------------------------------------------------------
# Escaping — the requirement that is easy to forget by hand
# --------------------------------------------------------------------------


def test_tool_text_is_escaped():
    req = _minimal(title='Crystal structure of <script>alert(1)</script> & friends')
    html = render_report(req, generated_at=FIXED)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp; friends" in html


def test_evidence_interpretation_is_escaped_inside_provenance_span():
    req = _with_evidence(Evidence(grounds="ok", interpretation="a < b & c"))
    html = render_report(req, generated_at=FIXED)
    assert '<span class="non-tool-source">a &lt; b &amp; c</span>' in html


def test_data_usage_body_is_escaped_and_never_wrapped():
    """Data usage is plain agent narrative now: escaped, but never provenance-coloured."""
    req = _minimal(data_usage=[DataUsageItem(heading="Note", body="a < b & c")])
    html = render_report(req, generated_at=FIXED)
    assert "a &lt; b &amp; c" in html
    assert '<span class="non-tool-source">a &lt; b &amp; c</span>' not in html


# --------------------------------------------------------------------------
# Provenance — lives ONLY in the Evidence cell now
# --------------------------------------------------------------------------


def test_evidence_grounds_are_plain_and_interpretation_is_wrapped():
    """grounds render tool-sourced (no span); the interpretation half gets the colour."""
    req = _with_evidence(
        Evidence(grounds="EC 4.2.1.1; bound ZN", interpretation="a carbonic anhydrase fold")
    )
    html = render_report(req, generated_at=FIXED)
    assert "EC 4.2.1.1; bound ZN" in html
    assert '<span class="non-tool-source">a carbonic anhydrase fold</span>' in html
    # the tool-sourced grounds half is never wrapped
    assert '<span class="non-tool-source">EC 4.2.1.1' not in html


def test_evidence_without_interpretation_has_no_provenance_span():
    req = _with_evidence(Evidence(grounds="Thr315 gatekeeper residue"))
    html = render_report(req, generated_at=FIXED)
    assert "Thr315 gatekeeper residue" in html
    # grounds-only evidence must not be wrapped in the assistant colour
    assert '<span class="non-tool-source">Thr315' not in html


# --------------------------------------------------------------------------
# Cells and columns
# --------------------------------------------------------------------------


def test_pdb_id_column_is_linked():
    html = render_report(_minimal(), generated_at=FIXED)
    assert '<a href="https://www.rcsb.org/structure/4HHB" target="_blank" rel="noopener">4HHB</a>' in html


def test_missing_and_none_values_render_as_na():
    req = ReportDocument(
        title="t",
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="resolution", label="Resolution (Å)", kind=ColumnKind.NUMERIC),
        ],
        rows=[{"pdb_id": "6XYZ", "resolution": None}, {"pdb_id": "7ABC"}],
    )
    html = render_report(req, generated_at=FIXED)
    assert html.count("NA") >= 2


def test_columns_can_be_reordered_and_replaced():
    """The frame is rigid; the table is parametric."""
    req = ReportDocument(
        title="Ligand search",
        columns=[
            Column(key="comp_id", label="Component ID", kind=ColumnKind.LIGAND_ID),
            Column(key="formula", label="Formula"),
            Column(key="weight", label="Weight", kind=ColumnKind.NUMERIC),
        ],
        rows=[{"comp_id": "ATP", "formula": "C10 H16 N5 O13 P3", "weight": 507.181}],
    )
    html = render_report(req, generated_at=FIXED)
    assert "https://www.rcsb.org/ligand/ATP" in html
    assert "Component ID" in html
    assert "PDB ID" not in html


def test_unknown_row_key_is_rejected():
    with pytest.raises(ValidationError, match="not declared in columns"):
        ReportDocument(
            title="t",
            columns=[Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID)],
            rows=[{"pdb_id": "4HHB", "typo_key": "oops"}],
        )




# --------------------------------------------------------------------------
# API call provenance
# --------------------------------------------------------------------------


def test_editor_must_come_from_rcsb():
    with pytest.raises(ValidationError, match="returned verbatim"):
        ApiCall(label="hand-built", editor={"url": "https://example.com/query-editor", "params": {}})


def test_resolver_calls_without_editor_are_allowed():
    call = ApiCall(label="Resolved EC class", tool_name="rcsb_find_enzyme_classes")
    html = render_report(_minimal(api_calls=[call]), generated_at=FIXED)
    assert "Resolved EC class" in html
    assert "no editor link for this tool" in html
    # This is a server annotation, not agent interpretation: it must NOT wear the
    # provenance colour, which now means "agent interpretation in Evidence" and nothing else.
    assert '<span class="non-tool-source">(no editor link' not in html
    assert '<span class="muted">(no editor link for this tool)</span>' in html


def test_provenance_colour_appears_only_in_the_legend_and_evidence():
    """The orange class means exactly one thing now — agent interpretation in Evidence — so
    it must never leak onto server-generated notes (API-requests annotations, data usage,
    no-results). Guarded by count: legend swatch (1) + one interpretation (1) = 2, no more."""
    doc = ReportDocument(
        title="t",
        api_calls=[ApiCall(label="Resolved EC class", tool_name="rcsb_find_enzyme_classes")],
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="evidence", label="Evidence"),
        ],
        rows=[
            {"pdb_id": "1CA2", "evidence": Evidence(grounds="EC 4.2.1.1", interpretation="a carbonic anhydrase")},
            {"pdb_id": "3KS3", "evidence": Evidence(grounds="title match")},  # grounds-only -> no span
        ],
        data_usage=[DataUsageItem(heading="Discovery", body="812 entries matched.")],
    )
    html = render_report(doc, generated_at=FIXED)
    assert html.count('class="non-tool-source"') == 2


def test_editor_object_renders_as_percent_encoded_url():
    """The un-encoded editor object must render to the exact URL the tool used
    to embed directly: json.dumps(compact) then percent-encode, `&amp;` between params."""
    search = ApiCall(
        label="Search",
        editor=EditorLink(
            url="https://search.rcsb.org/query-editor.html",
            params={"json": {"query": {"type": "terminal"}, "return_type": "entry"}},
        ),
    )
    graphiql = ApiCall(
        label="Fetch",
        editor=EditorLink(
            url="https://data.rcsb.org/graphiql/index.html",
            params={"query": "query{x}", "variables": {"ids": ["4HHB"]}},
        ),
    )
    html = render_report(_minimal(api_calls=[search, graphiql]), generated_at=FIXED)
    # Compact JSON, no spaces, fully percent-encoded (`{`->%7B, `:`->%3A, `"`->%22).
    assert (
        'href="https://search.rcsb.org/query-editor.html?json='
        "%7B%22query%22%3A%7B%22type%22%3A%22terminal%22%7D%2C%22return_type%22%3A%22entry%22%7D"
        '"' in html
    )
    # query is a bare string (percent-encoded), then `&amp;variables=` (autoescaped `&`).
    assert (
        'href="https://data.rcsb.org/graphiql/index.html?query=query%7Bx%7D'
        "&amp;variables=%7B%22ids%22%3A%5B%224HHB%22%5D%7D"
        '"' in html
    )


def test_editor_href_hardening_for_degenerate_agent_input():
    """Agent-hand-built (not tool-verbatim) editors must degrade cleanly, never
    diverging with a `variables=null` or a dangling `?`."""
    # A None-valued param is dropped, not encoded as "null" (mirrors the tools).
    none_var = ApiCall(
        label="Fetch",
        editor=EditorLink(
            url="https://data.rcsb.org/graphiql/index.html",
            params={"query": "q{x}", "variables": None},
        ),
    )
    html = render_report(_minimal(api_calls=[none_var]), generated_at=FIXED)
    assert 'href="https://data.rcsb.org/graphiql/index.html?query=q%7Bx%7D"' in html
    assert "variables=null" not in html
    # Empty params yield the bare base URL, no dangling "?".
    empty = ApiCall(
        label="Search",
        editor=EditorLink(url="https://search.rcsb.org/query-editor.html", params={}),
    )
    html = render_report(_minimal(api_calls=[empty]), generated_at=FIXED)
    assert 'href="https://search.rcsb.org/query-editor.html"' in html
    assert "query-editor.html?" not in html


# --------------------------------------------------------------------------
# Empty result set
# --------------------------------------------------------------------------


def test_empty_results_render_the_no_results_block():
    req = ReportDocument(
        title="Nothing found",
        no_results_note="No entries carry this EC and a bound iron ion.",
    )
    html = render_report(req, generated_at=FIXED)
    assert "No matching structures were found." in html
    assert "No entries carry this EC and a bound iron ion." in html
    # plain prose now — never wrapped in the provenance colour
    assert '<span class="non-tool-source">No entries' not in html
    assert "<table>" not in html


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def test_all_required_sections_appear_in_fixed_order():
    req = _minimal(
        api_calls=[ApiCall(label="Search", editor=EditorLink(url="https://search.rcsb.org/query-editor.html", params={"json": {}}))],
        data_usage=[DataUsageItem(heading="Discovery", body="One structured query.")],
    )
    html = render_report(req, generated_at=FIXED)
    # Anchor on the section HEADERS, not bare substrings — the legend prose also
    # mentions "Results" and "Data usage summary", so a substring search matches there.
    order = [
        "<h2>API requests</h2>",
        "<h2>Results</h2>",
        "<h2>Data usage summary</h2>",
    ]
    positions = [html.index(s) for s in order]
    assert positions == sorted(positions)


def test_template_version_is_recorded_in_output():
    from rcsb_mcp.report import TEMPLATE_VERSION

    html = render_report(_minimal(), generated_at=FIXED)
    assert TEMPLATE_VERSION in html
