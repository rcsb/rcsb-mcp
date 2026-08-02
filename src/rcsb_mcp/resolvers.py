"""Ontology / identifier resolvers: free text -> a typed annotation id (GO, InterPro,
EC, MONDO, NCBI taxon), so a search can anchor on a shared annotation rather than a
depositor's wording.

These are the only tools that do NOT call an RCSB API — they query external EBI and
UniProt web services (via rcsb_mcp.client._get_json) and, best-effort, count how many
PDB entries carry each hit (via a Search count query). Self-contained: their EBI
endpoint constants, the typed aliases, and the two private helpers all live here.

The tool functions are module-level (so they stay directly unit-testable); a FastMCP
server attaches them with register_resolver_tools(mcp), the register-onto-mcp pattern.
This module imports nothing back from server.
"""

from __future__ import annotations

import asyncio
import re
from typing import Annotated, Any, Literal

import httpx
from pydantic import Field

from rcsb_mcp import queries
from rcsb_mcp.client import _get_json, _post_search
from rcsb_mcp.tooling import READ_ONLY


ResolverLimit = Annotated[int, Field(ge=1, le=25)]

# Gene Ontology resolver (EBI QuickGO) + friendly aspect/namespace aliases.
QUICKGO_SEARCH_URL = "https://www.ebi.ac.uk/QuickGO/services/ontology/go/search"
GO_ASPECTS = {
    "molecular_function": "molecular_function", "function": "molecular_function", "mf": "molecular_function",
    "biological_process": "biological_process", "process": "biological_process", "bp": "biological_process",
    "cellular_component": "cellular_component", "component": "cellular_component",
    "location": "cellular_component", "cc": "cellular_component",
}
# Accepted `namespace` values, derived from the KEYS of the alias map above — every spelling the
# resolver accepts, including the short mf/bp/cc forms the prose never documented. Typing it (vs
# a bare str) ships the enum in the tool schema, so the caller picks from the list and the two
# can never drift. The body still normalizes (strip/lower/alias) for direct Python callers.
GoNamespace = Literal[tuple(sorted(GO_ASPECTS))]  # type: ignore[valid-type]

# InterPro domain/family resolver — EBI Search over the interpro7 index, NOT the InterPro
# REST API. The REST API's `search` matches entry names only, and misses ordinary phrasings:
#
#   "alpha beta hydrolase"                 REST: nothing   here: IPR000073 (994 PDB entries)
#   "alpha/beta hydrolase fold-3 domain"   REST: nothing   here: IPR013094
#   "Abhydrolase_3"                        REST: nothing   here: PF07859
#
# The last two are why: this index also searches `short_name` and `description`, so a Pfam
# short name or a fuller phrase resolves. The first is worse than it looks — dropping one
# slash from a phrase that otherwise works took the caller from a 994-entry anchor to none.
#
# TWO REFERENCES EXIST AND ONLY ONE IS CORRECT. Use the OpenAPI spec:
#     https://www.ebi.ac.uk/ebisearch/ws/rest/openapi.json
# NOT the WADL (.../ws/rest?_wadl), whose camelCase parameter names are dead. EBI Search
# ignores unrecognised parameters SILENTLY — no error, no warning — so the WADL's
# `filterQueries` behaves exactly like a misspelling. Measured on query=kinase:
#
#   no restriction         8,136 hits   CDD, INTERPRO, PANTHER, PFAM
#   filter=...PFAM           761 hits   PFAM only          <- honoured (OpenAPI name)
#   filterQueries=...PFAM  8,136 hits   unchanged          <- ignored (WADL name)
#   <made-up name>=...     8,136 hits   unchanged          <- indistinguishable
#
# Following the WADL would have shipped a resolver whose safety restriction did nothing.
#
# (EBI's "domain" means a SEARCH INDEX — interpro7, intenz — never a protein domain.)
INTERPRO_SEARCH_URL = "https://www.ebi.ac.uk/ebisearch/ws/rest/interpro7"

# The index spans 14 member databases, but only these two are ingested by RCSB, so only
# these yield ids that `rcsb_polymer_entity_annotation.annotation_id` can filter on.
# Measured — every other id space returns ZERO PDB entries, including for domains that are
# certainly in the archive (SMART SM00220 is the S/T kinase catalytic domain):
#
#   IPR000073 -> 994    PF00151 -> 12  |  cd08367, PTHR11352, SM00220, PS50011,
#                                          NF033838, G3DSA:3.40.50.1820 -> 0 each
#
# So the extra breadth is not usable breadth: unrestricted, the top hit for "kinase" and
# "p53 tumor suppressor" is a CDD accession, and "alpha beta hydrolase" returns PROFILE and
# PRINTS ids at ranks 2-3. Every one of those would filter to nothing downstream, silently.
INTERPRO_SOURCE_DATABASES = ("INTERPRO", "PFAM")

