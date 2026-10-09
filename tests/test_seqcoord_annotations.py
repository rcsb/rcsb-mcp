"""rcsb_seqcoord_annotations: a PDB sequence and, optionally, feature types. No network.

The tool picks what agents used to: the reference (from the id's form), the sources (from the
types) and the TYPE filter, in the spelling the API matches. Each choice left to an agent gave
a silent zero (measured 2026-10-09): ACTIVE_SITE asked of PDB sources, an unknown or wrongly
cased type, DISULFIDE_BRIDGE itself (the API returns it but only filters "DISULFIDE BRIDGE"),
and an id that names no PDB sequence. An answer over the size budget is refused with the types
the sequence has.
"""

import asyncio

import pytest

from rcsb_mcp import queries, seqcoord
from rcsb_mcp.feature_types import FEATURE_TYPE_SOURCES

ALL = ["UNIPROT", "PDB_ENTITY", "PDB_INSTANCE", "PDB_INTERFACE"]


def _vars(query_id, feature_types=None):
    return queries.build_sc_annotations_query(query_id, feature_types)["variables"]


def _type_filter(*values):
    return [{"field": "TYPE", "operation": "EQUALS", "values": list(values)}]


@pytest.mark.parametrize("query_id, sent, reference", [
    ("4HHB_1", "4HHB_1", "PDB_ENTITY"),
    ("4HHB.A", "4HHB.A", "PDB_INSTANCE"),
    ("4hhb_1", "4HHB_1", "PDB_ENTITY"),        # measured: "4hhb_1" and "4hhb.a" return nothing
    ("4hhb.a", "4HHB.A", "PDB_INSTANCE"),      # RCSB chain ids are upper-case (3J3Q's 1356 too)
    ("pdb_00004hhb_1", "4HHB_1", "PDB_ENTITY"),  # measured: indexed only as 4HHB_1
    ("AF_AFP69905F1_1", "AF_AFP69905F1_1", "PDB_ENTITY"),
    ("AF_AFP69905F1.A", "AF_AFP69905F1.A", "PDB_INSTANCE"),
    ("MA_MABAKCEPC0001_1", "MA_MABAKCEPC0001_1", "PDB_ENTITY"),
])
def test_the_reference_follows_the_form_of_the_id(query_id, sent, reference):
    v = _vars(query_id)
    assert (v["queryId"], v["reference"]) == (sent, reference)


@pytest.mark.parametrize("query_id, message", [
    ("P69905", r'query_id="P69905", from_ref="UNIPROT".*rcsb_get_uniprot'),
    ("p69905", r'query_id="P69905"'),                 # the call it suggests must work as written
    ("NP_000508", r'from_ref="NCBI_PROTEIN"'),        # measured: taken as a PDB entity, it gave 0
    ("NC_000011.10", r'from_ref="NCBI_GENOME"'),
    ("4hhb", r"entities \(4HHB_1\) or instances \(4HHB.A\)"),
    ("pdb_00004hhb", r"entities \(4HHB_1\)"),
    ("", "PDB polymer entity"),
])
def test_an_id_that_is_not_a_pdb_sequence_is_refused_with_the_way_to_one(query_id, message):
    with pytest.raises(ValueError, match=message):
        _vars(query_id)


@pytest.mark.parametrize("feature_types", [None, []])
def test_without_types_every_source_is_asked_unfiltered(feature_types):
    v = _vars("4HHB_1", feature_types)
    assert (v["sources"], v["filters"]) == (ALL, None)


