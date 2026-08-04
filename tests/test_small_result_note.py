"""`queries.small_result_note` — a thin answer from a query that matched on WORDING.

This came from a real miss. A full-text search for "PSII-FCPII supercomplex" returns 11
entries, which reads like a complete answer; the archive holds more, deposited as
"PSII-FCP". The recovery — harvest the annotations the hits share, re-search on those —
lives in the optional rcsb_search_assistant prompt, so a client that never loads it has
nothing telling it the count might be a vocabulary artefact rather than a fact about the
archive. Tool responses always arrive; prompts do not.

Scoped to FULL TEXT deliberately. For an annotation-id or entry-id filter a small count is
almost always simply correct, and firing there would put a note on every narrow lookup —
the failure mode that trains callers to skip notes entirely.

Pure function, no network.
"""

import pytest

from rcsb_mcp import queries
from rcsb_mcp.queries import _SMALL_RESULT_MAX, small_result_note


def _attr(path, operator="exact_match", value="x"):
    return queries.attribute_node([{"attribute": path, "operator": operator, "value": value}], "and")


FULLTEXT = queries.fulltext_node("PSII-FCPII supercomplex")


# --- fires where recall depends on wording --------------------------------------
@pytest.mark.parametrize("count", [1, 2, 11, _SMALL_RESULT_MAX - 1])
def test_a_thin_full_text_answer_is_flagged(count):
    note = small_result_note(FULLTEXT, count)
    assert note and f"total_count is {count}" in note


def test_the_threshold_covers_the_case_that_prompted_the_note():
    """Pins the DECISION, not the number, so tuning does not churn the test — but lowering
    it past the motivating case fails here and says what was given up.

    Measured over 28 realistic full-text queries spanning 2..40,751 hits:

        < 5    fires on  7%
        < 10   fires on  7%   (nothing in the sample lands between 5 and 9)
        < 20   fires on 11%   -- and catches "PSII-FCPII supercomplex" at 11

    That last case is the one this note exists for: 11 hits reads like a complete answer,
    while the archive also holds entries deposited as "PSII-FCP". Anything below 12 is
    silent on it.
    """
    assert small_result_note(FULLTEXT, 11) is not None, (
        f"_SMALL_RESULT_MAX={_SMALL_RESULT_MAX} is silent on the 11-hit PSII-FCPII case "
        "this note was written for — deliberate, or an accident?"
    )
    assert small_result_note(FULLTEXT, _SMALL_RESULT_MAX) is None


@pytest.mark.parametrize("count", [_SMALL_RESULT_MAX, 47, 9079])
def test_an_ordinary_answer_says_nothing(count):
    assert small_result_note(FULLTEXT, count) is None


# --- silent where wording is not the risk ----------------------------------------
@pytest.mark.parametrize(
    "node, why",
    [
        (_attr("rcsb_entry_container_identifiers.entry_id"), "an id lookup returning 1 is correct"),
        (_attr("rcsb_polymer_entity_annotation.annotation_id", value="IPR000073"),
         "an annotation anchor is not vocabulary-dependent; a wrong anchor is the resolver's problem"),
        (_attr("rcsb_entry_info.resolution_combined", "less", 2.0), "a numeric filter has no synonyms"),
        (queries.sequence_node("MVLSPADKTNVKAAW", "protein", 0.9, 0.9),
         "for sequence search the remedy is the identity threshold, not a synonym"),
    ],
)
def test_non_wording_queries_are_left_alone(node, why):
    assert small_result_note(node, 1) is None, why


def test_a_composed_query_containing_full_text_still_fires():
    """Full text ANDed with a filter is still wording-dependent for the text half."""
    composed = queries.group_node([FULLTEXT, _attr("exptl.method", value="X-RAY DIFFRACTION")], "and")
    assert small_result_note(composed, 3) is not None


# --- what the note says -----------------------------------------------------------
def test_the_zero_case_does_not_tell_the_caller_to_mine_hits_it_does_not_have():
    """Shipped wrong once: at 0 the general note said "fetch these hits and re-search on any
    value they share", which is impossible when there are none — and hedged with "that is
    often simply the answer", which is the wrong reassurance for nothing at all.

    Zero also has fewer routes. Harvesting shared values needs hits; synonyms and an
    ontology anchor are what remain, and both work from an empty result.
    """
    note = small_result_note(FULLTEXT, 0)
    assert "total_count is 0" in note and "an empty result" in note
    assert "these hits" not in note and "they share" not in note
    assert "often simply the answer" not in note
    assert "rcsb_query_fulltext" in note and "rcsb_find_*" in note


