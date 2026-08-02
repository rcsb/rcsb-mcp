"""`rcsb_find_interpro_domains` builds a safe, usable EBI Search query.

The resolver moved off the InterPro REST API onto EBI Search's `interpro7` index, which
searches `short_name` and `description` as well as entry names. That fixed a real recall
hole — all three of these returned NOTHING from the REST API:

    "alpha beta hydrolase"                 -> IPR000073, 994 PDB entries
    "alpha/beta hydrolase fold-3 domain"   -> IPR013094, 114
    "Abhydrolase_3"                        -> PF07859,    68   (a Pfam short name)

The first is the one that stings: dropping a single slash from a phrase that otherwise
works took the caller from a 994-entry anchor to none.

But the new index is a Lucene endpoint spanning 14 member databases, and both of those
facts are traps. These tests pin the two guards that make it safe. Query construction only
— no network.
"""

import pytest

from rcsb_mcp.resolvers import (
    INTERPRO_SEARCH_URL,
    INTERPRO_SOURCE_DATABASES,
    INTERPRO_SUBDOMAIN_TYPES,
    INTERPRO_TYPES,
    _escape_lucene,
)


# --- trap 1: the caller's text is parsed as query syntax ------------------------
@pytest.mark.parametrize(
    "text, why",
    [
        ("alpha/beta hydrolase", "HTTP 400 unescaped — and it is a completely ordinary phrase"),
        ("serine/threonine kinase", "same"),
        ("kinase: activity", "WORSE: the colon parses as a field qualifier, so it returns "
                             "0 hits with no error at all"),
        ("p53 (tumor)", "parentheses group"),
        ("C2H2-type", "a leading hyphen is NOT syntax, but the character still needs escaping"),
    ],
)
def test_caller_text_is_escaped_before_it_reaches_the_query(text, why):
    escaped = _escape_lucene(text)
    assert escaped != text, why
    for ch in '+-!(){}[]^"~*?:\\/':
        # every occurrence of a special char must be preceded by a backslash
        for i, c in enumerate(escaped):
            if c == ch and ch != "\\":
                assert i and escaped[i - 1] == "\\", f"unescaped {ch!r} in {escaped!r}"


def test_escaping_leaves_ordinary_text_alone():
    """Escaping must not mangle the common case, or every query pays for the rare one."""
    for text in ("SH2 domain", "immunoglobulin", "zinc finger", "Abhydrolase_3"):
        assert _escape_lucene(text) == text


# --- trap 2: 12 of the 14 member databases are unusable downstream ---------------
def test_only_rcsb_ingestible_id_spaces_are_requested():
    """The index is broader than RCSB, and the extra breadth filters to nothing.

    Measured against rcsb_polymer_entity_annotation.annotation_id:

        IPR000073 -> 994   PF00151 -> 12
        cd08367 (CDD), PTHR11352 (PANTHER), SM00220 (SMART), PS50011 (PROSITE),
        NF033838 (NCBIFAM), G3DSA:3.40.50.1820 (CATHGENE3D)  -> 0 each

    SM00220 is the serine/threonine kinase catalytic domain, so its zero is not a rare
    domain — that id space simply is not in the archive. Unrestricted, the top hit for
    "kinase" and for "p53 tumor suppressor" is a CDD accession, which would resolve
    confidently and then filter to nothing.
    """
    assert set(INTERPRO_SOURCE_DATABASES) == {"INTERPRO", "PFAM"}


def test_pfam_is_deliberately_included_not_an_accident():
    """Pfam is a genuine addition, not collateral: RCSB ingests it, so PF ids filter.

    It is also what makes "Abhydrolase_3" resolvable at all — that is a Pfam short name
    with no InterPro equivalent by that spelling.
    """
    assert "PFAM" in INTERPRO_SOURCE_DATABASES


# --- the type vocabulary ---------------------------------------------------------
@pytest.mark.parametrize("alias, expected", sorted(INTERPRO_TYPES.items()))
def test_every_accepted_entry_type_maps_to_the_field_vocabulary(alias, expected):
    """The `type` FIELD uses underscores; the subdomain ids use hyphens.

    `type:active-site` returns 0 hits rather than an error, so a hyphenated value would be
    an invisible always-empty filter. Nothing here may map to a hyphenated form.
    """
    assert "-" not in expected, f"{alias!r} maps to {expected!r}, which the field will not match"
    assert expected in set(INTERPRO_TYPES.values())


def test_the_three_newly_reachable_types_are_offered():
    """coiled_coil, disordered and region are indexed but the REST API did not expose them."""
    assert {"coiled_coil", "disordered", "region"} <= set(INTERPRO_TYPES.values())