@pytest.mark.parametrize("feature_types, sources, values", [
    (["ACTIVE_SITE"], ["UNIPROT"], ["ACTIVE_SITE"]),               # UniProt's alone
    (["BINDING_SITE"], ["UNIPROT", "PDB_INSTANCE"], ["BINDING_SITE"]),
    (["ACTIVE_SITE", "CATH"], ["UNIPROT", "PDB_INSTANCE"], ["ACTIVE_SITE", "CATH"]),
    (["DISULFIDE_BRIDGE"], ["PDB_INSTANCE"], ["DISULFIDE BRIDGE"]),  # measured on 1CRN_1: 0 vs 3
    (["DISULFIDE_BRIDGE", "DISULFIDE_BRIDGE_"], ["PDB_INSTANCE"], ["DISULFIDE BRIDGE"]),
    (["DISULFIDE BRIDGE"], ["PDB_INSTANCE"], ["DISULFIDE BRIDGE"]),  # the filter spelling itself
    (["CIS_PEPTIDE", "SCOP_2_B_SUPERFAMILY"], ["PDB_INSTANCE"], ["CIS-PEPTIDE", "SCOP2B_SUPERFAMILY"]),
])
def test_types_choose_the_sources_and_the_spelling_the_filter_matches(feature_types, sources, values):
    v = _vars("4HHB_1", feature_types)
    assert (v["sources"], v["filters"]) == (sources, _type_filter(*values))


@pytest.mark.parametrize("value, first", [
    ("active site", "ACTIVE_SITE (UNIPROT)"),    # measured: "ACTIVE SITE" finds 0, ACTIVE_SITE 3 (2PTN_1)
    ("active_site", "ACTIVE_SITE (UNIPROT)"),
    ("disulfide bond", "DISULFIDE_BRIDGE (PDB_INSTANCE)"),  # not BOND_OUTLIER: BOND is common
    ("hydropaty", "HYDROPATHY (PDB_ENTITY)"),               # a near spelling: no type spells it so
    ("disordered region", "DISORDER (PDB_ENTITY)"),
    ("Pfam domain", "PFAM (PDB_ENTITY)"),
])
def test_an_unknown_type_is_refused_leading_with_the_closest(value, first):
    with pytest.raises(ValueError, match="is not a feature type") as err:
        _vars("4HHB_1", [value])
    assert str(err.value).split("Did you mean: ")[1].startswith(first)


def test_suggestions_skip_near_spellings_when_a_type_spells_the_word_out():
    with pytest.raises(ValueError) as err:
        _vars("4HHB_1", ["glycosylation"])
    assert "GLYCOSYLATION_SITE (UNIPROT)" in str(err.value)
    assert "GLYCYLATION" not in str(err.value)


def test_a_refused_type_points_to_a_call_without_types():
    with pytest.raises(ValueError, match="Call without feature_types"):
        _vars("4HHB_1", ["b-factor"])


def test_a_type_sequence_coordinates_does_not_serve_is_refused_and_never_suggested():
    """UNASSIGNED_SEC_STRUCT was removed from Sequence Coordinates on purpose; it used to be the
    only suggestion for "secondary structure", and asking for it answered "none here"."""
    with pytest.raises(ValueError, match="No source emits UNASSIGNED_SEC_STRUCT"):
        _vars("4HHB_1", ["UNASSIGNED_SEC_STRUCT"])
    with pytest.raises(ValueError) as err:
        _vars("4HHB_1", ["secondary structure"])
    assert "UNASSIGNED_SEC_STRUCT" not in str(err.value)


@pytest.mark.parametrize("value", ["protein binding", "protein_binding", "protein binding site"])
def test_a_type_no_source_emits_is_refused_and_never_suggested(value):
    assert FEATURE_TYPE_SOURCES["PROTEIN_BINDING"] == []
    with pytest.raises(ValueError, match="No source emits PROTEIN_BINDING"):
        _vars("4HHB_1", ["PROTEIN_BINDING"])
    with pytest.raises(ValueError) as err:
        _vars("4HHB_1", [value])
    assert "PROTEIN_BINDING" not in str(err.value) and "BINDING_SITE" in str(err.value)


# --- answers: empty, over the budget, timed out ------------------------------------------------

def _annotation(source, target, types, pad=0):
    return {"source": source, "target_id": target,
            "features": [{"type": t, "description": "x" * pad} for t in types]}


