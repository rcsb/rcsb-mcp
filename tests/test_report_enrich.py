"""Tests for building a resolved ReportDocument from the agent's identifiers.

The agent supplies only ids + evidence; every other cell is derived server-side
from the id. These cover the mapping, both table specs, and above all the
best-effort guarantee: no API response may cost a finished report.
"""

from __future__ import annotations

import asyncio

import pytest

from rcsb_mcp.report import enrich, tables
from rcsb_mcp.report.models import ReportRequest, Result, ResultType


def _run(coro):
    """Drive a coroutine to completion (the project has no pytest-asyncio)."""
    return asyncio.run(coro)


def _req(ids, result_type=ResultType.ENTRY, **kw):
    return ReportRequest(
        title="t",
        result_type=result_type,
        results=[Result(id=i, evidence=[{"text": "matched"}]) for i in ids],
        **kw,
    )


def _entry(rcsb_id="4HHB", title="T", method="X-RAY DIFFRACTION", res=(1.74,), organisms=("Homo sapiens",)):
    return {
        "rcsb_id": rcsb_id,
        "struct": {"title": title},
        "exptl": [{"method": method}],
        "rcsb_entry_info": {"resolution_combined": list(res)},
        "polymer_entities": [
            {"rcsb_entity_source_organism": [{"ncbi_scientific_name": o}]} for o in organisms
        ],
    }


def _comp(rcsb_id="ATP", name="ADENOSINE-5'-TRIPHOSPHATE", type_="non-polymer", weight=507.181):
    return {"rcsb_id": rcsb_id, "chem_comp": {"name": name, "type": type_, "formula_weight": weight}}


def _fetcher(nodes):
    async def fetch(query, root_field, ids):
        return nodes

    return fetch


# --------------------------------------------------------------------------
# Value mapping
# --------------------------------------------------------------------------


def test_entry_values_maps_the_derivable_cells():
    assert tables.entry_values(_entry()) == {
        "title": "T",
        "organism": "Homo sapiens",
        "method": "X-RAY DIFFRACTION",
        "resolution": 1.74,
    }


def test_ligand_values_maps_the_derivable_cells():
    assert tables.ligand_values(_comp()) == {
        "name": "ADENOSINE-5'-TRIPHOSPHATE",
        "type": "non-polymer",
        "weight": 507.181,
    }


def test_all_distinct_organisms_are_shown_in_order():
    """A complex carries several organisms; show every one rather than picking."""
    entry = _entry(organisms=("Homo sapiens", "HIV-1", "Homo sapiens"))
    assert tables.entry_values(entry)["organism"] == "Homo sapiens; HIV-1"


def test_organism_falls_back_to_scientific_name():
    """193D/1MJ0 carry only scientific_name; keying on ncbi_ alone rendered them NA."""
    entry = {"rcsb_id": "1MJ0", "polymer_entities": [
        {"rcsb_entity_source_organism": [
            {"ncbi_scientific_name": None, "scientific_name": "Designed synthetic gene"}]}]}
    assert tables.entry_values(entry)["organism"] == "Designed synthetic gene"


def test_multiple_methods_are_all_shown_but_resolution_stays_single():
    """Joint X-ray/neutron entries (10YN, 5E5J) are real — show both methods.

    Resolution must NOT be joined alongside them: resolution_combined is ordered by
    the `refine` block, not by `exptl`, so side-by-side lists assert a pairing that
    is actually reversed for 10YN (refine: NEUTRON=2.4, X-RAY=1.65).
    """
    entry = _entry()
    entry["exptl"] = [{"method": "X-RAY DIFFRACTION"}, {"method": "NEUTRON DIFFRACTION"}]
    entry["rcsb_entry_info"]["resolution_combined"] = [2.4, 1.65]
    v = tables.entry_values(entry)
    assert v["method"] == "X-RAY DIFFRACTION; NEUTRON DIFFRACTION"
    assert v["resolution"] == 1.65, "best resolution, as a number — never a joined pair"


def test_missing_fields_become_none_not_crashes():
    """NMR has no resolution; any field can be absent entirely."""
    assert tables.entry_values({"rcsb_id": "1ABC"}) == {
        "title": None, "organism": None, "method": None, "resolution": None,
    }
    assert tables.entry_values(_entry(res=()))["resolution"] is None
    assert tables.ligand_values({"rcsb_id": "ZZZ"}) == {"name": None, "type": None, "weight": None}


def test_computed_models_fall_back_to_determination_methodology():
    """An AlphaFold model has no exptl; don't render Method as NA."""
    entry = {"rcsb_id": "AF_X", "struct": {"title": "T"}, "exptl": None,
             "rcsb_entry_info": {"structure_determination_methodology": "computational"}}
    assert tables.entry_values(entry)["method"] == "computational"


# --------------------------------------------------------------------------
# Building the document
# --------------------------------------------------------------------------


def test_entry_document_has_the_fixed_six_columns():
    doc = _run(enrich.build_document(_req(["4HHB"]), _fetcher([_entry()])))
    assert [c.label for c in doc.columns] == [
        "PDB ID", "Title", "Organism", "Method", "Resolution (Å)", "Evidence"]
    assert doc.rows[0]["title"] == "T"
    assert doc.rows[0]["resolution"] == 1.74


