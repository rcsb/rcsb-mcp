"""An MCP server for the RCSB PDB Search and Data APIs.

Exposes tools that let an LLM search the Protein Data Bank
(https://search.rcsb.org) by keyword, structural attribute, or sequence
similarity, and fetch metadata from the RCSB Data API
(https://data.rcsb.org/graphql) for entries, polymer entities, and ligands.
The Search API returns only identifiers, so the search tools optionally
enrich results with titles/resolution/method pulled from the Data API.
Additionally, the Sequence Coordinates API (https://sequence-coordinates.rcsb.org/graphql)
is used to map alignments and positional annotations between sequence reference systems
(`UNIPROT`, `NCBI_PROTEIN`, `NCBI_GENOME`, `PDB_ENTITY`, `PDB_INSTANCE`).

Run locally (stdio, for Claude Desktop / MCP Inspector):
    python -m rcsb_mcp.server
"""
from __future__ import annotations

from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from . import queries

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
DATA_GRAPHQL_URL = "https://data.rcsb.org/graphql"
SEQCOORD_GRAPHQL_URL = "https://sequence-coordinates.rcsb.org/graphql"
USER_AGENT = "rcsb-mcp/0.1 (https://github.com/your/repo)"
TIMEOUT = httpx.Timeout(30.0)

mcp = FastMCP("rcsb-pdb")


# --------------------------------------------------------------------------- #
# Low-level HTTP helpers
# --------------------------------------------------------------------------- #
async def _post_search(body: dict[str, Any]) -> dict[str, Any]:
    """POST a query to the Search API. Returns a normalized result dict."""
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(SEARCH_URL, json=body)
    # The API returns 204 No Content when nothing matches.
    if resp.status_code == 204:
        return {"total_count": 0, "result_set": []}
    resp.raise_for_status()
    return resp.json()


async def _post_graphql(
    query: str, variables: dict[str, Any] | None = None, url: str = DATA_GRAPHQL_URL
) -> dict[str, Any]:
    """POST a GraphQL query to an RCSB GraphQL endpoint. Returns the raw {data, errors} payload.

    These endpoints reply 200 even for query/validation errors, surfacing them in
    an ``errors`` array, so callers must inspect that rather than HTTP status.
    """
    body = {"query": query, "variables": variables or {}}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(url, json=body)
    resp.raise_for_status()
    return resp.json()


async def _graphql_field(body: dict[str, Any], field: str, url: str = DATA_GRAPHQL_URL) -> Any:
    """Run a builder's GraphQL body and return data[field] (dict/list/None), raising on errors."""
    payload = await _post_graphql(body["query"], body.get("variables"), url=url)
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "") for e in payload["errors"])
        raise RuntimeError(f"RCSB GraphQL error: {msgs}")
    return (payload.get("data") or {}).get(field)


async def _query_batch(
    object_key: str, ids: list[str], fields: str | None
) -> dict[str, Any]:
    """Fetch a batch Data API object, returning {count, <object>: [...], not_found?}.

    The API silently drops unknown ids, so we report which requested ids did
    not come back. Returned field selections are passed through as-is.
    """
    spec = queries.DATA_OBJECTS[object_key]
    nodes = await _graphql_field(queries.build_data_query(object_key, ids, fields), spec.root_field)
    # Unknown ids are either dropped or returned as null depending on the field.
    nodes = [n for n in (nodes or []) if n is not None]
    returned = {str(n.get("rcsb_id", "")).upper() for n in nodes}
    requested = [str(i).strip().upper() for i in ids if str(i).strip()]
    missing = [i for i in requested if i not in returned]
    result: dict[str, Any] = {"count": len(nodes), spec.root_field: nodes}
    if missing:
        result["not_found"] = missing
    return result


async def _query_single(
    object_key: str, id_value: Any, fields: str | None
) -> dict[str, Any]:
    """Fetch a singleton Data API object, or a not-found marker."""
    spec = queries.DATA_OBJECTS[object_key]
    node = await _graphql_field(queries.build_data_query(object_key, id_value, fields), spec.root_field)
    return node if node is not None else {"id": id_value, "error": "not found"}


