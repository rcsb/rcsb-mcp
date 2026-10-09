"""Notes for filters that do not mean what they read as.

Two notes rcsb_search_request adds next to the intersection and thin-result ones, each
firing only on the filters it is about:

* composition -- oligomeric state and chain counts count a bound peptide as a chain, so a
  homodimer with a peptide in each site is "Hetero 4-mer" and a "Homo 2-mer" filter
  misses it (14-3-3 + phosphopeptide: ~90% of the dimers).
* missing value -- a value filter on an attribute many entries leave empty (crystal pH:
  27% of X-ray entries) drops those entries untested. The note says how many, counted live
  by swapping the filter for "has no value" while requiring the category's anchor, so
  entries the attribute cannot apply to (pH on a cryo-EM entry) are not counted.

Network-free: the Search API is replaced by a stub that records each request.
"""

import asyncio
import copy

import pytest

from rcsb_mcp import queries, query_doc, search
from rcsb_mcp.search_attributes import SPARSE_SEARCH_ATTRIBUTES

PH = "exptl_crystal_grow.pH"
PH_ANCHOR = "exptl_crystal_grow.pdbx_details"
RES = "rcsb_entry_info.resolution_combined"
OLIGO = "rcsb_struct_symmetry.oligomeric_state"


def term(attribute, operator="exact_match", value="x", negation=False):
    params = {"attribute": attribute, "operator": operator}
    if operator != "exists":
        params["value"] = value
    if negation:
        params["negation"] = True
    return {"type": "terminal", "service": "text", "parameters": params}


def group(op, *nodes):
    return {"type": "group", "logical_operator": op, "nodes": list(nodes)}


PH_RANGE = term(PH, "range", {"from": 7.0, "to": 7.8})
HIRES = term(RES, "less", 2.0)


# --------------------------------------------------------------------------- #
# composition
# --------------------------------------------------------------------------- #
def test_composition_note_fires_on_a_value_filter_on_any_composition_attribute():
    for attribute in queries.COMPOSITION_ATTRIBUTES:
        node = group("and", term(attribute, value="Homo 2-mer"), HIRES)
        assert queries.composition_note(node) == queries.COMPOSITION_NOTE, attribute
    # an OR does not change what the filter means, so it still applies
    assert queries.composition_note(group("or", term(OLIGO), HIRES))


def test_composition_note_stays_silent_where_it_does_not_apply():
    assert queries.composition_note(HIRES) is None
    assert queries.composition_note(term(OLIGO, "exists")) is None          # no value tested
    assert queries.composition_note(term(OLIGO, negation=True)) is None     # excluding, not selecting
    chem = {"type": "terminal", "service": "text_chem",
            "parameters": {"attribute": OLIGO, "operator": "exact_match", "value": "x"}}
    assert queries.composition_note(chem) is None


def test_every_composition_attribute_is_searchable():
    """A misspelt path here would silently never fire."""
    assert queries.COMPOSITION_ATTRIBUTES <= set(search._ATTR_INDEX["structure"])


# --------------------------------------------------------------------------- #
# missing-value probes (pure)
# --------------------------------------------------------------------------- #
CHECKED = {PH: PH_ANCHOR}
ABSENT = {"type": "group", "logical_operator": "and", "nodes": [
    {"type": "terminal", "service": "text",
     "parameters": {"attribute": PH, "operator": "exists", "negation": True}},
    {"type": "terminal", "service": "text",
     "parameters": {"attribute": PH_ANCHOR, "operator": "exists"}},
]}


def test_a_sparse_value_filter_anded_with_the_rest_gets_one_probe():
    node = group("and", PH_RANGE, HIRES)
    before = copy.deepcopy(node)
    [(attribute, probe)] = queries.missing_value_probes(node, CHECKED)
    assert attribute == PH
    # "no pH, but a crystallisation record": a cryo-EM entry never had pH to leave out
    assert probe["nodes"][0] == ABSENT
    assert probe["nodes"][1] == HIRES, "the rest of the query is left exactly as it was"
    assert node == before, "the caller's query must not be modified"


def test_the_swap_reaches_into_nested_and_groups():
    node = group("and", HIRES, group("and", term(RES, "greater", 1.0), PH_RANGE))
    [(_, probe)] = queries.missing_value_probes(node, CHECKED)
    assert probe["nodes"][1]["nodes"][1] == ABSENT
    assert probe["nodes"][1]["nodes"][0] == node["nodes"][1]["nodes"][0]


