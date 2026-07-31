"""The query bodies the composer produces must match what the flat builders produced.

`tests/fixtures/query_bodies_baseline.json` was generated from those builders BEFORE the
refactor and COMMITTED. The builders are gone now; the fixture is what outlived them, and
it is the only remaining record of how these queries were shaped when the flat tools were
the ones shipping. Every case is rendered through the composer pipeline -- rcsb_query_* ->
rcsb_query_composer -> rcsb_search_request -- and must come out byte-identical.

This is the substitute for the tool-selection A/B that can't be run. It cannot tell us
whether a model routes to the right tool -- nothing offline can -- but it removes
"does the refactor still build the same query?" from the list of open questions, so the
only thing left to judge in the wild is routing.
"""

from __future__ import annotations

import json

import pytest

from query_cases import CASES, body_via_pipeline, load_baseline

# name -> callable(case) -> body. Only the composer pipeline remains; the flat
# build_*_query adapter went with the builders it drove.
ADAPTERS = {"pipeline": body_via_pipeline}

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


def test_the_fixture_records_only_shapes_that_predate_the_refactor():
    """No case may use a shape the flat builders could not build.

    The fixture's authority comes entirely from having been generated BEFORE the composer
    existed. A nested group or a two-service query has no pre-refactor body to record, so
    adding one here would produce an entry blessed by nothing but the code it is meant to
    check -- the fixture would silently start agreeing with whatever the tree does.

    Those shapes are real capability and are tested against the Search API contract in
    test_query_compose.py and test_query_tools.py; they just cannot live in this record.
    """
    def offenders(query, depth=0):
        if query["kind"] != "group":
            return
        if depth:
            yield "a nested group"
        services = [n for n in query["nodes"] if n["kind"] != "attribute"]
        if len(services) > 1:
            yield f"{len(services)} service nodes in one group"
        for child in query["nodes"]:
            yield from offenders(child, depth + 1)

    bad = {c["name"]: list(offenders(c["query"])) for c in CASES}
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, (
        "these cases use shapes the pre-composer builders could not express, so the "
        f"fixture cannot be a record of prior behaviour for them: {bad}"
    )