def _entry_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Compact, flat summary for one CoreEntry node (used to enrich search hits)."""
    info = node.get("rcsb_entry_info") or {}
    resolutions = info.get("resolution_combined") or []
    return {
        "id": node.get("rcsb_id"),
        "title": (node.get("struct") or {}).get("title"),
        "experimental_method": (node.get("exptl") or [{}])[0].get("method"),
        "resolution_A": resolutions[0] if resolutions else None,
        "deposited": (node.get("rcsb_accession_info") or {}).get("deposit_date"),
    }


async def _fetch_entry_summaries(pdb_ids: list[str]) -> list[dict[str, Any]]:
    """Batch-fetch flat entry summaries via GraphQL, one result per requested id.

    The API drops unknown ids from its response, so we map returned nodes back
    by id and fill an explicit "not found" for any that are missing.
    """
    ids = [pid.strip().upper() for pid in pdb_ids if pid.strip()]
    if not ids:
        return []
    nodes = await _graphql_field(queries.build_data_query("entries", ids), "entries") or []
    by_id = {
        str(n.get("rcsb_id", "")).upper(): _entry_summary(n) for n in nodes if n is not None
    }
    return [by_id.get(pid, {"id": pid, "error": "not found"}) for pid in ids]


async def _enrich(identifiers: list[str], limit: int = 25) -> list[dict[str, Any]]:
    """Fetch entry metadata for a list of identifiers in a single GraphQL request."""
    # Only top-level entry IDs can be enriched as entries; entity/assembly IDs
    # look like "1ABC_1" / "1ABC-1", so strip the suffix and de-duplicate.
    entry_ids: list[str] = []
    seen: set[str] = set()
    for ident in identifiers[:limit]:
        base = ident.split("_")[0].split("-")[0]
        if base not in seen:
            seen.add(base)
            entry_ids.append(base)
    if not entry_ids:
        return []
    try:
        return await _fetch_entry_summaries(entry_ids)
    except (httpx.HTTPError, RuntimeError) as exc:
        # Enrichment is best-effort: never fail the search because of it.
        return [{"id": pid, "error": str(exc)} for pid in entry_ids]


def _format(raw: dict[str, Any], enriched: list[dict[str, Any]] | None) -> dict[str, Any]:
    hits = [
        {"id": r["identifier"], "score": round(r.get("score", 0.0), 3)}
        for r in raw.get("result_set", [])
    ]
    result = {"total_count": raw.get("total_count", 0), "returned": len(hits), "hits": hits}
    if enriched is not None:
        result["details"] = enriched
    return result


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
async def search_fulltext(
    query: str,
    return_type: str = "entry",
    limit: int = 10,
    include_computed_models: bool = False,
    enrich: bool = True,
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Search the PDB by free-text keywords (e.g. "CRISPR Cas9", "hemoglobin").

    Args:
        query: Free-text search terms. Quote multi-word phrases for exact match.
        return_type: One of entry, polymer_entity, assembly, etc. (default "entry").
        limit: Max number of hits to return (1-100).
        include_computed_models: Also search computed structure models (AlphaFold etc.).
        enrich: If true, attach title/method/resolution for each entry hit.
        group_by_identity: If set (100/95/90/70/50/30), collapse redundant hits into
            sequence-identity clusters and return one representative each; forces
            return_type to "polymer_entity".
    """
    limit = max(1, min(limit, 100))
    return_type = "polymer_entity" if group_by_identity else return_type
    body = queries.build_fulltext_query(
        query,
        return_type=return_type,
        rows=limit,
        include_computed=include_computed_models,
        group_by_identity=group_by_identity,
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched)


