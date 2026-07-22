"""Tests for the deterministic report renderer."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from rcsb_mcp.report import (
    ApiCall,
    AttributeCondition,
    Block,
    Column,
    ColumnKind,
    CollectionLink,
    DataUsageItem,
    Fragment,
    QuerySummary,
    ReportRequest,
    build_collection_url,
    render_report,
)

FIXED = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)


def _minimal(**kw) -> ReportRequest:
    base = dict(
        title="Test report",
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="resolution", label="Resolution (Å)", kind=ColumnKind.NUMERIC),
        ],
        rows=[{"pdb_id": "4HHB", "resolution": 1.74}],
    )
    base.update(kw)
    return ReportRequest(**base)


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


def test_fragment_text_is_escaped_inside_provenance_span():
    req = _minimal(
        interpretation=[Block(body=[Fragment(text="a < b & c", model_supplied=True)])]
    )
    html = render_report(req, generated_at=FIXED)
    assert '<span class="non-tool-source">a &lt; b &amp; c</span>' in html


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


def test_model_supplied_fragments_are_wrapped_and_tool_ones_are_not():
    req = _minimal(
        summary=[
            Block(
                body=[
                    Fragment(text="32 entries matched."),
                    Fragment(text="Fe-type enzymes dominate.", model_supplied=True),
                ]
            )
        ]
    )
    html = render_report(req, generated_at=FIXED)
    assert "32 entries matched." in html
    assert '<span class="non-tool-source">Fe-type enzymes dominate.</span>' in html
    assert '<span class="non-tool-source">32 entries matched.' not in html


def test_mixed_provenance_inside_a_table_cell():
    req = ReportRequest(
        title="t",
        columns=[
            Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
            Column(key="info", label="Additional Information"),
        ],
        rows=[
            {
                "pdb_id": "2QDY",
                "info": [
                    {"text": "Thr315 gatekeeper residue"},
                    {"text": "commonly associated with imatinib resistance", "model_supplied": True},
                ],
            }
        ],
    )
    html = render_report(req, generated_at=FIXED)
    assert "Thr315 gatekeeper residue" in html
    assert '<span class="non-tool-source">commonly associated with imatinib resistance</span>' in html


# --------------------------------------------------------------------------
# Cells and columns
# --------------------------------------------------------------------------


def test_pdb_id_column_is_linked():
    html = render_report(_minimal(), generated_at=FIXED)
    assert '<a href="https://www.rcsb.org/structure/4HHB" target="_blank" rel="noopener">4HHB</a>' in html


def test_missing_and_none_values_render_as_na():
    req = ReportRequest(
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
    req = ReportRequest(
        title="Ligand search",
        columns=[
            Column(key="comp_id", label="Component ID", kind=ColumnKind.LIGAND_ID),
            Column(key="formula", label="Formula"),
            Column(key="weight", label="Weight", kind=ColumnKind.NUMERIC),
        ],
        rows=[{"comp_id": "ATP", "formula": "C10 H16 N5 O13 P3", "weight": 507.181}],
        collection=CollectionLink(return_type="mol_definition"),
    )
    html = render_report(req, generated_at=FIXED)
    assert "https://www.rcsb.org/ligand/ATP" in html
    assert "Component ID" in html
    assert "PDB ID" not in html


def test_unknown_row_key_is_rejected():
    with pytest.raises(ValidationError, match="not declared in columns"):
        ReportRequest(
            title="t",
            columns=[Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID)],
            rows=[{"pdb_id": "4HHB", "typo_key": "oops"}],
        )


# --------------------------------------------------------------------------
# Collection URL
# --------------------------------------------------------------------------


def test_collection_url_roundtrips_to_valid_json():
    url = build_collection_url(["101M", "1ASH", "4HHB"])
    assert url.startswith("https://www.rcsb.org/search?request=")
    payload = urllib.parse.unquote(url.split("request=", 1)[1])
    parsed = json.loads(payload)
    assert parsed["return_type"] == "entry"
    terminal = parsed["query"]["nodes"][0]
    assert terminal["parameters"]["value"] == ["101M", "1ASH", "4HHB"]
    assert terminal["parameters"]["attribute"] == "rcsb_entry_container_identifiers.entry_id"


def test_collection_rows_are_large_enough_for_the_set():
    url = build_collection_url([f"{i:04d}" for i in range(60)])
    parsed = json.loads(urllib.parse.unquote(url.split("request=", 1)[1]))
    assert parsed["request_options"]["paginate"]["rows"] >= 60


def test_ids_are_derived_from_the_identifier_column():
    html = render_report(_minimal(), generated_at=FIXED)
    assert "www.rcsb.org/search?request=" in html
    assert "Open 1 result in RCSB.org Advanced Search" in html


def test_collection_link_can_be_disabled():
    req = _minimal(collection=CollectionLink(enabled=False))
    html = render_report(req, generated_at=FIXED)
    assert "Explore the final collection" not in html


def test_mol_definition_uses_comp_id_attribute():
    url = build_collection_url(["ATP"], return_type="mol_definition")
    parsed = json.loads(urllib.parse.unquote(url.split("request=", 1)[1]))
    terminal = parsed["query"]["nodes"][0]
    assert terminal["parameters"]["attribute"] == "rcsb_chem_comp_container_identifiers.comp_id"


def test_unknown_return_type_gives_actionable_error():
    with pytest.raises(ValueError, match="pass collection.attribute explicitly"):
        build_collection_url(["X"], return_type="interface")


# --------------------------------------------------------------------------
# API call provenance
# --------------------------------------------------------------------------


def test_editor_url_must_come_from_rcsb():
    with pytest.raises(ValidationError, match="returned verbatim"):
        ApiCall(label="hand-built", editor_url="https://example.com/query-editor")


def test_resolver_calls_without_editor_url_are_allowed():
    call = ApiCall(label="Resolved EC class", tool_name="rcsb_find_enzyme_classes")
    html = render_report(_minimal(api_calls=[call]), generated_at=FIXED)
    assert "Resolved EC class" in html
    assert "no editor link for this tool" in html


# --------------------------------------------------------------------------
# Empty result set
# --------------------------------------------------------------------------


def test_empty_results_render_the_no_results_block():
    req = ReportRequest(
        title="Nothing found",
        no_results_note=[Fragment(text="No entries carry this EC and a bound iron ion.", model_supplied=True)],
    )
    html = render_report(req, generated_at=FIXED)
    assert "No matching structures were found." in html
    assert "<table>" not in html
    assert "Explore the final collection" not in html


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def test_all_required_sections_appear_in_fixed_order():
    req = _minimal(
        query=QuerySummary(
            total_count=32,
            conditions=[AttributeCondition(attribute="exptl.method", operator="exact_match", value="X-RAY DIFFRACTION")],
        ),
        api_calls=[ApiCall(label="Search", editor_url="https://search.rcsb.org/query-editor.html?json=%7B%7D")],
        data_usage=[DataUsageItem(heading="Discovery", body=[Fragment(text="One structured query.")])],
        interpretation=[Block(body=[Fragment(text="Interpretation.", model_supplied=True)])],
    )
    html = render_report(req, generated_at=FIXED)
    order = [
        "Search attributes and conditions",
        "API requests",
        "Results",
        "Data usage summary",
        "Interpretation",
        "Explore the final collection in RCSB.org",
    ]
    positions = [html.index(s) for s in order]
    assert positions == sorted(positions)


def test_template_version_is_recorded_in_output():
    from rcsb_mcp.report import TEMPLATE_VERSION

    html = render_report(_minimal(), generated_at=FIXED)
    assert TEMPLATE_VERSION in html
