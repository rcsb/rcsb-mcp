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

# InterPro domain/family resolver (EBI InterPro REST API) + friendly type aliases.
INTERPRO_SEARCH_URL = "https://www.ebi.ac.uk/interpro/api/entry/interpro/"
INTERPRO_TYPES = {
    "domain": "domain", "family": "family",
    "homologous_superfamily": "homologous_superfamily", "superfamily": "homologous_superfamily",
    "repeat": "repeat", "conserved_site": "conserved_site",
    "binding_site": "binding_site", "active_site": "active_site", "ptm": "ptm",
}
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
                "(rcsb_search_fulltext, optionally with attribute filters) for it.")
    # `pdb_entry_count` is absent when the caller passed with_pdb_counts=False, and None when
    # the count query itself failed. Neither is evidence of absence, and conflating None with
    # 0 would report "not annotated in the PDB" whenever the Search API was merely unreachable.
    counts = [it["pdb_entry_count"] for it in items if isinstance(it.get("pdb_entry_count"), int)]
    if len(counts) < len(items):
        return None
    if not any(counts):
        return (f"Matched {label}(s) but none are annotated in the PDB (pdb_entry_count 0). "
                "A keyword search (rcsb_search_fulltext) may still surface relevant structures.")
    best = max(counts)
    if len(items) <= _LOW_COVERAGE_MAX_HITS and best < _LOW_COVERAGE_MAX_ENTRIES:
        return (f"Best match covers only {best} PDB entr{'y' if best == 1 else 'ies'}. That is "
                "expected for a rare target, but a match that fits your WORDING while denoting a "
                "NARROWER concept than you meant looks exactly the same. Read the name that came "
                "back before anchoring a search on this id; if it may be the wrong concept, "
                "broaden the query or cross-check with rcsb_search_fulltext.")
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
    located in ...". Resolve the phrase to a GO id here, then search by it — see the resolver
    guidance in the rcsb_mcp_guide prompt for the attribute path and lineage semantics.

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
    family". Resolve the phrase to an InterPro accession (IPRxxxxxx) here, then search by it —
    see the resolver guidance in the rcsb_mcp_guide prompt for the attribute path and lineage
    semantics.

    Args:
        query: Free-text domain/family name, e.g. "SH2 domain", "immunoglobulin".
        entry_type: Optional InterPro type filter. Omit to return all types.
        limit: Max entries to return.
        with_pdb_counts: If true (default), annotate each entry with pdb_entry_count (PDB
            entries carrying it).

    Returns:
        {query, entry_type, count, entries:[{id, name, type, pdb_entry_count?}]}.
    """
    etype = None
    if entry_type:
        etype = INTERPRO_TYPES.get(entry_type.strip().lower())
        if etype is None:
            raise ValueError(f"entry_type must be one of {sorted(set(INTERPRO_TYPES.values()))}")
    params: dict[str, Any] = {"search": query, "page_size": limit}
    if etype:
        params["type"] = etype
    data = await _get_json(INTERPRO_SEARCH_URL, params, "EBI InterPro")
    results = data.get("results") or []
    entries: list[dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata") or {}
        entries.append({"id": meta.get("accession"), "name": meta.get("name"), "type": meta.get("type")})
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
    Resolve the phrase to an EC number here, then search by it — see the resolver guidance in
    the rcsb_mcp_guide prompt for the attribute path and lineage semantics.

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
    phrase to a MONDO id here, then search by it — see the resolver guidance in the
    rcsb_mcp_guide prompt for the attribute path and lineage semantics.

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
    search cannot expand. Resolve the phrase to a taxon id here, then search by it — see the
    resolver guidance in the rcsb_mcp_guide prompt for the attribute path, lineage semantics and
    the id-typing gotcha.

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