# Accepted `entry_type` values -> the vocabulary the index's `type` field uses.
#
# The complete set is published as the subdomains of interpro7 at
#     https://www.ebi.ac.uk/ebisearch/ws/rest/domains/
# and INTERPRO_SUBDOMAIN_TYPES below records it verbatim, so "did we miss a type?" has an
# answer that does not depend on what a sample happened to return.
#
# Two vocabularies for one concept, and mixing them fails SILENTLY. The subdomain ids are
# hyphenated ("interpro7_active-site"); the `type` FIELD is underscored ("active_site").
# `type:active-site` returns 0 hits rather than an error, so a hyphenated value here would
# be an always-empty filter nothing would flag. Everything below is underscored.
#
# (Each result also carries source="interpro7_<type>", the same vocabulary again. Querying
# a subdomain directly — /interpro7_homologous_superfamily — returns results IDENTICAL to
# filtering the parent index, verified on three type/query pairs, so the parent index plus
# `filter` is used: one endpoint, one vocabulary, no hyphen mapping.)
#
# Three types the InterPro REST API did not expose are reachable here: coiled_coil,
# disordered, region.
INTERPRO_SUBDOMAIN_TYPES = (
    "active-site", "binding-site", "coiled_coil", "conserved-site", "disordered",
    "domain", "family", "homologous_superfamily", "ptm", "region", "repeat",
)
INTERPRO_TYPES = {
    "domain": "domain", "family": "family",
    "homologous_superfamily": "homologous_superfamily", "superfamily": "homologous_superfamily",
    "repeat": "repeat", "conserved_site": "conserved_site",
    "binding_site": "binding_site", "active_site": "active_site", "ptm": "ptm",
    "coiled_coil": "coiled_coil", "disordered": "disordered", "region": "region",
}

# Lucene syntax characters. EBI Search parses the query, so raw caller text is unsafe:
# "alpha/beta hydrolase" and "serine/threonine kinase" return HTTP 400, and "kinase:
# activity" is worse — the colon parses as a field qualifier and it returns 0 hits with no
# error at all. Escaping fixes all three.
_LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


def _escape_lucene(text: str) -> str:
    """Escape a caller's free text so the search engine treats it as terms, not syntax."""
    return _LUCENE_SPECIAL.sub(r"\\\1", text)


# Accepted `entry_type` values, derived from the KEYS of the alias map above — every spelling the
# resolver actually accepts, including the "superfamily" alias. Typing it (vs a bare str) ships
# the enum in the tool schema, so the caller picks from the list instead of guessing and the two
# can never drift. The body still normalizes (strip/lower/alias), so direct Python callers keep
# the lenient path.
InterProEntryType = Literal[tuple(sorted(INTERPRO_TYPES))]  # type: ignore[valid-type]

# Enzyme Commission (EC) resolver — EBI Search over the IntEnz database (text -> EC number).
INTENZ_SEARCH_URL = "https://www.ebi.ac.uk/ebisearch/ws/rest/intenz"

# Disease resolver — EBI Ontology Lookup Service (OLS4) over MONDO (text -> MONDO id).
OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

# Organism / taxon resolver — UniProt taxonomy REST (text -> NCBI Taxonomy id). UniProt's
# taxonId IS the NCBI Taxonomy id, which feeds rcsb_entity_source_organism.taxonomy_lineage.id.
UNIPROT_TAXONOMY_SEARCH_URL = "https://rest.uniprot.org/taxonomy/search"


async def _annotation_pdb_count(attribute: str, value: str) -> int | None:
    """Count PDB entries whose polymer-entity annotation `attribute` equals `value`. Best-effort."""
    body = queries.build_count_query(
        filters=[{"attribute": attribute, "operator": "exact_match", "value": value}],
        return_type="entry",
    )
    try:
        raw = await _post_search(body)
        return raw.get("total_count", 0)
    except (httpx.HTTPError, ValueError, RuntimeError):
        return None


