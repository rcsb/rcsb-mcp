"""Local validation of agent-supplied search attribute paths + operators.

Agents guess attribute paths from naming conventions; the Search API then reports a
guessed path as a capability limit ("aggregation is not allowed on the attribute"),
which reads as "exists but not aggregatable" and costs several round trips. search.py
validates every path/operator against the authoritative catalog BEFORE the API call,
so a guess fails fast, locally, with a "did you mean". These tests pin that.
"""

import ast
import inspect

import pytest

from rcsb_mcp import nested_attributes, search
from rcsb_mcp.search import (
    AttributeFilter,
    _check_attribute,
    _check_nested_attribute_pairs,
    _check_operator,
    _collect_query_attributes,
    _validate_advanced_body,
    _validate_query_attributes,
)

GOOD = "rcsb_entry_info.resolution_combined"  # a real numeric structure attribute


# --- the primitives --------------------------------------------------------
def test_valid_path_returns_the_catalog_record():
    rec = _check_attribute(GOOD, "structure")
    assert rec["attribute"] == GOOD and rec["type"] == "number"


def test_invalid_path_raises_and_steers_to_the_authoritative_lookup():
    with pytest.raises(ValueError) as e:
        _check_attribute("rcsb_ec_lineage.id", "structure")  # the short (guessed) EC form
    msg = str(e.value)
    assert "not a searchable structure attribute" in msg
    assert "rcsb_list_pdb_search_attributes" in msg  # points at the lookup, not a dead end
    assert "do not guess" in msg


def test_schema_selection_matters():
    """A structure-only attribute must not validate under the chemical catalog."""
    with pytest.raises(ValueError):
        _check_attribute(GOOD, "chemical")


def test_operator_is_checked_against_the_attributes_own_operator_list():
    rec = _check_attribute(GOOD, "structure")
    _check_operator(rec, "less")  # numeric op on a number -> fine
    with pytest.raises(ValueError, match="not valid for attribute"):
        _check_operator(rec, "contains_phrase")  # string op on a number -> rejected, lists valid ops


# --- the combined validator ------------------------------------------------
def test_validate_flags_condition_operator_and_facet_and_sort():
    ok = AttributeFilter(attribute=GOOD, operator="less", value=2)
    _validate_query_attributes(attributes=[ok])  # all valid -> no raise

    with pytest.raises(ValueError, match="not a searchable"):
        _validate_query_attributes(attributes=[AttributeFilter(attribute="made.up.path", operator="exact_match", value="x")])
    with pytest.raises(ValueError, match="not valid for attribute"):
        _validate_query_attributes(attributes=[AttributeFilter(attribute=GOOD, operator="contains_phrase", value="2")])
    with pytest.raises(ValueError, match="not a searchable"):
        _validate_query_attributes(facets=[{"name": "L", "aggregation_type": "terms",
                                            "attribute": "rcsb_nonpolymer_entity_container_identifiers.comp_id"}])
    with pytest.raises(ValueError, match="not a searchable"):
        _validate_query_attributes(sort_by="resolution")  # not the real path (resolution_combined)


def test_nested_facet_attribute_is_validated():
    with pytest.raises(ValueError, match="not a searchable"):
        _validate_query_attributes(facets=[{
            "name": "Method", "aggregation_type": "terms", "attribute": "exptl.method",
            "facets": [{"name": "bad", "aggregation_type": "terms", "attribute": "not.a.real.path"}],
        }])


# --- catalog is narrower than the live API in two spots: don't false-reject -----
def test_in_operator_is_accepted_on_numeric_and_date_attributes():
    """The live Search API accepts an `in` list match on numeric/date attributes; the
    generator maps `in` onto them, so the catalog carries it and validation accepts it."""
    for path in ("rcsb_entry_info.resolution_combined", "rcsb_entry_info.deposited_polymer_monomer_count"):
        rec = _check_attribute(path, "structure")
        assert "in" in rec["operators"], "catalog must carry `in` for numeric attrs (generator maps it on)"
        _check_operator(rec, "in")  # must NOT raise
    # and end-to-end through the combined validator
    _validate_query_attributes(attributes=[
        AttributeFilter(attribute="rcsb_entry_info.resolution_combined", operator="in", value=[2.0, 3.0])])


def test_text_operator_on_a_numeric_is_still_rejected():
    """The `in` exemption must not blanket-allow — a genuine type mismatch still raises."""
    with pytest.raises(ValueError, match="not valid for attribute"):
        _check_operator(_check_attribute("rcsb_entry_info.resolution_combined", "structure"), "contains_phrase")


