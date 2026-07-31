"""The query bodies must not change when the search tools are rewritten as composers.

`tests/fixtures/query_bodies_baseline.json` was generated from the builders at HEAD and
is COMMITTED, so it keeps asserting pre-refactor behaviour after they are replaced. Each
adapter in ADAPTERS renders the same declarative cases a different way and must produce
byte-identical bodies:

    current   queries.build_*_query(...)                        (today)
    pipeline  rcsb_query_* -> rcsb_query_composer -> request    (added with the refactor)

This is the substitute for the tool-selection A/B that can't be run. It cannot tell us
whether a model routes to the right tool -- nothing offline can -- but it removes
"does the refactor still build the same query?" from the list of open questions, so the
only thing left to judge in the wild is routing.
"""

from __future__ import annotations

import json

import pytest

from query_cases import CASES, body_via_current, body_via_pipeline, load_baseline

# name -> callable(case) -> body.
ADAPTERS = {"current": body_via_current, "pipeline": body_via_pipeline}

BASELINE = load_baseline()
IDS = [c["name"] for c in CASES]


@pytest.mark.parametrize("adapter", list(ADAPTERS))
@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_body_matches_baseline(case, adapter):
    """Byte-identical, compared as canonical JSON so key order can't mask a difference."""
    got = ADAPTERS[adapter](case)
    want = BASELINE[case["name"]]
    assert json.dumps(got, sort_keys=True) == json.dumps(want, sort_keys=True), (
        f"{adapter} adapter changed the query body for {case['name']!r}.\n"
        f"got:  {json.dumps(got, sort_keys=True)}\n"
        f"want: {json.dumps(want, sort_keys=True)}"
    )


def test_fixture_and_cases_are_in_sync():
    """A dropped case must fail loudly, not shrink the guard in silence."""
    assert set(BASELINE) == set(IDS), (
        f"only in fixture: {sorted(set(BASELINE) - set(IDS))}; "
        f"only in cases: {sorted(set(IDS) - set(BASELINE))}. "
        "Regenerate with `python tests/query_cases.py` ONLY if the change is intended."
    )


def test_every_search_service_is_covered():
    """The fixture is worthless if it stops exercising a service the refactor touches."""
    def kinds(q):
        if q["kind"] == "group":
            for n in q["nodes"]:
                yield from kinds(n)
        else:
            yield q["kind"]

    seen = {k for c in CASES for k in kinds(c["query"])}
    assert seen == {"fulltext", "attribute", "sequence", "chemical",
                    "structure", "seqmotif", "strucmotif"}, f"services covered: {sorted(seen)}"


def test_every_envelope_parameter_is_covered():
    """Each result-shaping parameter moving to rcsb_search_request needs a case."""
    exercised = {k for c in CASES for k in c["config"]}
    required = {"return_type", "limit", "offset", "all_hits", "include_computed_models",
                "sort_by", "sort_direction", "group_by", "group_by_ranking", "facets"}
    assert not (required - exercised), f"envelope params with no case: {sorted(required - exercised)}"


def test_baseline_bodies_carry_the_details_a_rewrite_would_drop():
    """Spot-pin three things that are easy to lose and invisible in a summary diff."""
    # The sequence service sets its own scoring strategy; nothing else does.
    assert BASELINE["sequence-protein-defaults"]["request_options"]["scoring_strategy"] == "sequence"
    # A single-condition query collapses to a bare terminal -- no wrapping group.
    assert BASELINE["attribute-single-numeric"]["query"]["type"] == "terminal"
    # all_hits drops pagination entirely rather than sending a large `rows`.
    opts = BASELINE["config-all-hits"]["request_options"]
    assert opts.get("return_all_hits") is True and "paginate" not in opts


def test_numeric_strings_are_coerced_but_dates_are_not():
    """Coercion is driven by the attribute's declared type, not the operator."""
    num = BASELINE["attribute-numeric-string-coercion"]["query"]["parameters"]["value"]
    assert num == 2.0 and isinstance(num, float), "numeric string must become a number"
    date = BASELINE["attribute-date"]["query"]["parameters"]["value"]
    assert date == "2024-01-01T00:00:00Z", "an ISO date must stay a string"


def test_baseline_rejects_queries_it_cannot_express():
    """Nested groups are new capability -- they must not slip into the baseline unnoticed."""
    from query_cases import _flatten

    nested = {"kind": "group", "logical_operator": "and", "nodes": [
        {"kind": "group", "logical_operator": "or", "nodes": [
            {"kind": "attribute", "attributes": []}]},
        {"kind": "attribute", "attributes": []},
    ]}
    with pytest.raises(ValueError, match="nested group is not expressible"):
        _flatten(nested)

    # Two service nodes -- a cross-service AND -- is the other new shape.
    with pytest.raises(ValueError, match="not expressible by the current builders"):
        _flatten({"kind": "group", "logical_operator": "and", "nodes": [
            {"kind": "sequence", "sequence": "MVL"},
            {"kind": "structure", "entry_id": "4HHB"},
        ]})