# A hit annotated on very few PDB entries is one of two things: a genuinely rare target,
# where the small answer IS the answer — or a name match onto a concept narrower than the
# caller meant. The second is the dangerous one, because it passes every emptiness check
# below and yields a confident, tiny, WRONG answer: rcsb_find_interpro_domains("hormone-
# sensitive lipase") returns exactly one confident hit, IPR010468 with pdb_entry_count 1 —
# the mammalian N-terminal domain, not what the HSL family means in microbial esterase
# nomenclature. Nothing available here can tell the two cases apart, so the note ADVISES
# rather than warns, and the thresholds are deliberately tight: it stays silent unless there
# was almost no choice to make AND the coverage is thin, so a rare-target query does not get
# second-guessed on every call. Tune these two numbers, not the message.
_LOW_COVERAGE_MAX_HITS = 2
_LOW_COVERAGE_MAX_ENTRIES = 10


def _resolver_fallback_note(items: list[dict[str, Any]], label: str) -> str | None:
    """Advise a keyword fallback when a resolver finds nothing usable — or when what it DID
    find resolved cleanly but may not be the concept that was asked for."""
    if not items:
        return (f"No {label} matched this concept. Fall back to a keyword search "
                "(rcsb_query_fulltext, optionally composed with attribute filters) for it.")
    # `pdb_entry_count` is absent when the caller passed with_pdb_counts=False, and None when
    # the count query itself failed. Neither is evidence of absence, and conflating None with
    # 0 would report "not annotated in the PDB" whenever the Search API was merely unreachable.
    counts = [it["pdb_entry_count"] for it in items if isinstance(it.get("pdb_entry_count"), int)]
    if len(counts) < len(items):
        return None
    if not any(counts):
        # rcsb_query_fulltext IS recommended here, and deliberately NOT in the low-coverage
        # branch below. The reasons differ: nothing is annotated at all, so a keyword search
        # is a genuine ALTERNATIVE ROUTE. Down there the note only fires when coverage is
        # under _LOW_COVERAGE_MAX_ENTRIES, so "full text finds more" is guaranteed by the
        # trigger itself and says nothing. Do not harmonise the two branches.
        return (f"Matched {label}(s) but none are annotated in the PDB (pdb_entry_count 0). "
                "A resolver matches your words against TERM NAMES, so it can equally have "
                "landed on a narrower or adjacent piece of your concept. Read the name that "
                "came back; if it is not what you meant, resolve a broader or "
                "differently-worded term for the same concept. Separately, a keyword search "
                "(rcsb_query_fulltext) may still surface relevant structures.")
    best = max(counts)
    if len(items) <= _LOW_COVERAGE_MAX_HITS and best < _LOW_COVERAGE_MAX_ENTRIES:
        return (f"Best match covers only {best} PDB entr{'y' if best == 1 else 'ies'}. That is "
                "expected for a rare target, but a resolver matches your words against TERM "
                "NAMES, so it can equally have landed on a narrower or adjacent piece of your "
                "concept. Read the name that came back before anchoring on this id; if it is "
                "not what you meant, resolve a broader or differently-worded term for the same "
                "concept.")
    return None