def test_reserved_sort_score_is_allowed_but_a_guessed_sort_attribute_is_not():
    _validate_query_attributes(sort_by="score")  # reserved relevance sort -> must NOT raise
    with pytest.raises(ValueError, match="not a searchable"):
        _validate_query_attributes(sort_by="resolution")  # guessed (real path is resolution_combined)


# --- nested-attribute pairing (rcsb_search_by_attribute) -------------------
# The real pairs are re-derived from the LIVE metadata schema at most once a day (see
# rcsb_mcp.nested_attributes) rather than vendored, so these tests fake that loader with
# a fixed synthetic pair set instead of hitting the network.
NESTED_VALUE = "rcsb_binding_affinity.value"
NESTED_TYPE = "rcsb_binding_affinity.type"
_FAKE_PAIRS = {"structure": [(NESTED_VALUE, NESTED_TYPE)], "chemical": []}


@pytest.fixture(autouse=True)
def _fake_nested_pairs(monkeypatch):
    """Auto-applied in this file: every _check_nested_attribute_pairs call in these tests
    resolves against _FAKE_PAIRS instead of nested_attributes.download_schemas (network)."""
    monkeypatch.setattr(nested_attributes, "load_nested_attribute_pairs", lambda *a, **k: _FAKE_PAIRS)


def test_nested_attribute_alone_is_rejected():
    """A dependent nested attribute with no partner in the same filter list must raise —
    the Search API would otherwise silently match it outside the intended category."""
    with pytest.raises(ValueError, match="nested attribute"):
        _check_nested_attribute_pairs(
            [AttributeFilter(attribute=NESTED_VALUE, operator="greater", value=1)], "structure",
        )


def test_nested_attribute_partner_side_alone_is_also_rejected():
    """The category/type side is just as much a nested attribute as its dependent partner."""
    with pytest.raises(ValueError, match="nested attribute"):
        _check_nested_attribute_pairs(
            [AttributeFilter(attribute=NESTED_TYPE, operator="exact_match", value="x")], "structure",
        )


def test_nested_attribute_pair_together_is_accepted():
    _check_nested_attribute_pairs(
        [
            AttributeFilter(attribute=NESTED_VALUE, operator="greater", value=1),
            AttributeFilter(attribute=NESTED_TYPE, operator="exact_match", value="x"),
        ],
        "structure",
    )  # both present -> no raise


def test_non_nested_attributes_are_unaffected():
    _check_nested_attribute_pairs([AttributeFilter(attribute=GOOD, operator="less", value=2)], "structure")


def test_nested_attribute_check_is_schema_scoped():
    """A structure-only nested attribute isn't flagged when validated under the chemical
    schema (it simply isn't in that schema's partner map, so it isn't "nested" there)."""
    _check_nested_attribute_pairs(
        [AttributeFilter(attribute=NESTED_VALUE, operator="greater", value=1)], "chemical",
    )  # not a chemical-schema nested attribute -> no raise


def test_nested_attribute_check_degrades_gracefully_on_load_failure(monkeypatch):
    """If the day-cache can't be refreshed AND there's no prior cache to fall back to,
    the check must skip (not raise) — a metadata-endpoint hiccup must never break an
    otherwise-valid, unrelated search."""
    def boom(*a, **k):
        raise RuntimeError("network unreachable")
    monkeypatch.setattr(nested_attributes, "load_nested_attribute_pairs", boom)
    _check_nested_attribute_pairs(
        [AttributeFilter(attribute=NESTED_VALUE, operator="greater", value=1)], "structure",
    )  # load failure -> skipped, no raise


def test_every_search_tool_that_takes_attributes_is_covered_by_wiring_test_below():
    # Sanity: rcsb_search_by_attribute itself calls the nested check (not just the primitive).
    src = inspect.getsource(search.rcsb_search_by_attribute)
    assert "_check_nested_attribute_pairs" in src


# --- advanced (raw body) ---------------------------------------------------
def test_advanced_body_validates_text_terminals_and_ignores_malformed():
    good = {"query": {"type": "terminal", "service": "text",
                      "parameters": {"attribute": GOOD, "operator": "less", "value": 2}}}
    _validate_advanced_body(good)  # valid -> no raise
    _validate_advanced_body({})  # malformed / no query -> no raise (API validates the rest)
    _validate_advanced_body({"query": {"type": "terminal", "service": "sequence"}})  # non-text -> skipped

    bad = {"query": {"type": "group", "logical_operator": "and", "nodes": [
        {"type": "terminal", "service": "text", "parameters": {"attribute": "invented.path", "operator": "exact_match"}}]}}
    with pytest.raises(ValueError, match="not a searchable"):
        _validate_advanced_body(bad)