@mcp.tool()
async def search_by_attribute(
    attribute: str,
    operator: str,
    value: Any = None,
    return_type: str = "entry",
    limit: int = 10,
    enrich: bool = True,
    negation: bool = False,
    case_sensitive: bool = False,
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Search by a specific structural attribute.

    Examples:
        - High-resolution structures:
          attribute="rcsb_entry_info.resolution_combined", operator="less", value=2.0
        - Organism:
          attribute="rcsb_entity_source_organism.ncbi_scientific_name",
          operator="exact_match", value="Homo sapiens"
        - Released after a date:
          attribute="rcsb_accession_info.initial_release_date",
          operator="greater", value="2024-01-01T00:00:00Z"
        - Has any ligand annotated (no value needed):
          attribute="rcsb_nonpolymer_entity.pdbx_description", operator="exists"

    Args:
        attribute: A dotted RCSB attribute path (see the Search API attribute list).
        operator: One of exact_match, in, contains_words, contains_phrase,
            greater, greater_or_equal, less, less_or_equal, equals, range, exists.
        value: The comparison value (string, number, list, or a range object
            {from, to, include_lower, include_upper} — bounds are EXCLUSIVE unless
            include_lower/include_upper are true). Omit for the "exists" operator.
        return_type: Result identifier type (default "entry").
        limit: Max hits (1-100).
        enrich: Attach entry metadata when return_type is "entry".
        negation: Invert the match (e.g. "not Homo sapiens").
        case_sensitive: Match the value case-sensitively (default insensitive).
        group_by_identity: If set (100/95/90/70/50/30), return one representative per
            sequence-identity cluster; forces return_type to "polymer_entity".
    """
    limit = max(1, min(limit, 100))
    return_type = "polymer_entity" if group_by_identity else return_type
    body = queries.build_attribute_query(
        attribute,
        operator,
        value,
        return_type=return_type,
        rows=limit,
        negation=negation,
        case_sensitive=case_sensitive,
        group_by_identity=group_by_identity,
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched)


@mcp.tool()
async def search_combined(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    limit: int = 10,
    enrich: bool = True,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Search with several constraints at once (free text + attribute filters).

    Use this when a request combines multiple conditions, e.g.
    "human hemoglobin structures better than 2 Angstrom resolution":
        full_text="hemoglobin",
        filters=[
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "rcsb_entry_info.resolution_combined",
             "operator": "less", "value": 2.0},
        ],
        sort_by="rcsb_entry_info.resolution_combined", sort_direction="asc"

    Args:
        full_text: Optional free-text term, combined with the filters.
        filters: List of {attribute, operator, value} dicts (see search_by_attribute
            for operators and attribute paths). Each may also carry optional
            "negation" and "case_sensitive" booleans.
        logical_operator: Combine all conditions with "and" (default) or "or".
        return_type: Result identifier type (default "entry").
        limit: Max hits (1-100).
        enrich: Attach title/method/resolution for each entry hit.
        sort_by: Attribute to sort by, e.g. "rcsb_entry_info.resolution_combined".
            Omit to sort by relevance score.
        sort_direction: "asc" or "desc" (default "asc").
        group_by_identity: If set (100/95/90/70/50/30), return one representative per
            sequence-identity cluster; forces return_type to "polymer_entity".
    """
    limit = max(1, min(limit, 100))
    return_type = "polymer_entity" if group_by_identity else return_type
    body = queries.build_combined_query(
        full_text=full_text,
        filters=filters,
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by_identity=group_by_identity,
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched)


@mcp.tool()
async def search_by_sequence(
    sequence: str,
    sequence_type: str = "protein",
    identity_cutoff: float = 0.3,
    evalue_cutoff: float = 1.0,
    limit: int = 10,
) -> dict[str, Any]:
    """Find PDB polymer entities similar to a given sequence (MMseqs2, BLAST-like).

    Args:
        sequence: The query sequence in one-letter code.
        sequence_type: "protein", "dna", or "rna".
        identity_cutoff: Minimum sequence identity as a fraction 0-1 (e.g. 0.3 = 30%).
        evalue_cutoff: Maximum E-value to report.
        limit: Max hits (1-100). Returns polymer_entity IDs like "4HHB_1".
    """
    limit = max(1, min(limit, 100))
    body = queries.build_sequence_query(
        sequence,
        sequence_type=sequence_type,
        identity_cutoff=identity_cutoff,
        evalue_cutoff=evalue_cutoff,
        rows=limit,
    )
    raw = await _post_search(body)
    return _format(raw, None)


@mcp.tool()
async def search_by_chemical(
    value: str,
    query_type: str = "descriptor",
    descriptor_type: str = "SMILES",
    match_type: str = "graph-relaxed",
    match_subset: bool = False,
    return_type: str = "mol_definition",
    limit: int = 10,
) -> dict[str, Any]:
    """Search PDB chemical components by structure (SMILES/InChI) or formula.

    Args:
        value: A SMILES/InChI string (query_type="descriptor") or a molecular
            formula like "C8H9NO2" (query_type="formula").
        query_type: "descriptor" (default) or "formula".
        descriptor_type: "SMILES" or "InChI" (descriptor queries only).
        match_type: Graph/fingerprint criterion for descriptor queries. Use
            "graph-relaxed" for whole-molecule matches or "sub-struct-graph-relaxed"
            for substructure search; "fingerprint-similarity" for similar molecules.
        match_subset: Formula queries only — match formulas that merely contain the
            requested atoms.
        return_type: Result identifier type (default "mol_definition" = chem comp).
        limit: Max hits (1-100).
    """
    limit = max(1, min(limit, 100))
    body = queries.build_chemical_query(
        value,
        query_type=query_type,
        descriptor_type=descriptor_type,
        match_type=match_type,
        match_subset=match_subset,
        return_type=return_type,
        rows=limit,
    )
    raw = await _post_search(body)
    return _format(raw, None)


@mcp.tool()
async def search_by_structure(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
    return_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Find structures with a similar 3D shape to a reference PDB structure.

    Args:
        entry_id: Reference PDB entry, e.g. "4HHB".
        assembly_id: Use this biological assembly as the reference (e.g. "1").
            Defaults to assembly "1" when neither assembly_id nor asym_id is given.
        asym_id: Use this single chain as the reference instead (mutually exclusive
            with assembly_id).
        return_type: Result identifier type; defaults to "assembly" for an assembly
            reference or "polymer_instance" for a chain reference.
        limit: Max hits (1-100).
    """
    limit = max(1, min(limit, 100))
    body = queries.build_structure_query(
        entry_id,
        assembly_id=assembly_id,
        asym_id=asym_id,
        return_type=return_type,
        rows=limit,
    )
    raw = await _post_search(body)
    return _format(raw, None)


@mcp.tool()
async def search_by_seqmotif(
    pattern: str,
    pattern_type: str = "prosite",
    sequence_type: str = "protein",
    return_type: str = "polymer_entity",
    limit: int = 10,
) -> dict[str, Any]:
    """Find polymers containing a short sequence motif (PROSITE / regex / simple).

    Args:
        pattern: The motif, e.g. "C-x(2,4)-C-x(3)-[LIVMFYWC]-x(8)-H-x(3,5)-H"
            (prosite), "C..H[LIVF]" (regex), or "NXS" (simple wildcards).
        pattern_type: "prosite" (default), "regex", or "simple".
        sequence_type: "protein" (default), "dna", or "rna".
        return_type: Result identifier type (default "polymer_entity").
        limit: Max hits (1-100).
    """
    limit = max(1, min(limit, 100))
    body = queries.build_seqmotif_query(
        pattern,
        pattern_type=pattern_type,
        sequence_type=sequence_type,
        return_type=return_type,
        rows=limit,
    )
    raw = await _post_search(body)
    return _format(raw, None)


@mcp.tool()
async def search_advanced(query_body: dict[str, Any]) -> dict[str, Any]:
    """Run a raw RCSB Search API query body (escape hatch).

    Endpoint: https://search.rcsb.org/rcsbsearch/v2/query . The typed search_*
    tools cover the common cases; use this for features they don't expose —
    facets, return_all_hits, return_counts, group_by "groups", strucmotif, or
    deeply nested boolean queries. The body must follow the Search API query
    language ({"query": ..., "return_type": ..., "request_options": ...}).
    Returns the normalized {total_count, returned, hits} result.

    Example:
        query_body={
          "query": {"type": "terminal", "service": "full_text",
                    "parameters": {"value": "ribosome"}},
          "return_type": "entry",
          "request_options": {"paginate": {"start": 0, "rows": 5}},
        }
    """
    raw = await _post_search(query_body)
    return _format(raw, None)


# --------------------------------------------------------------------------- #
# Data API tools — one per GraphQL root field (singular forms are covered by
# their batch tool, called with a single-element list). Each returns the raw
# selected GraphQL node(s); pass `fields` to override the curated default
# selection with your own GraphQL sub-selection (omit the surrounding braces).
# --------------------------------------------------------------------------- #
@mcp.tool()
async def get_entries(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch metadata for one or more PDB entries (title, method, resolution, dates).

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]. Unknown IDs are
    listed under "not_found". For a single entry pass a one-element list.
    """
    return await _query_batch("entries", entry_ids, fields)


@mcp.tool()
async def get_polymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entities (protein/nucleic-acid molecules).

    IDs combine entry + entity number, e.g. ["4HHB_1"] — exactly what
    search_by_sequence returns. Default fields: description, sequence, length,
    weight, and source organism.
    """
    return await _query_batch("polymer_entities", entity_ids, fields)


@mcp.tool()
async def get_nonpolymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer (ligand/cofactor) entities, e.g. ["4HHB_3"].

    Default fields: description, weight, copy count, and the bound chemical
    component ID. Use get_chem_comps for the chemistry of that component.
    """
    return await _query_batch("nonpolymer_entities", entity_ids, fields)


@mcp.tool()
async def get_branched_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched (carbohydrate / oligosaccharide) entities, e.g. ["5FMB_2"]."""
    return await _query_batch("branched_entities", entity_ids, fields)


@mcp.tool()
async def get_polymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity instances (individual chains), e.g. ["4HHB.A"] (entry.asym_id)."""
    return await _query_batch("polymer_entity_instances", instance_ids, fields)


@mcp.tool()
async def get_nonpolymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity instances (individual bound ligands), e.g. ["4HHB.E"]."""
    return await _query_batch("nonpolymer_entity_instances", instance_ids, fields)


@mcp.tool()
async def get_branched_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched entity instances (individual glycan chains), e.g. ["5FMB.C"]."""
    return await _query_batch("branched_entity_instances", instance_ids, fields)


@mcp.tool()
async def get_assemblies(assembly_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological assemblies, e.g. ["4HHB-1"] (entry-assembly).

    Default fields: composition counts and oligomeric state.
    """
    return await _query_batch("assemblies", assembly_ids, fields)


@mcp.tool()
async def get_interfaces(interface_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch assembly interfaces, e.g. ["1BMV-1.1"] (entry-assembly.interface).

    Default fields: buried area, character, composition, residue count.
    """
    return await _query_batch("interfaces", interface_ids, fields)


@mcp.tool()
async def get_chem_comps(comp_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch chemical components / ligands by their short codes, e.g. ["HEM", "ATP"].

    Default fields: name, formula, weight, type, SMILES, InChIKey.
    """
    return await _query_batch("chem_comps", comp_ids, fields)


@mcp.tool()
async def get_entry_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch entry groups (clusters of related entries) by group ID."""
    return await _query_batch("entry_groups", group_ids, fields)


@mcp.tool()
async def get_polymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity groups (e.g. sequence clusters), e.g. ["85_70"]."""
    return await _query_batch("polymer_entity_groups", group_ids, fields)


@mcp.tool()
async def get_nonpolymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity groups (clusters of related ligands) by group ID."""
    return await _query_batch("nonpolymer_entity_groups", group_ids, fields)


@mcp.tool()
async def get_uniprot(uniprot_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch the UniProt record RCSB maps to an accession, e.g. "P69905".

    Default fields: accession(s), entry name, protein name, source organism.
    """
    return await _query_single("uniprot", uniprot_id, fields)


@mcp.tool()
async def get_pubmed(pubmed_id: int, fields: str | None = None) -> dict[str, Any]:
    """Fetch the PubMed record for a citation by its integer ID, e.g. 6726807.

    Default fields: PubMed Central ID, DOI, abstract text.
    """
    return await _query_single("pubmed", pubmed_id, fields)


@mcp.tool()
async def get_group_provenance(group_provenance_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch provenance/method metadata for a grouping, e.g. "provenance_sequence_identity"."""
    return await _query_single("group_provenance", group_provenance_id, fields)


@mcp.tool()
async def data_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an arbitrary GraphQL query against the RCSB Data API (escape hatch).

    Endpoint: https://data.rcsb.org/graphql . The get_* tools cover every root
    field with curated defaults; reach for this only when you need fields or
    nesting they don't expose, or to combine several objects in one query.
    Returns the raw {"data": ..., "errors": ...} payload so query/validation
    errors are visible.

    Example:
        query='''query($ids:[String!]!){
          assemblies(assembly_ids:$ids){ rcsb_id pdbx_struct_oper_list{ matrix } }
        }'''
        variables={"ids": ["4HHB-1"]}

    Args:
        query: A GraphQL query string. Prefer $variables over inlining values.
        variables: Optional dict of GraphQL variables referenced by the query.
    """
    return await _post_graphql(query, variables)


# --------------------------------------------------------------------------- #
# Sequence Coordinates API tools (https://sequence-coordinates.rcsb.org/graphql)
# Map alignments and positional annotations between sequence reference systems
# (UniProt, NCBI, PDB entity/instance). Each returns the raw selected GraphQL
# node(s); pass `fields` to override the default selection.
# --------------------------------------------------------------------------- #
@mcp.tool()
async def seqcoord_alignments(
    query_id: str,
    from_ref: str,
    to_ref: str,
    seq_range: list[int] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Cross-reference a sequence across PDB, UniProt, and NCBI, with aligned ranges.

    This is the tool for "which X identifiers correspond to this sequence?" across
    databases — including NCBI. The RCSB Data API only cross-references UniProt, so
    use THIS tool for NCBI RefSeq protein / genome mappings (and PDB<->UniProt too).
    The returned target_alignments[].target_id values are the mapped identifiers in
    the to_ref system, each with its aligned regions.

    Reference systems (from_ref/to_ref):
        UNIPROT       — a UniProt accession, e.g. "P69905"
        NCBI_PROTEIN  — an NCBI RefSeq protein, e.g. "NP_000508"
        NCBI_GENOME   — an NCBI RefSeq genome, e.g. "NC_000016"
        PDB_ENTITY    — a PDB polymer entity, e.g. "4HHB_1" (entry_entityNumber)
        PDB_INSTANCE  — a PDB polymer chain, e.g. "4HHB.A" (entry.asym_id)

    Note: PDB query ids must be ENTITY-level ("4HHB_1"), not a bare entry ("4HHB").
    To answer a question about a whole entry, first get its polymer entity ids
    (e.g. via the Data API: 4HHB -> 4HHB_1, 4HHB_2) and query each one.

    Examples:
        - "What NCBI proteins map to PDB entity 4HHB_1?"
          query_id="4HHB_1", from_ref="PDB_ENTITY", to_ref="NCBI_PROTEIN"
        - "Which PDB entities correspond to UniProt P69905?"
          query_id="P69905", from_ref="UNIPROT", to_ref="PDB_ENTITY"

    Args:
        query_id: The sequence id in the from_ref system (see above).
        from_ref: Reference system of query_id.
        to_ref: Reference system to map onto.
        seq_range: Optional [begin, end] (1-based) to restrict the query region.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_alignments_query(query_id, from_ref, to_ref, seq_range, fields)
    data = await _graphql_field(body, "alignments", url=SEQCOORD_GRAPHQL_URL)
    if not data or not (data.get("target_alignments")):
        return {
            "query_id": query_id,
            "from_ref": from_ref,
            "to_ref": to_ref,
            "target_alignments": [],
            "note": (
                "No alignments found. For PDB, query_id must be an entity ("
                f'e.g. "4HHB_1"), not a bare entry. Got {query_id!r}.'
                if from_ref.startswith("PDB") and "_" not in query_id and "." not in query_id
                else "No alignments found for this query."
            ),
        }
    return data


@mcp.tool()
async def seqcoord_annotations(
    query_id: str,
    reference: str,
    sources: list[str],
    seq_range: list[int] | None = None,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch positional sequence annotations (features) for one sequence.

    reference (the system query_id is given in): NCBI_GENOME, NCBI_PROTEIN,
    PDB_ENTITY, PDB_INSTANCE, UNIPROT.
    sources (annotation provenance, one or more): PDB_ENTITY, PDB_INSTANCE,
    PDB_INTERFACE, UNIPROT.

    Args:
        query_id: The sequence id, e.g. "4HHB_1" (PDB_ENTITY) or "P69905" (UNIPROT).
        reference: Reference system of query_id.
        sources: Annotation source(s) to pull features from.
        seq_range: Optional [begin, end] (1-based) to restrict the region.
        filters: Optional list of {field, operation, source?, values} filter dicts,
            where field is TARGET_ID or TYPE and operation is CONTAINS or EQUALS.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_annotations_query(
        query_id, reference, sources, seq_range, filters, fields
    )
    data = await _graphql_field(body, "annotations", url=SEQCOORD_GRAPHQL_URL) or []
    return {"count": len(data), "annotations": data}


@mcp.tool()
async def seqcoord_group_alignments(
    group: str,
    group_id: str,
    filter_terms: list[str] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch alignments among the members of a sequence group.

    group: MATCHING_UNIPROT_ACCESSION or SEQUENCE_IDENTITY.

    Args:
        group: How the group is defined.
        group_id: The group id, e.g. "P69905" (a UniProt accession) for
            MATCHING_UNIPROT_ACCESSION.
        filter_terms: Optional list of target ids to restrict the group members.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_group_alignments_query(group, group_id, filter_terms, fields)
    data = await _graphql_field(body, "group_alignments", url=SEQCOORD_GRAPHQL_URL)
    return data if data is not None else {"group_id": group_id, "error": "no alignment found"}


@mcp.tool()
async def seqcoord_group_annotations(
    group: str,
    group_id: str,
    sources: list[str],
    summary: bool = False,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch annotations across the members of a sequence group.

    group: MATCHING_UNIPROT_ACCESSION or SEQUENCE_IDENTITY.
    sources (one or more): PDB_ENTITY, PDB_INSTANCE, PDB_INTERFACE, UNIPROT.

    Args:
        group: How the group is defined.
        group_id: The group id, e.g. "P69905" for MATCHING_UNIPROT_ACCESSION.
        sources: Annotation source(s) to pull features from.
        summary: If true, return a positional summary aggregated across the group
            (group_annotations_summary) instead of per-member annotations.
        filters: Optional filter dicts (see seqcoord_annotations).
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_group_annotations_query(
        group, group_id, sources, summary=summary, filters=filters, fields=fields
    )
    field = "group_annotations_summary" if summary else "group_annotations"
    data = await _graphql_field(body, field, url=SEQCOORD_GRAPHQL_URL) or []
    return {"count": len(data), "annotations": data}


@mcp.tool()
async def seqcoord_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an arbitrary GraphQL query against the RCSB Sequence Coordinates API.

    Endpoint: https://sequence-coordinates.rcsb.org/graphql . Escape hatch for
    fields/arguments the typed seqcoord_* tools don't expose. Root fields:
    alignments, annotations, group_alignments, group_annotations,
    group_annotations_summary. Returns the raw {"data": ..., "errors": ...} payload.

    Args:
        query: A GraphQL query string. Prefer $variables over inlining values.
        variables: Optional dict of GraphQL variables referenced by the query.
    """
    return await _post_graphql(query, variables, url=SEQCOORD_GRAPHQL_URL)


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
