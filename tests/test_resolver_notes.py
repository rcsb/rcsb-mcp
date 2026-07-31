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


def test_the_low_coverage_note_explains_why_rephrasing_will_not_help():
    """The one thing this note knows that the caller does not.

    A resolver matches words against term names, so the term you want can share no
    vocabulary with your query — and then no amount of rewording reaches it. Without that,
    the natural response to "this looks wrong" is to try another phrasing, which is the one
    move guaranteed to fail.
    """
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    assert "rephrasing will not reach it" in note


def test_the_low_coverage_note_recommends_no_specific_recovery():
    """Deliberately diagnostic only — it must not name a remedy it cannot stand behind.

    Two were considered and dropped on measurement. Keyword search: rcsb_query_fulltext
    returns nothing for a concept whose name is not in any entry's text, which is exactly
    the case that trips this note. Climbing to a broader id: only 12% of InterPro
    annotations have ANY ancestor, and IPR010468 — the case this note exists for — has
    none, so the advice would fail on its own motivating example.

    A remedy belongs here once the resolver can hand back a broader id and its coverage as
    DATA rather than as instructions. Until then this states the diagnosis and stops.
    """
    note = _resolver_fallback_note(_hits(1), "InterPro entry")
    for remedy in ("rcsb_query_fulltext", "broaden", "lineage"):
        assert remedy not in note, (
            f"the low-coverage note recommends {remedy!r}; both remedies were measured and "
            "fail on the case that triggers it"
        )


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
