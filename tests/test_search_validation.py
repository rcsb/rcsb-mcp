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


# --- wiring guard: no search tool may skip validation ----------------------
def test_every_tool_that_takes_an_attribute_path_validates_it():
    """A structural guard: any tool accepting an agent-supplied attribute path must call a
    validator, so a future tool (or a refactor) can't ship a guessed path to the API.

    The tool set is DERIVED from the signatures rather than listed. A hardcoded roster only
    guards the tools someone remembered to add, and goes stale the moment tools are renamed
    — which is exactly what happened when rcsb_search_* became rcsb_query_*: the list still
    named seven tools that no longer existed, so the guard passed while checking nothing.
    """
    src = inspect.getsource(search)
    tree = ast.parse(src)
    # Parameters that carry an attribute path the agent chose, in any tool that has one.
    ATTRIBUTE_BEARING = {"attributes", "sort_by", "facets"}
    validators = {"_validate_query_attributes"}

    obliged, validates = set(), set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        if not node.name.startswith(("rcsb_query_", "rcsb_search_")):
            continue
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        if params & ATTRIBUTE_BEARING:
            obliged.add(node.name)
        calls = {c.func.id for c in ast.walk(node)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        if calls & validators:
            validates.add(node.name)

    assert obliged, "no tool takes an attribute path — the guard has lost its subject"
    missing = sorted(obliged - validates)
    assert not missing, f"tools taking an attribute path but never validating it: {missing}"


def test_an_unknown_key_in_a_filter_is_rejected_not_dropped():
    """The tool surface has TWO things called an operator, and conflating them was silent.

    `AttributeFilter.operator` is the per-condition COMPARISON (exact_match, in, less);
    `logical_operator` is the ONE boolean joining every condition, and it is a sibling of
    the `attributes` array, not a field of it. Under pydantic's default (extra="ignore") a
    caller who wrote `logical_operator` inside a filter had it dropped in silence and got
    "and" while having asked for "or" — a different answer, no error, nothing to notice.

    The docstring used to warn ("They all share this one operator"). Prose is the wrong
    guard for this: the schema already says where the field lives, and a caller who
    misreads prose will misread that too. Rejecting the key is what actually stops it.
    """
    import pytest as _pytest
    from pydantic import ValidationError

    from rcsb_mcp.search import AttributeFilter

    with _pytest.raises(ValidationError) as exc:
        AttributeFilter.model_validate({
            "attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
            "operator": "exact_match", "value": "Homo sapiens",
            "logical_operator": "or",
        })
    assert "logical_operator" in str(exc.value), "the error must name the offending field"


def test_every_documented_filter_field_still_validates():
    """extra="forbid" must not reject the legitimate surface."""
    from rcsb_mcp.search import AttributeFilter

    f = AttributeFilter.model_validate({
        "attribute": "exptl.method", "operator": "exact_match",
        "value": "X-RAY DIFFRACTION", "negation": True, "case_sensitive": True,
    })
    assert f.negation and f.case_sensitive
    assert AttributeFilter.model_validate(
        {"attribute": "rcsb_nonpolymer_entity.pdbx_description", "operator": "exists"}
    ).value is None


def test_grouped_paging_terminates():
    """With group_by, total_count stays UNGROUPED and paging against it never ends.

    The API reports two numbers for a grouped search: `total_count` is the raw hit count
    and `group_by_count` is how many groups those collapse into — 2,092 SH2-domain
    entities become 159 UniProt groups. Paging against 2,092 produced:

        offset  returned  has_more  next_offset
           150         9      True          159
           200         0      True          200      <- 0 hits, "more", same offset

    An agent following the documented offset/next_offset protocol loops on 200 forever.
    Paging must use the group count when there is one.
    """
    from rcsb_mcp.search import _format

    raw = {"result_set": [], "total_count": 2092, "group_by_count": 159}
    out = _format(raw, {"return_type": "polymer_entity"}, offset=200)
    assert out["group_count"] == 159
    assert out["has_more"] is False, "past the last group there is nothing more"
    assert out["next_offset"] is None

    partial = {"result_set": [{"identifier": f"X_{i}"} for i in range(9)],
               "total_count": 2092, "group_by_count": 159}
    mid = _format(partial, {"return_type": "polymer_entity"}, offset=150)
    assert mid["has_more"] is False, "150 + 9 == 159 groups: the last page"


def test_total_count_still_reports_ungrouped_hits():
    """`group_count` is added, not substituted: how many entities carry the annotation is
    a different question from how many distinct proteins they represent, and callers
    reporting coverage need the first."""
    from rcsb_mcp.search import _format

    out = _format({"result_set": [], "total_count": 2092, "group_by_count": 159},
                  {"return_type": "polymer_entity"}, offset=0)
    assert out["total_count"] == 2092 and out["group_count"] == 159


def test_an_ungrouped_search_gains_no_group_count():
    """Silence when it does not apply — the field marks that grouping happened."""
    from rcsb_mcp.search import _format

    out = _format({"result_set": [], "total_count": 42}, {"return_type": "entry"}, offset=0)
    assert "group_count" not in out