def test_the_superfamily_alias_survived_the_migration():
    assert INTERPRO_TYPES["superfamily"] == "homologous_superfamily"


# --- the endpoint ----------------------------------------------------------------
def test_the_resolver_points_at_ebi_search():
    """Same API family as the EC resolver (ebisearch/ws/rest/intenz), not the InterPro REST
    API — which is what the `query`/`fields`/`size` parameter names in the caller assume."""
    assert INTERPRO_SEARCH_URL == "https://www.ebi.ac.uk/ebisearch/ws/rest/interpro7"
    assert "interpro/api" not in INTERPRO_SEARCH_URL


# --- the reference that must NOT be followed -------------------------------------
def test_the_constraint_goes_in_a_parameter_the_api_actually_reads():
    """EBI Search ignores unrecognised parameters SILENTLY, so a wrong name is invisible.

    Two references exist and they disagree on names. The OpenAPI spec
    (…/ws/rest/openapi.json) documents `filter`; the WADL (…/ws/rest?_wadl) documents
    `filterQueries`. Only `filter` is live. Measured on query=kinase:

        no restriction        8,136 hits  CDD, INTERPRO, PANTHER, PFAM
        filter=…PFAM            761 hits  PFAM only                     <- honoured
        filterQueries=…PFAM   8,136 hits  unchanged                     <- ignored
        <made-up name>=…      8,136 hits  unchanged                     <- identical

    So following the WADL would have left INTERPRO_SOURCE_DATABASES doing nothing, and the
    resolver would have returned CDD and PANTHER accessions that filter to zero PDB entries
    downstream — with no error anywhere to notice.

    This pins the parameter NAME. It cannot verify the API still honours it (that needs the
    network); what it prevents is someone "fixing" the code to match the WADL.
    """
    import inspect

    from rcsb_mcp import resolvers

    src = inspect.getsource(resolvers.rcsb_find_interpro_domains)
    assert '"filter"' in src, "the non-scoring constraint must use the OpenAPI name"
    assert "filterQueries" not in src, "that WADL name is silently ignored by the live API"


def test_every_published_type_is_offered_and_no_invented_ones():
    """The type list is traceable to the published subdomains, not to what a sample returned.

    https://www.ebi.ac.uk/ebisearch/ws/rest/domains/ lists interpro7's subdomains, one per
    entry type. INTERPRO_SUBDOMAIN_TYPES records that list verbatim; this asserts the
    resolver offers exactly it, so a type added upstream shows up as a failure here rather
    than as a capability nobody noticed was missing.

    The normalisation is the point: subdomain ids are hyphenated, the `type` field is
    underscored, and `type:active-site` returns 0 hits instead of an error.
    """
    published = {t.replace("-", "_") for t in INTERPRO_SUBDOMAIN_TYPES}
    offered = set(INTERPRO_TYPES.values())
    assert offered == published, (
        f"missing: {sorted(published - offered)}   invented: {sorted(offered - published)}"
    )
    assert len(INTERPRO_SUBDOMAIN_TYPES) == 11


def test_the_hyphenated_forms_are_never_used_as_filter_values():
    """Three of the eleven differ between the two vocabularies; only those can go wrong."""
    hyphenated = {t for t in INTERPRO_SUBDOMAIN_TYPES if "-" in t}
    assert hyphenated == {"active-site", "binding-site", "conserved-site"}
    assert not hyphenated & set(INTERPRO_TYPES.values())


def test_the_docstring_offers_a_way_to_broaden():
    """InterPro has no lineage, so `in` is the ONLY way to broaden — and it was the one
    resolver of five not saying so.

    The other four attach "use `in` with several ids to broaden" to their hierarchical
    *_lineage.id sentence. InterPro has no lineage paths, so it lost that sentence and the
    `in` hint with it — leaving the resolver where broadening matters MOST as the only one
    that never mentions how. Verified against the live API:

        IPR000073 alone                994
        IPR029058 alone              3,295
        in [both]                    3,295   (union)
        in [IPR000073, PF07859]      1,062   (id spaces mix)

    Asserted as behaviour, not phrasing: the docstring must name `in`, because the tool
    returns a LIST of candidates and exact_match uses exactly one of them.
    """
    from rcsb_mcp.resolvers import rcsb_find_interpro_domains

    doc = rcsb_find_interpro_domains.__doc__
    assert "`in`" in doc, "the only broadening route must be named"
    assert "exact_match" in doc, "the single-id route stays documented too"
