"""Tests for server-side fill of the fixed result columns."""

from __future__ import annotations

import asyncio

import pytest

from rcsb_mcp.report import enrich
from rcsb_mcp.report.models import Column, ColumnKind, ReportRequest

FIXED_COLUMNS = [
    Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
    Column(key="title", label="Title"),
    Column(key="organism", label="Organism", kind=ColumnKind.ORGANISM),
    Column(key="method", label="Method"),
    Column(key="resolution", label="Resolution (Å)", kind=ColumnKind.NUMERIC),
    Column(key="evidence", label="Evidence"),
]


def _run(coro):
    """Drive a coroutine to completion (the project has no pytest-asyncio)."""
    return asyncio.run(coro)


def _entry(rcsb_id="4HHB", title="T", method="X-RAY DIFFRACTION", res=(1.74,), organisms=("Homo sapiens",)):
    return {
        "rcsb_id": rcsb_id,
        "struct": {"title": title},
        "exptl": [{"method": method}],
        "rcsb_entry_info": {"resolution_combined": list(res)},
        "polymer_entities": [{"rcsb_entity_source_organism": [{"ncbi_scientific_name": o}]} for o in organisms],
    }


def _report(rows, columns=None):
    return ReportRequest(title="t", columns=columns or FIXED_COLUMNS, rows=rows)


def _fetcher(entries):
    async def fetch(ids):
        return entries

    return fetch


# --------------------------------------------------------------------------
# Value mapping
# --------------------------------------------------------------------------


def test_entry_values_maps_the_four_columns():
    assert enrich.entry_values(_entry()) == {
        "title": "T",
        "organism": "Homo sapiens",
        "method": "X-RAY DIFFRACTION",
        "resolution": 1.74,
    }


def test_all_distinct_organisms_are_shown_in_order():
    """A complex carries several organisms; show every one rather than picking."""
    entry = _entry(organisms=("Homo sapiens", "HIV-1", "Homo sapiens"))
    assert enrich.entry_values(entry)["organism"] == "Homo sapiens; HIV-1"


def test_missing_fields_become_none_not_crashes():
    """NMR has no resolution; any field can be absent entirely."""
    assert enrich.entry_values({"rcsb_id": "1ABC"}) == {
        "title": None, "organism": None, "method": None, "resolution": None,
    }
    nmr = _entry(res=())
    assert enrich.entry_values(nmr)["resolution"] is None


# --------------------------------------------------------------------------
# Filling rows
# --------------------------------------------------------------------------


def test_rows_are_filled_from_the_ids_alone():
    req = _report([{"pdb_id": "4HHB", "evidence": "matched"}])
    _run(enrich.fill_from_entries(req, _fetcher([_entry()])))
    assert req.rows[0] == {
        "pdb_id": "4HHB",
        "evidence": "matched",
        "title": "T",
        "organism": "Homo sapiens",
        "method": "X-RAY DIFFRACTION",
        "resolution": 1.74,
    }


