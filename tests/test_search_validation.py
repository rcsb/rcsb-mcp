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

from rcsb_mcp import search
from rcsb_mcp.search import (
    AttributeFilter,
    _check_attribute,
    _check_operator,
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
    """The metadata schema omits `in` from numeric/date operator lists, but the live
    Search API accepts a list match there — validation must not false-reject it."""
    for path in ("rcsb_entry_info.resolution_combined", "rcsb_entry_info.deposited_polymer_monomer_count"):
        rec = _check_attribute(path, "structure")
        assert "in" not in rec["operators"], "precondition: catalog omits `in` for this numeric attr"
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
            calls = {c.func.id for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            seen[node.name] = bool(calls & validators)
    missing = sorted(t for t in tools if not seen.get(t))
    assert not missing, f"search tools that never validate their attributes: {missing}"
