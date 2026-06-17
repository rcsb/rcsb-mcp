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
USER_AGENT = "rcsb-mcp/0.1 (https://github.com/rcsb/rcsb-mcp)"
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
        attribute: A dotted RCSB attribute path (see the Search API attribute list: https://search.rcsb.org/structure-search-attributes.html).
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

def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