def test_server_value_overwrites_anything_the_agent_sent():
    """The API is the source of truth — a stale/hallucinated agent value must lose."""
    req = _report([{"pdb_id": "4HHB", "title": "WRONG", "resolution": 9.9, "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([_entry()])))
    assert req.rows[0]["title"] == "T"
    assert req.rows[0]["resolution"] == 1.74


def test_id_matching_is_case_insensitive():
    req = _report([{"pdb_id": "4hhb", "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([_entry(rcsb_id="4HHB")])))
    assert req.rows[0]["title"] == "T"


def test_unknown_id_keeps_the_row_and_renders_na():
    """The fetch resolved but the API didn't return this id (obsolete/hallucinated),
    so the server-owned cells are explicitly None -> "NA" at render."""
    req = _report([{"pdb_id": "9ZZZ", "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([])))
    assert req.rows[0]["pdb_id"] == "9ZZZ"
    assert req.rows[0]["evidence"] == "e"
    assert all(req.rows[0][k] is None for k in enrich.SERVER_FILLED_KEYS)


def test_fetch_failure_never_loses_the_report():
    async def boom(ids):
        raise RuntimeError("data API down")

    req = _report([{"pdb_id": "4HHB", "evidence": "e"}])
    _run(enrich.fill_from_entries(req, boom))
    assert req.rows[0] == {"pdb_id": "4HHB", "evidence": "e"}


def test_ligand_tables_are_left_alone():
    """A LIGAND_ID table has no entry-level method/resolution — don't touch it."""
    columns = [
        Column(key="comp_id", label="Ligand ID", kind=ColumnKind.LIGAND_ID),
        Column(key="title", label="Name"),
    ]
    req = _report([{"comp_id": "ATP", "title": "agent value"}], columns=columns)

    async def must_not_be_called(ids):
        raise AssertionError("ligand tables must not be enriched")

    _run(enrich.fill_from_entries(req, must_not_be_called))
    assert req.rows[0]["title"] == "agent value"


def test_only_declared_columns_are_filled():
    """Never introduce a row key that isn't a declared column — the model rejects it."""
    columns = [
        Column(key="pdb_id", label="PDB ID", kind=ColumnKind.PDB_ID),
        Column(key="evidence", label="Evidence"),
    ]
    req = _report([{"pdb_id": "4HHB", "evidence": "e"}], columns=columns)
    _run(enrich.fill_from_entries(req, _fetcher([_entry()])))
    assert set(req.rows[0]) == {"pdb_id", "evidence"}
    ReportRequest(title="t", columns=columns, rows=req.rows)  # must still validate


def test_multiple_methods_are_all_shown_but_resolution_stays_single():
    """Joint X-ray/neutron entries (10YN, 5E5J) are real — show both methods.

    Resolution must NOT be joined alongside them: resolution_combined is ordered by
    the `refine` block, not by `exptl`, so side-by-side lists assert a pairing that is
    actually reversed for 10YN (refine: NEUTRON=2.4, X-RAY=1.65). One value claims
    nothing about which method produced it.
    """
    entry = _entry()
    entry["exptl"] = [{"method": "X-RAY DIFFRACTION"}, {"method": "NEUTRON DIFFRACTION"}]
    entry["rcsb_entry_info"]["resolution_combined"] = [2.4, 1.65]
    v = enrich.entry_values(entry)
    assert v["method"] == "X-RAY DIFFRACTION; NEUTRON DIFFRACTION"
    assert v["resolution"] == 1.65, "best resolution, as a number — never a joined pair"


def test_organism_falls_back_to_scientific_name():
    """193D/1MJ0 carry only scientific_name; keying on ncbi_ alone rendered them NA."""
    entry = {"rcsb_id": "1MJ0", "polymer_entities": [
        {"rcsb_entity_source_organism": [{"ncbi_scientific_name": None, "scientific_name": "Designed synthetic gene"}]}]}
    assert enrich.entry_values(entry)["organism"] == "Designed synthetic gene"


def test_all_digit_pdb_id_sent_as_a_number_is_still_enriched():
    """All-digit ids (1914) are real and a model may emit them unquoted."""
    req = _report([{"pdb_id": 1914, "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([_entry(rcsb_id="1914")])))
    assert req.rows[0]["title"] == "T"


def test_ligand_column_blocks_enrichment_even_with_a_pdb_id_column():
    """`title` means the component name there — entry fill would clobber it."""
    columns = [
        Column(key="pdb_id", label="PDB", kind=ColumnKind.PDB_ID),
        Column(key="comp_id", label="Ligand", kind=ColumnKind.LIGAND_ID),
        Column(key="title", label="Ligand name"),
    ]
    req = _report([{"pdb_id": "4HHB", "comp_id": "HEM", "title": "PROTOPORPHYRIN IX"}], columns=columns)

    async def must_not_be_called(ids):
        raise AssertionError("a table containing a ligand column must not be enriched")

    _run(enrich.fill_from_entries(req, must_not_be_called))
    assert req.rows[0]["title"] == "PROTOPORPHYRIN IX"


def test_single_values_stay_scalar():
    """The common case must stay a number so the numeric column renders properly."""
    assert enrich.entry_values(_entry())["resolution"] == 1.74
    assert isinstance(enrich.entry_values(_entry())["resolution"], float)


def test_computed_models_fall_back_to_determination_methodology():
    """An AlphaFold model has no exptl; don't render Method as NA."""
    entry = {"rcsb_id": "AF_X", "struct": {"title": "T"}, "exptl": None,
             "rcsb_entry_info": {"structure_determination_methodology": "computational"}}
    assert enrich.entry_values(entry)["method"] == "computational"


@pytest.mark.parametrize("junk", [
    {"rcsb_id": "4HHB", "polymer_entities": [None]},          # null list member
    {"rcsb_id": 4321},                                         # non-str id
    {"rcsb_id": "4HHB", "struct": "not-a-dict"},              # wrong shape
    {"rcsb_id": "4HHB", "exptl": "nope", "rcsb_entry_info": []},
    {"rcsb_id": "4HHB", "struct": {"title": {"nested": "obj"}}},  # value outside Cell
])
def test_junk_from_the_api_never_destroys_the_report(junk):
    """The best-effort guarantee must cover response PARSING, not just the fetch."""
    req = _report([{"pdb_id": "4HHB", "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([junk])))
    assert req.rows[0]["pdb_id"] == "4HHB"
    assert req.rows[0]["evidence"] == "e"


def test_non_list_fetch_result_is_survived():
    _run(enrich.fill_from_entries(_report([{"pdb_id": "4HHB"}]), _fetcher(None)))


def test_unmatched_id_blanks_rather_than_keeping_agent_text():
    """A resolved fetch that omits an id means 'no such entry' -> NA, not stale agent text
    masquerading as tool-sourced."""
    req = _report([{"pdb_id": "9ZZZ", "title": "AGENT GUESS", "evidence": "e"}])
    _run(enrich.fill_from_entries(req, _fetcher([])))
    assert req.rows[0]["title"] is None


def test_id_column_found_without_an_explicit_kind():
    """A forgotten kind:pdb_id must not silently blank four columns for the whole table."""
    columns = [Column(key="pdb_id", label="PDB ID"), Column(key="title", label="Title")]
    req = _report([{"pdb_id": "4HHB"}], columns=columns)
    _run(enrich.fill_from_entries(req, _fetcher([_entry()])))
    assert req.rows[0]["title"] == "T"


def test_a_failing_chunk_does_not_blank_other_rows():
    """Partial degradation: rows in a chunk that failed keep what the agent supplied."""
    ids_seen = []

    async def flaky(ids):
        ids_seen.append(ids)
        if "4HHB" in ids:
            return [_entry()]
        raise RuntimeError("upstream 429")

    req = _report(
        [{"pdb_id": "4HHB", "evidence": "a"}] + [{"pdb_id": f"{i:03d}Z", "title": "kept", "evidence": "b"} for i in range(60)]
    )
    _run(enrich.fill_from_entries(req, flaky))
    assert len(ids_seen) > 1, "must chunk, not one unbounded request"
    assert req.rows[0]["title"] == "T"          # succeeded chunk -> filled
    assert req.rows[-1]["title"] == "kept"      # failed chunk -> untouched


def test_case_and_whitespace_variants_dedupe_to_one_id():
    seen = {}

    async def fetch(ids):
        seen["ids"] = ids
        return [_entry()]

    req = _report([{"pdb_id": "4hhb"}, {"pdb_id": " 4HHB "}])
    _run(enrich.fill_from_entries(req, fetch))
    assert seen["ids"] == ["4HHB"]


def test_ids_are_deduped_before_fetching():
    seen = {}

    async def fetch(ids):
        seen["ids"] = ids
        return [_entry()]

    req = _report([{"pdb_id": "4HHB", "evidence": "a"}, {"pdb_id": "4HHB", "evidence": "b"}])
    _run(enrich.fill_from_entries(req, fetch))
    assert seen["ids"] == ["4HHB"]
    assert all(r["title"] == "T" for r in req.rows)