def test_a_band_on_one_attribute_is_swapped_whole():
    """pH >= 7 AND pH <= 8 swapped one bound at a time paired "no pH" with the other bound
    and counted 0 every time: the note never appeared (live, Mpro: the real gap was 669)."""
    node = group("and", term(PH, "greater_or_equal", 7.0), term(PH, "less_or_equal", 8.0), HIRES)
    [(attribute, probe)] = queries.missing_value_probes(node, CHECKED)
    assert attribute == PH
    remaining = [t["parameters"] for t in queries._terminals(probe)]
    assert not any(p["attribute"] == PH and p["operator"] != "exists" for p in remaining), \
        "no bound may survive next to 'has no value'"
    assert {"attribute": PH, "operator": "exists", "negation": True} in remaining


def test_a_band_alone_has_no_rest_to_match():
    node = group("and", term(PH, "greater_or_equal", 7.0), term(PH, "less_or_equal", 8.0))
    assert queries.missing_value_probes(node, CHECKED) == []


@pytest.mark.parametrize("node", [
    PH_RANGE,                                              # alone: no "rest" to match
    group("or", PH_RANGE, HIRES),                          # under OR the swap changes the rest
    group("and", HIRES, group("or", PH_RANGE, HIRES)),     # ...at any depth
    group("and", term(PH, "exists"), HIRES),               # no value tested
    group("and", term(PH, "range", {"from": 7}, negation=True), HIRES),
    group("and", term(RES, "less", 2.0), HIRES),           # not a sparse attribute
])
def test_no_probe_where_the_count_would_not_mean_what_the_note_says(node):
    assert queries.missing_value_probes(node, CHECKED) == []


def test_probes_are_capped():
    checked = {PH: PH_ANCHOR, "refine.B_iso_mean": "refine.ls_R_factor_R_work",
               "reflns.B_iso_Wilson_estimate": "reflns.d_resolution_high"}
    node = group("and", HIRES, *(term(a, "less", 1) for a in sorted(checked)))
    assert len(queries.missing_value_probes(node, checked)) == queries.MAX_MISSING_VALUE_PROBES


def test_the_checked_set_is_the_sparse_attributes_outside_nested_documents():
    assert search._MISSING_VALUE_CHECKED[PH] == PH_ANCHOR
    assert search._MISSING_VALUE_CHECKED.items() <= SPARSE_SEARCH_ATTRIBUTES.items()
    assert not any(search._ATTR_INDEX["structure"][a].get("nested_group")
                   for a in search._MISSING_VALUE_CHECKED)


