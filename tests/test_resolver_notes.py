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
def test_no_hits_explains_the_failure_and_offers_both_remedies():
    """An empty resolver result is the branch where the caller has least to go on, so it
    says WHY before what to do — the words matched no term's indexed text, which is a
    different failure from "the archive has none of this".

    Re-resolving comes BEFORE the keyword fallback: every rcsb_query_* description prefers
    an ontology anchor over a name match, so the note should not send the caller to
    keywords first.
    """
    note = _resolver_fallback_note([], "InterPro entry")
    assert note and "No InterPro entry matched" in note
    assert "TERM NAMES" in note, "the note must say why nothing matched"
    assert "rcsb_query_fulltext" in note
    assert note.index("differently-worded") < note.index("rcsb_query_fulltext"), (
        "re-resolving is the preferred remedy and must be offered first"
    )


def test_the_empty_note_does_not_call_it_an_intersection():
    """Nothing is intersected when a resolver returns nothing — the words matched no term.

    It also would not generalise. This note is shared by five resolvers over four backends,
    and only UniProt taxonomy ANDs the query terms ("human coli" -> 0 while each word alone
    returns hits); interpro7, QuickGO and OLS4 all still return partial matches. And
    "intersection" already means conditions ANDed at a return_type level elsewhere on this
    server, which is a collision worth avoiding.
    """
    note = _resolver_fallback_note([], "GO term")
    assert "intersection" not in note.lower()


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
    # The INVARIANT is that re-resolving is offered as the remedy — not the adjectives used
    # to describe the replacement term. An earlier version asserted the literal phrase
    # "broader or differently-worded" and broke the moment "synonym" was added to it, which
    # is a better note failing a worse test.
    assert "resolve a" in note and "term for the same concept" in note


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


# --- the notes are assembled from adjacent string literals ----------------------
def test_no_note_fragment_joins_without_a_separator():
    """Implicit concatenation silently drops spaces, and no assertion here catches it.

    A real one shipped: `"...differently-worded term for"` followed by `"the same concept."`
    rendered as "term forthe same concept", with all 15 tests green. Content assertions are
    blind to it because every substring they look for is still present.

    So this checks the SEAMS rather than the text: for each pair of adjacent string literals,
    the first must not end alphanumeric while the second begins alphanumeric. That is the
    whole bug class, and it survives rewording — unlike an assertion on a phrase, which
    freezes prose nobody agreed to freeze.

    Uses `tokenize`, NOT `ast`: CPython folds adjacent constants during parsing, so by the
    time there is a tree the seam is gone. The first version of this test walked the AST,
    passed, and was proved blind by the mutation below before being trusted.
    """
    import io
    import tokenize
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "rcsb_mcp" / "resolvers.py"
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src.read_text()).readline)
            if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT,
                              tokenize.INDENT, tokenize.DEDENT)]
    seams = 0
    for left, right in zip(toks, toks[1:]):
        if left.type != tokenize.STRING or right.type != tokenize.STRING:
            continue
        # Strip prefix/quotes to get at the actual first and last characters.
        lv = left.string.rstrip().rstrip('"\'')
        rv = right.string.lstrip()
        rv = rv[1:] if rv[:1] in ('"', "'") else rv[2:]
        if not lv or not rv:
            continue
        seams += 1
        assert not (lv[-1].isalnum() and rv[0].isalnum()), (
            f"line {left.start[0]}: missing separator between "
            f"{lv[-30:]!r} and {rv[:30]!r}"
        )
    assert seams >= 5, f"only {seams} literal seams found — the tokenizer assumption is stale"


# --- rank/coverage inversion ----------------------------------------------------
def _ranked(*counts, id_key="id"):
    return [{id_key: f"ID{i}", "pdb_entry_count": c} for i, c in enumerate(counts)]


def test_an_inversion_names_both_ids_and_both_counts():
    """The case that looked healthy and was not.

    Rank is NAME similarity; coverage is unrelated. So the top hit is regularly not the
    best anchor, and unlike the zero-count and low-coverage notes nothing about the result
    looks wrong while it happens:

        rcsb_find_organisms("yeast")   rank 1: 32655, 0 entries — a PLASMID
                                       best:   559292, 2,933   — S. cerevisiae

    Naming both is the whole value. "The larger one may be broader" leaves the caller to
    notice their top hit is a plasmid; the ids hand them the comparison.
    """
    note = _resolver_fallback_note(_ranked(0, 2933), "NCBI taxon")
    assert note and "ID0" in note and "ID1" in note and "2933" in note


def test_the_note_does_not_claim_the_larger_hit_is_broader():
    """The trigger CANNOT tell a broader relative from a name collision, and both occur:

        interpro("hormone-sensitive lipase")  IPR010468 (1) < IPR033140 (49)  RELATED
        enzyme_classes(same words)            3.1.1.79  (2) < 2.7.11.31 (47)  UNRELATED

    Nothing in either response distinguishes them, so advising a move would be wrong about
    half the time. The note states the observation and hands the judgement back.
    """
    note = _resolver_fallback_note(_ranked(2, 47), "EC number")
    assert "may be" in note and "name collision" in note
    assert "use " not in note.lower(), "it must not instruct a switch it cannot justify"


@pytest.mark.parametrize(
    "counts, why",
    [
        ((2121, 2056, 30), "the top hit IS the best covered — nothing to report"),
        ((2056, 2121), "1.03x: SH2 domain. The top hit is already a fine anchor"),
        ((771, 778), "1.01x: ferredoxin"),
        ((994, 3295), "3.3x: alpha beta hydrolase — 994 is a perfectly usable anchor"),
        ((1, 12), "12x but the alternative is below the floor: a rare target, not an inversion"),
        ((500,), "a single well-covered hit: nothing to invert against"),
    ],
)
def test_the_thresholds_keep_it_quiet(counts, why):
    """BOTH thresholds are load-bearing — measured over 30 queries, not assumed.

    Ratio + floor fires on 30%. Dropping the ratio takes it to 47% by adding exactly the
    first four cases here. Dropping the floor would fire on rare targets where every count
    is small and a large ratio is an artefact of small numbers.
    """
    assert _resolver_fallback_note(_ranked(*counts), "GO term") is None, why


def test_a_zero_top_hit_does_not_divide_by_zero():
    """counts[0] == 0 is among the most worth reporting, so the test is a multiplication."""
    assert _resolver_fallback_note(_ranked(0, 40), "GO term") is not None


@pytest.mark.parametrize("id_key", ["id", "ec", "tax_id"])
def test_the_id_field_differs_per_resolver(id_key):
    """EC returns `ec`, organisms `tax_id`, the other three `id` — and naming the
    alternative is most of the note's value, so the accessor is not optional."""
    note = _resolver_fallback_note(_ranked(1, 99, id_key=id_key), "term", id_key)
    assert "ID1" in note and "None" not in note


def test_the_three_notes_cannot_fire_together():
    """No ordering rule is needed: the triggers are disjoint by construction.

    zero-counts needs max == 0; low-coverage needs max < 10; inversion needs max >= 25.
    """
    assert "none are annotated" in _resolver_fallback_note(_ranked(0, 0), "GO term")
    assert "covers only" in _resolver_fallback_note(_ranked(1), "GO term")
    assert "Ranked first" in _resolver_fallback_note(_ranked(1, 99), "GO term")