async def rcsb_find_go_terms(
    query: str,
    namespace: GoNamespace | None = None,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text molecular function, biological process, or cellular component /
    location (e.g. kinase activity, ATP binding, DNA repair, apoptosis, signal transduction,
    mitochondrial membrane, nucleus) to Gene Ontology (GO) terms, so you can run precise
    GO-based PDB searches instead of keyword guessing.

    Use this when a request involves what a protein DOES or where it acts — "proteins that
    <do X> / are involved in / participate in / are responsible for ...", "localized to /
    located in ...". Resolve the phrase to a GO id here, then filter on it with
    rcsb_query_attribute: exact_match on
    rcsb_polymer_entity_annotation.annotation_lineage.id, id AS A STRING ("GO:0004672").
    The *_lineage.id paths are HIERARCHICAL — they match the term AND everything beneath
    it; use `in` with several ids to broaden.
    For ONLY that exact term without descendants use annotation_id instead.

    Args:
        query: Free-text function / process / location, e.g. "kinase activity", "DNA repair".
        namespace: Optional GO aspect to restrict to. Omit to search all three.
        limit: Max GO terms to return.
        with_pdb_counts: If true (default), annotate each term with pdb_entry_count (PDB
            entries carrying it, via annotation_lineage.id).

    Returns:
        {query, namespace, count, terms:[{id, name, aspect, pdb_entry_count?}]}.
    """
    aspect = None
    if namespace:
        aspect = GO_ASPECTS.get(namespace.strip().lower())
        if aspect is None:
            raise ValueError(
                "namespace must be molecular_function, biological_process, or cellular_component"
            )
    # Over-fetch when filtering by aspect so the post-filter still fills `limit`.
    fetch = min(limit * 5, 50) if aspect else limit
    data = await _get_json(
        QUICKGO_SEARCH_URL, {"query": query, "limit": fetch, "page": 1}, "EBI QuickGO (GO)"
    )
    results = data.get("results") or []
    terms: list[dict[str, Any]] = []
    for r in results:
        if r.get("isObsolete"):
            continue
        if aspect and r.get("aspect") != aspect:
            continue
        terms.append({"id": r.get("id"), "name": r.get("name"), "aspect": r.get("aspect")})
        if len(terms) >= limit:
            break
    if with_pdb_counts and terms:
        counts = await asyncio.gather(*(
            _annotation_pdb_count("rcsb_polymer_entity_annotation.annotation_lineage.id", t["id"])
            for t in terms
        ))
        for term, count in zip(terms, counts):
            term["pdb_entry_count"] = count
    result = {"query": query, "namespace": aspect, "count": len(terms), "terms": terms}
    note = _resolver_fallback_note(terms, "GO term")
    if note:
        result["note"] = note
    return result


async def rcsb_find_interpro_domains(
    query: str,
    entry_type: InterProEntryType | None = None,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text protein domain, family, or fold (e.g. SH2 domain, immunoglobulin
    fold, zinc finger, beta-barrel, WD40 repeat, kinase domain) to InterPro entries, for
    precise InterPro-based PDB searches instead of keyword guessing.

    Use this whenever a request references a protein DOMAIN, FAMILY, or fold — "structures
    containing / with a <domain>", "<domain>-containing proteins", "members of the <family>
    family". Resolve the phrase to an accession here, then filter on it with
    rcsb_query_attribute: exact_match on rcsb_polymer_entity_annotation.annotation_id,
    accession AS A STRING ("IPR000719"). Lineage paths are not available.

    Ids come from InterPro ("IPR000719") or Pfam ("PF07859") — `source_database` on each
    entry says which. Both filter on the same attribute; nothing else needs to change.

    Args:
        query: Free-text domain/family name, e.g. "SH2 domain", "immunoglobulin".
        entry_type: Optional type filter. Omit to return all types.
        limit: Max entries to return.
        with_pdb_counts: If true (default), annotate each entry with pdb_entry_count (PDB
            entries carrying it).

    Returns:
        {query, entry_type, count, entries:[{id, name, type, source_database,
        pdb_entry_count?}]}.
    """
    etype = None
    if entry_type:
        etype = INTERPRO_TYPES.get(entry_type.strip().lower())
        if etype is None:
            raise ValueError(f"entry_type must be one of {sorted(set(INTERPRO_TYPES.values()))}")
    # `query` carries ONLY the caller's text, so relevance is scored against what they
    # actually asked for. Our constraints go in `filter`, which the API documents as
    # "non-scoring queries that do not affect relevance" (GET /{domain}, openapi.json at
    # https://www.ebi.ac.uk/ebisearch/ws/rest/openapi.json). Measured as equivalent today —
    # same hitCount and same top hit on 5 of 6 benchmark queries — because a uniformly
    # matching clause contributes near-constant score. Kept anyway: it is the documented
    # mechanism, and it stays correct if index statistics ever shift.
    filters = [f"source_database:({' OR '.join(INTERPRO_SOURCE_DATABASES)})"]
    if etype:
        filters.append(f"type:{etype}")
    params: dict[str, Any] = {
        "query": _escape_lucene(query),
        "filter": " AND ".join(filters),
        "format": "json",
        "fields": "name,type,source_database",
        "start": 0,
        # `size` is capped at 100 by the API; ResolverLimit already caps callers at 25.
        "size": limit,
    }
    data = await _get_json(INTERPRO_SEARCH_URL, params, "EBI Search (InterPro)")
    entries: list[dict[str, Any]] = []
    for r in data.get("entries") or []:
        fields = r.get("fields") or {}
        first = lambda key: (fields.get(key) or [None])[0]  # noqa: E731 - each field is a list
        entries.append({
            "id": r.get("id"),
            "name": first("name"),
            "type": first("type"),
            "source_database": first("source_database"),
        })
        if len(entries) >= limit:
            break
    if with_pdb_counts and entries:
        counts = await asyncio.gather(*(
            _annotation_pdb_count("rcsb_polymer_entity_annotation.annotation_id", e["id"])
            for e in entries
        ))
        for entry, count in zip(entries, counts):
            entry["pdb_entry_count"] = count
    result = {"query": query, "entry_type": etype, "count": len(entries), "entries": entries}
    note = _resolver_fallback_note(entries, "InterPro entry")
    if note:
        result["note"] = note
    return result


async def rcsb_find_enzyme_classes(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text enzyme, enzyme class, or catalyzed reaction (e.g. alcohol
    dehydrogenase, protease, kinase, DNA polymerase, hydrolase, oxidoreductase) to Enzyme
    Commission (EC) numbers, for precise EC-based PDB searches instead of keyword guessing.

    Use this when a request references an enzyme, enzyme class, or reaction — including
    "enzymes that catalyze / break down / degrade / synthesize / hydrolyze / phosphorylate ...".
    Resolve the phrase to an EC number here, then filter on it with rcsb_query_attribute:
    exact_match on rcsb_polymer_entity.rcsb_ec_lineage.id, EC number AS A STRING.
    The *_lineage.id paths are HIERARCHICAL — they match the term AND everything beneath
    it; use `in` with several ids to broaden.
    A partial EC like "3.4.21" therefore matches the whole sub-subclass.

    Args:
        query: Free-text enzyme / reaction, e.g. "alcohol dehydrogenase", "protein kinase".
        limit: Max EC numbers to return.
        with_pdb_counts: If true (default), annotate each with pdb_entry_count (PDB entries
            carrying it, via rcsb_ec_lineage.id).

    Returns:
        {query, count, enzymes:[{ec, name, pdb_entry_count?}]}.
    """
    # Over-fetch a little so dropping transferred/deleted entries still fills `limit`.
    fetch = min(limit + 5, 30)
    data = await _get_json(
        INTENZ_SEARCH_URL,
        {"query": query, "format": "json", "size": fetch, "fields": "name"},
        "EBI Search (IntEnz)",
    )
    enzymes: list[dict[str, Any]] = []
    for e in data.get("entries") or []:
        names = (e.get("fields") or {}).get("name") or []
        name = names[0] if names else None
        if name and name.lower().startswith(("transferred entry", "deleted entry")):
            continue
        enzymes.append({"ec": e.get("id"), "name": name})
        if len(enzymes) >= limit:
            break
    if with_pdb_counts and enzymes:
        counts = await asyncio.gather(*(
            _annotation_pdb_count("rcsb_polymer_entity.rcsb_ec_lineage.id", e["ec"])
            for e in enzymes
        ))
        for enzyme, count in zip(enzymes, counts):
            enzyme["pdb_entry_count"] = count
    result = {"query": query, "count": len(enzymes), "enzymes": enzymes}
    note = _resolver_fallback_note(enzymes, "EC number")
    if note:
        result["note"] = note
    return result


async def rcsb_find_disease_terms(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text disease, disorder, syndrome, or condition (e.g. diabetes, cancer,
    Alzheimer disease, cystic fibrosis) to MONDO ontology ids, for precise disease-based PDB
    searches instead of keyword guessing.

    Use for ANY request mentioning a disease/disorder/syndrome/condition — "structures involved
    in / associated with / linked to <disease>", "proteins implicated in <disease>". Resolve the
    phrase to a MONDO id here, then filter on it with rcsb_query_attribute: exact_match on
    rcsb_uniprot_annotation.annotation_lineage.id, id AS A STRING ("MONDO:0005148").
    The *_lineage.id paths are HIERARCHICAL — they match the term AND everything beneath
    it; use `in` with several ids to broaden.
    A MONDO id therefore finds the disease and its subtypes.

    Args:
        query: Free-text disease / condition, e.g. "cystic fibrosis", "breast cancer".
        limit: Max MONDO terms to return.
        with_pdb_counts: If true (default), annotate each with pdb_entry_count (PDB entries
            carrying it, via annotation_lineage.id).

    Returns:
        {query, count, diseases:[{id, name, pdb_entry_count?}]}.
    """
    # Over-fetch so de-duplication and obsolete-filtering still fill `limit`.
    fetch = min(limit * 3, 50)
    data = await _get_json(
        OLS_SEARCH_URL,
        {"q": query, "ontology": "mondo", "rows": fetch, "fieldList": "obo_id,label,is_obsolete"},
        "EBI OLS (MONDO)",
    )
    docs = ((data.get("response") or {}).get("docs")) or []
    diseases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in docs:
        oid = d.get("obo_id")
        if not oid or not oid.startswith("MONDO:") or oid in seen or d.get("is_obsolete"):
            continue
        seen.add(oid)
        diseases.append({"id": oid, "name": d.get("label")})
        if len(diseases) >= limit:
            break
    if with_pdb_counts and diseases:
        counts = await asyncio.gather(*(
            _annotation_pdb_count("rcsb_uniprot_annotation.annotation_lineage.id", x["id"])
            for x in diseases
        ))
        for disease, count in zip(diseases, counts):
            disease["pdb_entry_count"] = count
    result = {"query": query, "count": len(diseases), "diseases": diseases}
    note = _resolver_fallback_note(diseases, "MONDO disease term")
    if note:
        result["note"] = note
    return result


async def rcsb_find_organisms(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text organism, common name, or clade (e.g. human, mouse, baker's yeast,
    Escherichia coli, mammals, bacteria, primates) to NCBI Taxonomy ids, for precise
    taxonomy-based PDB searches instead of keyword guessing.

    Use when a request restricts structures by SOURCE ORGANISM or any higher taxon — a common
    name you want as a canonical taxon ("human", "fruit fly"), or a CLADE, which a plain name
    search cannot expand. Resolve the phrase to a taxon id here, then filter on it with
    rcsb_query_attribute: exact_match on rcsb_entity_source_organism.taxonomy_lineage.id,
    id AS A STRING ("9606", not 9606 — a bare number does not match).
    The *_lineage.id paths are HIERARCHICAL — they match the term AND everything beneath
    it; use `in` with several ids to broaden.
    A clade id ("40674" = Mammalia) therefore finds every organism beneath it; for a known
    exact species ncbi_scientific_name exact_match also works. An informal, polyphyletic
    group ("filamentous fungi", "extremophiles", "algae") is NOT a taxon and has no id:
    resolve the nearest CONTAINING taxon, then classify each hit from the lineage its own
    record returns.

    Args:
        query: Free-text organism / clade / common name, e.g. "human", "mammals", "E. coli".
        limit: Max taxa to return.
        with_pdb_counts: If true (default), annotate each taxon with pdb_entry_count (PDB
            entries from it or any organism beneath it, via taxonomy_lineage.id) — this also
            disambiguates a species from its strains.

    Returns:
        {query, count, taxa:[{tax_id, scientific_name, common_name, rank, pdb_entry_count?}]}.
    """
    # Over-fetch so de-duplication still fills `limit` (UniProt can return many strains).
    fetch = min(limit * 3, 50)
    data = await _get_json(
        UNIPROT_TAXONOMY_SEARCH_URL,
        {"query": query, "size": fetch, "fields": "id,scientific_name,common_name,rank"},
        "UniProt taxonomy",
    )
    taxa: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for r in data.get("results") or []:
        tid = r.get("taxonId")
        if tid is None or tid in seen:
            continue
        seen.add(tid)
        taxa.append({
            "tax_id": tid,
            "scientific_name": r.get("scientificName"),
            "common_name": r.get("commonName"),
            "rank": r.get("rank"),
        })
        if len(taxa) >= limit:
            break
    if with_pdb_counts and taxa:
        counts = await asyncio.gather(*(
            _annotation_pdb_count(
                "rcsb_entity_source_organism.taxonomy_lineage.id", str(t["tax_id"])
            )
            for t in taxa
        ))
        for taxon, count in zip(taxa, counts):
            taxon["pdb_entry_count"] = count
    result = {"query": query, "count": len(taxa), "taxa": taxa}
    note = _resolver_fallback_note(taxa, "NCBI taxon")
    if note:
        result["note"] = note
    return result


# rcsb_find_* are the resolver tools; register_resolver_tools wires each onto the
# passed FastMCP instance (equivalent to the @mcp.tool decorator, but the functions
# stay importable/testable on their own).
_RESOLVER_TOOLS = (
    rcsb_find_go_terms,
    rcsb_find_interpro_domains,
    rcsb_find_enzyme_classes,
    rcsb_find_disease_terms,
    rcsb_find_organisms,
)


def register_resolver_tools(mcp) -> None:
    """Attach the ontology/identifier resolver tools (rcsb_find_*) to a FastMCP server."""
    for fn in _RESOLVER_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