# --------------------------------------------------------------------------- #
# wired into rcsb_search_request
# --------------------------------------------------------------------------- #
@pytest.fixture
def api(monkeypatch):
    """A Search API stub: the main search returns 2 hits; a probe returns `gap`."""
    state = {"gap": 669, "probe_error": False, "sent": []}

    async def fake_post(body):
        state["sent"].append(body)
        is_probe = any(t.get("parameters", {}).get("negation") and
                       t["parameters"].get("operator") == "exists"
                       for t in queries._terminals(body["query"]))
        if is_probe:
            if state["probe_error"]:
                raise RuntimeError("RCSB Search API timed out")
            return {"total_count": state["gap"]}
        return {"total_count": 2, "result_set": [
            {"identifier": "7CUT", "score": 1.0}, {"identifier": "2HAL", "score": 0.9}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    return state


def run(node, **kw):
    doc = query_doc.sign(node)
    return asyncio.run(search.rcsb_search_request(doc, return_type="entry", **kw))


def test_the_gap_is_counted_and_reported(api):
    r = run(group("and", PH_RANGE, HIRES))
    notes = [n for n in r.get("notes", []) if PH in n]
    assert len(notes) == 1 and "669" in notes[0] and "excluded them untested" in notes[0]
    assert len(api["sent"]) == 2, "one search plus one count"
    probe = api["sent"][1]
    assert probe["request_options"]["return_counts"] is True
    assert probe["return_type"] == "entry"


def test_no_gap_no_note(api):
    api["gap"] = 0
    assert not any(PH in n for n in run(group("and", PH_RANGE, HIRES)).get("notes", []))


def test_a_failed_count_never_fails_the_search(api):
    api["probe_error"] = True
    r = run(group("and", PH_RANGE, HIRES))
    assert r["total_count"] == 2 and not any(PH in n for n in r.get("notes", []))


def test_queries_without_a_sparse_filter_send_one_request(api):
    run(group("and", HIRES, term("exptl.method", value="X-RAY DIFFRACTION")))
    assert len(api["sent"]) == 1, "the common case must not pay for the probe"


def test_a_slow_count_only_drops_its_note(api, monkeypatch):
    """The counts run alongside the search; one that outlives the budget is abandoned, so
    a finished search never waits on it for long."""
    monkeypatch.setattr(search, "_MISSING_VALUE_BUDGET", 0.05)
    fast = search._post_search

    async def slow_probe(body):
        if any(t["parameters"].get("negation") for t in queries._terminals(body["query"])
               if t.get("parameters")):
            await asyncio.sleep(1)
        return await fast(body)

    monkeypatch.setattr(search, "_post_search", slow_probe)
    r = run(group("and", PH_RANGE, HIRES))
    assert r["total_count"] == 2 and not any(PH in n for n in r.get("notes", []))


def test_a_failed_search_cancels_its_counts(monkeypatch):
    seen = []

    async def failing(body):
        if any(t["parameters"].get("negation") for t in queries._terminals(body["query"])
               if t.get("parameters")):
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                seen.append("cancelled")
                raise
            return {"total_count": 1}
        await asyncio.sleep(0.01)
        raise RuntimeError("RCSB Search API timed out")

    monkeypatch.setattr(search, "_post_search", failing)

    async def go():
        with pytest.raises(RuntimeError):
            await search.rcsb_search_request(query_doc.sign(group("and", PH_RANGE, HIRES)),
                                             return_type="entry")
        await asyncio.sleep(0)
    asyncio.run(go())
    assert seen == ["cancelled"]


def test_the_composition_note_reaches_the_caller(api):
    r = run(group("and", term(OLIGO, value="Homo 2-mer"), HIRES))
    assert queries.COMPOSITION_NOTE in r["notes"]


# --------------------------------------------------------------------------- #
# component paths searched as structure attributes
# --------------------------------------------------------------------------- #
COMP = "rcsb_chem_comp_container_identifiers.comp_id"
SHARED = frozenset({COMP, "chem_comp.name"})
VIRUS = term("rcsb_entity_source_organism.taxonomy_lineage.id", value="10239")


def test_a_component_condition_is_re_asked_of_the_chemical_index():
    """As a structure attribute a component path matches only non-polymer ligands: SEP 38
    entries, 2,328 through the chemical index; CF0 AND virus 0 vs the 9 viral FMK entries."""
    node = group("and", term(COMP, value="CF0"), VIRUS)
    before = copy.deepcopy(node)
    [(attribute, probe)] = queries.component_probes(node, SHARED)
    assert attribute == COMP
    assert probe["nodes"][0]["service"] == "text_chem"
    assert probe["nodes"][0]["parameters"] == node["nodes"][0]["parameters"]
    assert probe["nodes"][1] == VIRUS, "the rest of the query is untouched"
    assert node == before


@pytest.mark.parametrize("node", [
    term("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", value="SEP"),  # not shared
    term(COMP, "exists"),                                                    # nothing to widen
    term(COMP, value="SEP", negation=True),                                  # widening runs backwards
    {"type": "terminal", "service": "text_chem",                             # already chemical
     "parameters": {"attribute": COMP, "operator": "exact_match", "value": "SEP"}},
])
def test_no_component_probe_where_widening_means_nothing(node):
    assert queries.component_probes(node, SHARED) == []


def test_an_or_still_gets_the_probe():
    """Widening one condition can only keep or raise the count under OR too."""
    assert len(queries.component_probes(group("or", term(COMP, value="SEP"), VIRUS), SHARED)) == 1


def test_component_probes_are_capped():
    node = group("and", *(term(COMP, value=v) for v in ("SEP", "TPO", "PTR")))
    assert len(queries.component_probes(node, SHARED)) == queries.MAX_COMPONENT_PROBES


def test_the_shared_paths_are_the_component_paths_both_catalogs_carry():
    shared = search._SHARED_COMPONENT_PATHS
    assert COMP in shared and "chem_comp.name" in shared
    assert "rcsb_id" not in shared, "the entry id in the structure catalog, not a component"
    assert len(shared) > 50


@pytest.fixture
def chem_api(monkeypatch):
    """Main search: 38 hits. The same query through the chemical index: `wider`."""
    state = {"wider": 2328, "error": False}

    async def fake_post(body):
        if any(t.get("service") == "text_chem" for t in queries._terminals(body["query"])):
            if state["error"]:
                raise RuntimeError("RCSB Search API timed out")
            return {"total_count": state["wider"]}
        return {"total_count": 38, "result_set": [{"identifier": "1ABC", "score": 1.0}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    return state


def test_the_wider_count_reaches_the_caller(chem_api):
    [note] = [n for n in run(term(COMP, value="SEP")).get("notes", []) if "chemical index" in n]
    assert "38" in note and "2,328" in note and "chemical_attributes=True" in note


def test_no_wider_count_no_note(chem_api):
    chem_api["wider"] = 38      # a pure ligand (HEM: 6,485 either way)
    assert not any("chemical index" in n for n in run(term(COMP, value="HEM")).get("notes", []))


def test_a_failed_chemical_count_never_fails_the_search(chem_api):
    chem_api["error"] = True
    r = run(term(COMP, value="SEP"))
    assert r["total_count"] == 38 and not any("chemical index" in n for n in r.get("notes", []))
