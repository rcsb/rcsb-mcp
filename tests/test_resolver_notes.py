"""`_resolver_fallback_note` — what the five rcsb_find_* resolvers tell the agent about
a result that resolved but may not be usable.

The note is the zero-token half of the wrong-concept guardrail: the prompt states the rule
once, and this fires the reminder at the moment it applies, only when it applies. That makes
its silence as load-bearing as its text — a note on every rare-target query would train the
agent to skip it — so the quiet cases are tested as carefully as the loud ones.

Pure function, no network, no API key, no model.
"""

import pytest

from rcsb_mcp.resolvers import (
    _LOW_COVERAGE_MAX_ENTRIES,
    _LOW_COVERAGE_MAX_HITS,
    _resolver_fallback_note,
)


def _hits(*counts: int | None, n: int | None = None) -> list[dict]:
    """Resolver items carrying the given pdb_entry_counts (None = the count query failed)."""
    items = [{"id": f"X{i}", "pdb_entry_count": c} for i, c in enumerate(counts)]
    return items[:n] if n else items


# --- nothing resolved ---------------------------------------------------------
def test_no_hits_advises_keyword_fallback():
    note = _resolver_fallback_note([], "InterPro entry")
    assert note and "No InterPro entry matched" in note
    assert "rcsb_query_fulltext" in note


def test_all_zero_counts_advises_keyword_fallback():
    note = _resolver_fallback_note(_hits(0, 0, 0), "GO term")
    assert note and "none are annotated in the PDB" in note
    assert "rcsb_query_fulltext" in note


# --- resolved, but maybe the wrong concept ------------------------------------
def test_lone_low_coverage_hit_is_flagged():
    """The IPR010468 case: one confident hit, one PDB entry, wrong concept entirely."""
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    assert note, "a single hit covering one entry must not pass silently"
    assert "only 1 PDB entry" in note, note
    assert "NAME" in note, "the only reliable check is reading what came back"


def test_the_low_coverage_note_says_why_the_resolver_can_be_wrong():
    """The diagnosis, which is what makes the two remedies make sense.

    A resolver matches words against TERM NAMES, not against the concept — so a confident
    single hit can be a narrower or adjacent piece of what was asked for. Without that, a
    low count reads purely as "rare target" and the remedies look unmotivated.
    """
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    assert "TERM NAMES" in note and "narrower or adjacent" in note


def test_the_low_coverage_note_recommends_re_resolving():
    """The one remedy that measurement supports, on the IPR010468 case this note exists for:

        rcsb_find_interpro_domains("hormone-sensitive lipase")  IPR010468        1 entry
        rcsb_find_interpro_domains("lipase")                    IPR000734       21
        rcsb_find_interpro_domains("alpha/beta hydrolase")      IPR000073      994

    Re-resolving a broader or differently-worded term reaches a usable anchor. (An earlier
    claim that rephrasing CANNOT reach the right term was checked and is false — that is
    what these numbers are for.)
    """
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    assert "broader or differently-worded" in note


def test_the_low_coverage_note_does_not_suggest_a_full_text_cross_check():
    """A comparison whose outcome the trigger condition already determines is not a signal.

    This note fires only when the best match covers FEWER THAN _LOW_COVERAGE_MAX_ENTRIES
    entries. Any keyword matching more than a handful of structures therefore shows "far
    more" than the anchor — in the rare-but-correct case just as much as the wrong-anchor
    case. The note says a low count is expected for a rare target, so pairing it with a
    test that indicts every low count would contradict its own first sentence.

    Separately: full text does NOT come back empty here (52 entries for
    "hormone-sensitive lipase"), so the reason to leave it out is that the comparison is
    uninformative, NOT that the search finds nothing. Those were confused once already.
    """
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    assert "fulltext" not in note and "cross-check" not in note


def test_the_flag_advises_rather_than_forbids():
    """A low count is often simply correct — the note must not read as 'this is wrong'."""
    note = _resolver_fallback_note(_hits(2), "EC number")
    assert note and "expected for a rare target" in note


def test_entry_is_pluralised():
    assert "only 1 PDB entry." in _resolver_fallback_note(_hits(1), "GO term")
    assert "only 2 PDB entries." in _resolver_fallback_note(_hits(2), "GO term")


# --- the silences -------------------------------------------------------------
@pytest.mark.parametrize(
    "counts, why",
    [
        ((114, 110, 1), "a well-covered hit is a normal, usable resolution"),
        ((1,) * (_LOW_COVERAGE_MAX_HITS + 1), "several candidates means there was a choice to make"),
        ((_LOW_COVERAGE_MAX_ENTRIES,), "at the coverage threshold, not below it"),
    ],
)
def test_stays_silent(counts, why):
    assert _resolver_fallback_note(_hits(*counts), "GO term") is None, why


def test_missing_counts_say_nothing():
    """with_pdb_counts=False: no counts were requested, so there is nothing to judge."""
    assert _resolver_fallback_note([{"id": "GO:1"}, {"id": "GO:2"}], "GO term") is None


def test_failed_count_lookup_is_not_reported_as_zero():
    """None means the Search API was unreachable, NOT that the term is unannotated.

    Conflating them made the resolver claim "none are annotated in the PDB" whenever the
    count query failed — a confident false statement about the archive, produced by a
    network blip.
    """
    assert _resolver_fallback_note(_hits(None, None), "NCBI taxon") is None
    assert _resolver_fallback_note(_hits(None, 5), "NCBI taxon") is None


def test_partial_counts_do_not_trigger_the_low_coverage_flag():
    """One unknown count means the maximum is unknown, so 'best match covers N' is unprovable."""
    assert _resolver_fallback_note(_hits(1, None), "InterPro entry") is None


# --- the note reaches every resolver ------------------------------------------
def test_every_resolver_shares_this_note():
    """All five rcsb_find_* tools route through one helper, so the guardrail can't be partial."""
    import inspect

    from rcsb_mcp import resolvers

    for name in ("rcsb_find_go_terms", "rcsb_find_interpro_domains", "rcsb_find_enzyme_classes",
                 "rcsb_find_disease_terms", "rcsb_find_organisms"):
        src = inspect.getsource(getattr(resolvers, name))
        assert "_resolver_fallback_note" in src, f"{name} does not emit the resolver note"