def test_a_thin_answer_offers_the_route_that_needs_hits():
    """The reverse: above zero there ARE hits, so harvesting their shared values is the
    route the other two cannot replace — it reaches entries no synonym would guess."""
    note = small_result_note(FULLTEXT, 11)
    assert "rcsb_get_*" in note and "any value they share" in note


def test_every_route_names_the_tool_that_performs_it():
    """The synonym route once read "try other names or abbreviations for the same thing" —
    the only one of the three naming no tool, sitting between two that did. It scanned as a
    vague aside rather than an action, to the point of reading as absent.

    Whatever the routes are, each must name what to call. Both branches, since the zero and
    thin texts are separate strings and drifted apart once already.
    """
    for count in (0, 11):
        note = small_result_note(FULLTEXT, count)
        assert "rcsb_query_fulltext" in note, f"synonym route names no tool at {count}"
        assert "rcsb_find_*" in note, f"ontology route names no tool at {count}"


def test_it_offers_all_recovery_routes_and_hedges():
    """A thin answer is usually just the answer, so it advises rather than warns — and the
    two routes are RECALL moves, not a precision check.

    Verifying the hits you got are correct says nothing about entries you missed; the value
    of rcsb_get_* here is the annotations the hits CARRY, which are re-searchable and reach
    entries the wording never would.
    """
    note = small_result_note(FULLTEXT, 5)
    assert "often simply the answer" in note
    assert "rcsb_get_*" in note and "rcsb_find_*" in note
    assert "any value they share" in note
    # Synonym expansion: the only route that survives a zero result, and the last piece of
    # the assistant prompt's recall-probe block that no tool channel carried.
    assert "rcsb_query_fulltext" in note and "synonyms" in note


def test_it_does_not_name_a_fixed_set_of_annotation_types():
    """An earlier draft listed UniProt/InterPro/Pfam/GO/EC, which reads as exhaustive.

    It is not: gene name, struct_keywords, pdbx_description and organism are all shared
    values worth re-searching on, and often better ones. A list in a note also cannot track
    the attribute catalog, which is generated.
    """
    note = small_result_note(FULLTEXT, 5)
    for name in ("UniProt", "InterPro", "Pfam", "GO/EC"):
        assert name not in note


def test_it_does_not_tell_the_caller_to_distrust_results_as_policy():
    """"Always treat the first result as a probe" is the CLIENT's stance to take — a
    precision-critical caller may want the opposite. The server supplies the count and the
    routes; rcsb_search_assistant keeps the policy."""
    note = small_result_note(FULLTEXT, 5)
    for banned in ("always", "never", "do not trust", "distrust"):
        assert banned not in note.lower()


def test_the_count_is_the_ARCHIVE_count_not_the_page_the_caller_gets():
    """Grouping must not change which number this note reads. Got this wrong once.

    With group_by on, a response carries both counts — "hormone-sensitive lipase" is 60
    entities in 17 UniProt groups — and 17 is what the caller pages. That made group_count
    look like "the answer size", so the note was rewired to read it, and 17 is under the
    threshold where 60 is not: a search that found 60 entities started warning that the
    archive might word the concept differently.

    It does not, because this note is about RECALL — did the wording miss things? — and
    grouping is a post-hoc collapse of what was already found. It cannot cost recall. The
    60 is the evidence the wording worked; the 17 is a display choice.
    """
    fired_on_the_archive_count = small_result_note(FULLTEXT, 60)
    fired_on_the_group_count = small_result_note(FULLTEXT, 17)
    assert fired_on_the_archive_count is None
    assert fired_on_the_group_count is not None
    # So the wiring must hand it total_count, whichever is smaller.
    import inspect

    from rcsb_mcp import search

    assert 'small_result_note(node, result.get("total_count", 0))' in inspect.getsource(
        search.rcsb_search_request
    ), "grouping does not affect recall, so the note reads total_count either way"