def _run(monkeypatch, answers, query_id="1AON_1", feature_types=None, fields=None):
    calls = []

    async def fake(body, root, url):
        calls.append(body)
        answer = answers[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(seqcoord, "_graphql_field", fake)
    result = asyncio.run(seqcoord.rcsb_seqcoord_annotations(query_id, feature_types, fields))
    return result, calls


def _refusal(monkeypatch, answers, **kw):
    with pytest.raises(ValueError) as err:
        _run(monkeypatch, answers, **kw)
    return str(err.value)


def test_an_answer_within_the_budget_is_returned_whole(monkeypatch):
    data = [_annotation("UNIPROT", "P0A6F5", ["BINDING_SITE"])]
    result, _ = _run(monkeypatch, [data])
    assert result["count"] == 1 and result["annotations"] == data and "note" not in result


def test_an_id_with_no_annotations_at_all_is_refused_as_unknown(monkeypatch):
    """Measured: 6M0J.E (the author's chain E, RCSB chain B) and 4HHB_3 (a heme) answer 0."""
    message = _refusal(monkeypatch, [[]], query_id="6M0J.E")
    assert "matches no PDB polymer sequence" in message and "label_asym_id" in message


def test_a_sequence_without_the_asked_types_says_so(monkeypatch):
    result, calls = _run(monkeypatch, [[], [{"source": "UNIPROT"}]], query_id="4HHB_1",
                         feature_types=["ACTIVE_SITE"])
    assert result["count"] == 0 and "has none of these feature types" in result["note"]
    assert calls[1]["variables"]["filters"] is None  # the check asks whether the id exists at all
    _ = _refusal(monkeypatch, [[], []], query_id="4HHB_9", feature_types=["ACTIVE_SITE"])


def _groel(chains="ABCDEFGHIJKLMN", per_chain=21, uniprot=2):
    return ([_annotation("UNIPROT", "P0A6F5", ["BINDING_SITE"] * uniprot)]
            + [_annotation("PDB_INSTANCE", f"1AON.{c}", ["HELIX_P"] * (per_chain - 1) + ["BINDING_SITE"], pad=300)
               for c in chains])


def test_an_answer_over_the_budget_is_refused_with_what_the_sequence_has(monkeypatch):
    """Measured: every source of GroEL 1AON_1 is ~165k tokens, the instance features once per copy."""
    message = _refusal(monkeypatch, [_groel()])
    assert "Ask for some of its feature_types or one instance (1AON.A, 1AON.B" in message
    assert "and 6 more" in message
    assert "BINDING_SITE (UNIPROT 2, PDB_INSTANCE 14)" in message
    assert "HELIX_P (PDB_INSTANCE 280)" in message


def test_one_instance_is_offered_only_when_it_would_fit(monkeypatch):
    """Measured: 4HHB_1 suggested 4HHB.A, refused again: its UniProt features alone are ~20k."""
    heavy = [_annotation("UNIPROT", "P69905", ["SEQUENCE_VARIANT"] * 140, pad=300)] + _groel("AC", 3, 0)[1:]
    message = _refusal(monkeypatch, [heavy], query_id="4HHB_1")
    assert "one instance" not in message and "Ask for some of its feature_types." in message


def test_the_way_to_narrow_depends_on_what_was_asked(monkeypatch):
    chains = [_annotation("PDB_INSTANCE", f"6VXX.{c}", ["HELIX_P", "SHEET"] * 30, pad=300) for c in "CBA"]
    message = _refusal(monkeypatch, [chains], query_id="6VXX_1", feature_types=["HELIX_P", "SHEET"])
    assert "Ask for fewer feature_types or one instance (6VXX.A, 6VXX.B, 6VXX.C)" in message
    # one type: fewer is impossible (measured: 3J3Q_1 HELIX_P alone is ~1.6M tokens)
    message = _refusal(monkeypatch, [chains], query_id="6VXX_1", feature_types=["HELIX_P"])
    assert "Ask for one instance (6VXX.A" in message
    # twins share one filter spelling, so they count as one type
    message = _refusal(monkeypatch, [chains], query_id="6VXX_1",
                       feature_types=["DISULFIDE_BRIDGE", "DISULFIDE_BRIDGE_"])
    assert "fewer feature_types" not in message
    # one type of one instance: only the selection is left
    big = [_annotation("PDB_INSTANCE", "6VXX.A", ["HELIX_P"] * 200, pad=300)]
    message = _refusal(monkeypatch, [big], query_id="6VXX.A", feature_types=["HELIX_P"])
    assert "Ask for a smaller `fields` selection." in message


def test_the_inventory_is_fetched_when_a_custom_selection_left_types_out(monkeypatch):
    big = [{"features": [{"beg_seq_id": 1, "description": "x" * 300}] * 200}]
    small = [_annotation("PDB_INSTANCE", "1AON.A", ["SHEET"])]
    with pytest.raises(ValueError, match=r"SHEET \(PDB_INSTANCE 1\)"):
        _run(monkeypatch, [big, small], feature_types=["SHEET", "HELIX_P"],
             fields="features{ beg_seq_id description }")


def test_the_inventory_refetch_keeps_the_types_and_selects_what_it_needs(monkeypatch):
    big = [{"features": [{"beg_seq_id": 1, "description": "x" * 300}] * 200}]
    calls = []

    async def fake(body, root, url):
        calls.append(body)
        return big if len(calls) == 1 else [_annotation("PDB_INSTANCE", "1AON.A", ["SHEET"])]

    monkeypatch.setattr(seqcoord, "_graphql_field", fake)
    with pytest.raises(ValueError):
        asyncio.run(seqcoord.rcsb_seqcoord_annotations("1AON_1", ["SHEET"], "features{ beg_seq_id }"))
    assert calls[1]["variables"]["filters"] == calls[0]["variables"]["filters"]
    assert seqcoord._INVENTORY_FIELDS in calls[1]["query"]


@pytest.mark.parametrize("query_id, entity_hint", [("3J3Q_1", True), ("1CRN.A", False)])
def test_a_timeout_says_try_again_and_how_to_narrow_an_entity(monkeypatch, query_id, entity_hint):
    timeout = RuntimeError("RCSB GraphQL API timed out; try again or simplify the query.")
    with pytest.raises(RuntimeError, match="try again shortly") as err:
        _run(monkeypatch, [timeout], query_id=query_id)
    assert ("one of its instances" in str(err.value)) == entity_hint


def test_other_errors_pass_through_unchanged(monkeypatch):
    bad = RuntimeError("Field 'featurs' is not defined on Annotation.")
    with pytest.raises(RuntimeError, match="^Field 'featurs' is not defined"):
        _run(monkeypatch, [bad], query_id="4HHB_1", fields="featurs{ type }")


def test_the_sources_are_ordered_as_the_catalog_lists_them():
    for sources in FEATURE_TYPE_SOURCES.values():
        assert sources == [s for s in queries.ANNOTATION_SOURCES if s in sources]


# --- feature-type search (the suggestions for a wrong name) ---------------------------------------------------------------------

from rcsb_mcp import feature_type_notes as notes  # noqa: E402
from rcsb_mcp.feature_types import FEATURE_TYPES, FEATURE_TYPES_BY_FIELD  # noqa: E402


def test_every_note_is_about_a_real_type_or_field():
    assert set(notes.FEATURE_TYPE_NOTES) <= set(FEATURE_TYPES)
    assert set(notes.FIELD_NOTES) == set(FEATURE_TYPES_BY_FIELD)
    for prefix in notes.PREFIX_NOTES:
        assert any(t.startswith(prefix) for t in FEATURE_TYPES), prefix


@pytest.mark.parametrize("concept, expected", [
    ("secondary structure", {"HELIX_P", "SHEET"}),           # codes no agent spells from the concept
    ("electron density fit", {"RSRZ", "RSCC"}),
    ("b-factor", {"OWAB"}),
    ("transmembrane", {"TRANSMEMBRANE_REGION", "MEMBRANE_SEGMENT"}),  # UniProt's and PDBTM's
    ("missing residues", {"UNOBSERVED_RESIDUE_XYZ"}),
    ("pLDDT", {"MA_QA_METRIC_LOCAL_TYPE_PLDDT"}),
    ("disulfide bond", {"DISULFIDE_BRIDGE"}),
])
def test_a_concept_finds_the_codes_that_name_it(concept, expected):
    assert expected <= set(queries.find_feature_types(concept)[:_TYPE_SUGGESTIONS])


_TYPE_SUGGESTIONS = queries._TYPE_SUGGESTIONS


def test_an_exact_name_comes_first_and_unservable_types_never_come():
    assert queries.find_feature_types("binding_site")[0] == "BINDING_SITE"
    for concept in ("protein binding", "secondary structure", "unassigned"):
        found = queries.find_feature_types(concept)
        assert "PROTEIN_BINDING" not in found and "UNASSIGNED_SEC_STRUCT" not in found




@pytest.mark.parametrize("concept, first", [
    # each was led by a wrong or empty type before review 4 (2026-10-09); measured where noted
    ("catalytic residues", "ACTIVE_SITE"),              # was absent: 2PTN_1 has 3 ACTIVE_SITE
    ("helices", "HELIX_P"),                             # was no result at all
    ("alpha helices", "HELIX_P"),                       # was HELX_RH_AL_P, on no chain
    ("N-linked glycosylation", "GLYCOSYLATION_SITE"),   # was CROSS_LINK (LINKED~LINK)
    ("covalent bonds", "COVALENT_BOND"),                # was LIGAND_COVALENT_LINKAGE
    ("prenylation", "LIPID_MOIETY_BINDING_REGION"),     # was ARSENYLATION by near spelling
    ("GPI anchor", "LIPID_MOIETY_BINDING_REGION"),
    ("ubiquitination", "CROSS_LINK"),                   # 1AXC.A: 3 ubiquitin isopeptides
    ("metal binding", "BINDING_SITE"),                  # was METAL_ION_BINDING_SITE, superseded
    ("calcium binding", "BINDING_SITE"),
    ("exposed residues", "ASA"),
    ("chain breaks", "UNOBSERVED_RESIDUE_XYZ"),
    ("gaps", "UNOBSERVED_RESIDUE_XYZ"),
    ("cofactor binding site", "BINDING_SITE"),          # was OWAB: COFACTOR~FACTOR of "B-factor"
    ("inhibitor binding", "BINDING_SITE"),              # was INITIATOR_METHIONINE
])
def test_a_concept_leads_with_the_type_that_holds_it(concept, first):
    assert queries.find_feature_types(concept)[0] == first


@pytest.mark.parametrize("name", ["covalent bond", "chain", "unobserved_residue_xyz",
                                  "_3_R_3_HYDROXYBUTYRYLATION", "DISULFIDE_BRIDGE_", "DISULFIDE_BRIDGE"])
def test_a_name_however_written_comes_first(name):
    expected = name.upper().replace(" ", "_")
    assert queries.find_feature_types(name)[0] == expected


def test_a_misspelling_counts_only_against_names_and_only_for_a_word_nothing_spells():
    assert queries.find_feature_types("hydropaty") == ["HYDROPATHY"]
    assert "OWAB" not in queries.find_feature_types("cofactor")  # not the FACTOR of its B-factor note
    assert queries.find_feature_types("AlphaFold")[0].startswith("MA_QA_METRIC_LOCAL_TYPE_")
    assert "CHEMICAL" not in " ".join(queries.find_feature_types("helical"))


def test_superseded_types_rank_after_current_ones_but_stay_findable():
    found = queries.find_feature_types("nucleotide binding")
    assert found[0] == "BINDING_SITE"
    assert found.index("NUCLEOTIDE_PHOSPHATE_BINDING_REGION") > found.index("NUCLEOTIDE_MONOPHOSPHATE")
    assert queries.find_feature_types("calcium_binding_region")[0] == "CALCIUM_BINDING_REGION"