# --- _collect_query_attributes: the parser feeding validate_nested_attributes ----------
def _terminal(service, attribute, operator="exact_match"):
    return {"type": "terminal", "service": service, "parameters": {"attribute": attribute, "operator": operator}}


def test_collect_query_attributes_groups_by_schema():
    body = {"query": {"type": "group", "logical_operator": "and", "nodes": [
        _terminal("text", GOOD),
        _terminal("text_chem", "chem_comp.formula_weight"),
    ]}}
    assert _collect_query_attributes(body) == {
        "structure": [GOOD], "chemical": ["chem_comp.formula_weight"],
    }
    print("ok: collect_query_attributes groups by schema")


def test_collect_query_attributes_recurses_nested_groups():
    """A nested pair can straddle two sibling terminals anywhere in the group tree, not just
    two entries of the same flat list — so the collector must recurse into sub-groups."""
    body = {"query": {"type": "group", "logical_operator": "or", "nodes": [
        {"type": "group", "logical_operator": "and", "nodes": [
            _terminal("text", NESTED_VALUE), _terminal("text", NESTED_TYPE),
        ]},
        _terminal("text", GOOD),
    ]}}
    result = _collect_query_attributes(body)
    assert sorted(result["structure"]) == sorted([NESTED_VALUE, NESTED_TYPE, GOOD])
    assert result["chemical"] == []
    print("ok: collect_query_attributes recurses nested groups")


def test_collect_query_attributes_ignores_non_text_and_malformed():
    assert _collect_query_attributes({}) == {"structure": [], "chemical": []}
    assert _collect_query_attributes({"query": {"type": "terminal", "service": "sequence"}}) == {
        "structure": [], "chemical": [],
    }
    assert _collect_query_attributes({"query": {"type": "terminal", "service": "text"}}) == {
        "structure": [], "chemical": [],
    }  # missing parameters entirely -> skipped, not raised
    print("ok: collect_query_attributes ignores non-text and malformed nodes")


# --- nested-attribute pairing wired into the advanced (raw-body) path ------------------
def test_advanced_body_rejects_orphan_nested_attribute_anywhere_in_the_query():
    """An orphaned nested attribute must be caught even split across sibling terminals
    that rcsb_search_by_attribute's flat AttributeFilter list would never see together."""
    body = {"query": {"type": "group", "logical_operator": "and", "nodes": [
        _terminal("text", NESTED_VALUE, operator="equals"),
        _terminal("text", GOOD, operator="less"),
    ]}}
    with pytest.raises(ValueError, match="nested attribute"):
        _validate_advanced_body(body)


def test_advanced_body_accepts_nested_pair_across_sibling_terminals():
    body = {"query": {"type": "group", "logical_operator": "and", "nodes": [
        _terminal("text", NESTED_VALUE, operator="equals"),
        _terminal("text", NESTED_TYPE),
    ]}}
    _validate_advanced_body(body)  # both partners present, even in separate terminals -> no raise


# --- wiring guard: no search tool may skip validation ----------------------
def test_every_search_tool_validates_its_attributes():
    """A structural guard: each of the 9 search tools must call a validator, so a future
    tool (or a refactor) can't silently ship a path straight to the API unvalidated."""
    src = inspect.getsource(search)
    tree = ast.parse(src)
    tools = {
        "rcsb_search_fulltext", "rcsb_search_by_attribute", "rcsb_search_by_sequence",
        "rcsb_search_by_chemical", "rcsb_search_by_structure", "rcsb_search_by_seqmotif",
        "rcsb_search_strucmotif", "rcsb_search_advanced",
    }
    validators = {"_validate_query_attributes", "_validate_advanced_body"}
    seen = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name in tools:
            # A Name reference anywhere (not just as a direct Call.func) — some tools now
            # pass the validator to asyncio.to_thread(...) rather than calling it directly,
            # so it appears as an argument, not a call target.
            names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
            seen[node.name] = bool(names & validators)
    missing = sorted(t for t in tools if not seen.get(t))
    assert not missing, f"search tools that never validate their attributes: {missing}"