def test_ligand_document_has_the_fixed_five_columns():
    doc = _run(enrich.build_document(_req(["ATP"], ResultType.LIGAND), _fetcher([_comp()])))
    assert [c.label for c in doc.columns] == [
        "Ligand ID", "Name", "Type", "Weight (Da)", "Evidence"]
    assert doc.rows[0]["name"] == "ADENOSINE-5'-TRIPHOSPHATE"
    assert doc.rows[0]["type"] == "non-polymer"


def test_evidence_and_id_survive_untouched():
    doc = _run(enrich.build_document(_req(["4HHB"]), _fetcher([_entry()])))
    assert doc.rows[0]["id"] == "4HHB"
    assert doc.rows[0]["evidence"][0].text == "matched"


def test_result_order_is_preserved_as_the_ranking():
    ids = ["3A8G", "2QDY", "4HHB"]
    doc = _run(enrich.build_document(_req(ids), _fetcher([])))
    assert [r["id"] for r in doc.rows] == ids


def test_id_matching_is_case_insensitive():
    doc = _run(enrich.build_document(_req(["4hhb"]), _fetcher([_entry(rcsb_id="4HHB")])))
    assert doc.rows[0]["title"] == "T"


def test_all_digit_pdb_id_sent_as_a_number_is_still_filled():
    """All-digit ids (1914) are real and a model may emit them unquoted."""
    req = ReportRequest(title="t", result_type=ResultType.ENTRY, results=[Result(id="1914")])
    doc = _run(enrich.build_document(req, _fetcher([_entry(rcsb_id="1914")])))
    assert doc.rows[0]["title"] == "T"


def test_unknown_id_renders_na_rather_than_agent_text():
    """The fetch resolved but the API didn't return this id — the cells are None."""
    doc = _run(enrich.build_document(_req(["9ZZZ"]), _fetcher([])))
    assert doc.rows[0]["id"] == "9ZZZ"
    assert all(doc.rows[0][k] is None for k in tables.ENTRY_SPEC.filled_keys)


def test_no_fetcher_still_renders_the_table():
    """Offline: id + evidence are agent-supplied, the rest shows NA."""
    doc = _run(enrich.build_document(_req(["4HHB"]), None))
    assert doc.rows[0]["id"] == "4HHB"
    assert doc.columns  # table structure is still there


def test_ids_are_deduped_and_normalised_before_fetching():
    seen = {}

    async def fetch(query, root_field, ids):
        seen["ids"] = ids
        return [_entry()]

    doc = _run(enrich.build_document(_req(["4hhb", " 4HHB "]), fetch))
    assert seen["ids"] == ["4HHB"]
    assert all(r["title"] == "T" for r in doc.rows)


def test_the_spec_selects_the_query_and_root_field():
    seen = {}

    async def fetch(query, root_field, ids):
        seen[root_field] = query
        return []

    _run(enrich.build_document(_req(["ATP"], ResultType.LIGAND), fetch))
    assert "chem_comps" in seen and "chem_comps(comp_ids:" in seen["chem_comps"].replace(" ", "")


# --------------------------------------------------------------------------
# The best-effort guarantee — no API response may cost a finished report
# --------------------------------------------------------------------------


@pytest.mark.parametrize("junk", [
    {"rcsb_id": "4HHB", "polymer_entities": [None]},              # null list member
    {"rcsb_id": 4321},                                             # non-str id
    {"rcsb_id": "4HHB", "struct": "not-a-dict"},                  # wrong shape
    {"rcsb_id": "4HHB", "exptl": "nope", "rcsb_entry_info": []},
    {"rcsb_id": "4HHB", "struct": {"title": {"nested": "obj"}}},  # value outside Cell
    {"rcsb_id": "4HHB", "chem_comp": "not-a-dict"},
    None,
    "a bare string",
])
def test_junk_from_the_api_never_destroys_the_report(junk):
    doc = _run(enrich.build_document(_req(["4HHB"]), _fetcher([junk])))
    assert doc.rows[0]["id"] == "4HHB"
    assert doc.rows[0]["evidence"][0].text == "matched"


def test_non_list_fetch_result_is_survived():
    doc = _run(enrich.build_document(_req(["4HHB"]), _fetcher(None)))
    assert doc.rows[0]["id"] == "4HHB"


def test_fetch_failure_never_loses_the_report():
    async def boom(query, root_field, ids):
        raise RuntimeError("data API down")

    doc = _run(enrich.build_document(_req(["4HHB"]), boom))
    assert doc.rows[0]["id"] == "4HHB"
    # A failed chunk omits the derivable keys entirely; the template's row.get()
    # renders them "NA", and omitting keeps the packed link smaller.
    assert doc.rows[0].get("title") is None


def test_a_failing_chunk_does_not_blank_other_rows():
    """Partial degradation: a chunk that failed leaves its rows NA, others filled."""
    calls = []

    async def flaky(query, root_field, ids):
        calls.append(ids)
        if "4HHB" in ids:
            return [_entry()]
        raise RuntimeError("upstream 429")

    ids = ["4HHB"] + [f"{i:03d}Z" for i in range(enrich.CHUNK + 10)]
    doc = _run(enrich.build_document(_req(ids), flaky))
    assert len(calls) > 1, "must chunk, not one unbounded request"
    assert doc.rows[0]["title"] == "T"          # succeeded chunk -> filled
    assert doc.rows[-1].get("title") is None    # failed chunk -> NA
