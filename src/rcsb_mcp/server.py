"""An MCP server for the RCSB PDB Search and Data APIs.

Exposes tools that let an LLM search the Protein Data Bank
(https://search.rcsb.org) by keyword, structural attribute, or sequence
similarity, and fetch metadata from the RCSB Data API
(https://data.rcsb.org/graphql) for entries, polymer entities, and ligands.
The Search API returns only identifiers, so the search tools optionally
enrich results with titles/resolution/method pulled from the Data API.

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


async def _post_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST a GraphQL query to the Data API. Returns the raw {data, errors} payload.

    The endpoint replies 200 even for query/validation errors, surfacing them in
    an ``errors`` array, so callers must inspect that rather than HTTP status.
    """
    body = {"query": query, "variables": variables or {}}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(DATA_GRAPHQL_URL, json=body)
    resp.raise_for_status()
    return resp.json()


async def _graphql_nodes(body: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Run a builder's GraphQL body and return the list under data[field], raising on errors."""
    payload = await _post_graphql(body["query"], body.get("variables"))
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "") for e in payload["errors"])
        raise RuntimeError(f"RCSB Data API GraphQL error: {msgs}")
    return (payload.get("data") or {}).get(field) or []


def _entry_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Compact summary for one CoreEntry GraphQL node."""
    info = node.get("rcsb_entry_info") or {}
    resolutions = info.get("resolution_combined") or []
    return {
        "id": node.get("rcsb_id"),
        "title": (node.get("struct") or {}).get("title"),
        "experimental_method": (node.get("exptl") or [{}])[0].get("method"),
        "resolution_A": resolutions[0] if resolutions else None,
        "deposited": (node.get("rcsb_accession_info") or {}).get("deposit_date"),
    }


def _polymer_entity_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Compact summary for one CorePolymerEntity GraphQL node."""
    entity = node.get("rcsb_polymer_entity") or {}
    poly = node.get("entity_poly") or {}
    organisms = [
        o.get("ncbi_scientific_name") for o in (node.get("rcsb_entity_source_organism") or [])
    ]
    return {
        "id": node.get("rcsb_id"),
        "description": entity.get("pdbx_description"),
        "polymer_type": poly.get("type"),
        "length": poly.get("rcsb_sample_sequence_length"),
        "sequence": poly.get("pdbx_seq_one_letter_code_can"),
        "source_organisms": [o for o in organisms if o],
        "formula_weight_kDa": entity.get("formula_weight"),
    }


def _chem_comp_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Compact summary for one CoreChemComp (ligand) GraphQL node."""
    comp = node.get("chem_comp") or {}
    desc = node.get("rcsb_chem_comp_descriptor") or {}
    return {
        "id": node.get("rcsb_id"),
        "name": comp.get("name"),
        "formula": comp.get("formula"),
        "formula_weight": comp.get("formula_weight"),
        "type": comp.get("type"),
        "smiles": desc.get("SMILES"),
        "inchikey": desc.get("InChIKey"),
    }


async def _fetch_entry_summaries(pdb_ids: list[str]) -> list[dict[str, Any]]:
    """Batch-fetch entry summaries via GraphQL, one result per requested id.

    The API drops unknown ids from its response, so we map returned nodes back
    by id and fill an explicit "not found" for any that are missing.
    """
    ids = [pid.strip().upper() for pid in pdb_ids if pid.strip()]
    if not ids:
        return []
    nodes = await _graphql_nodes(queries.build_entries_query(ids), "entries")
    by_id = {n.get("rcsb_id", "").upper(): _entry_summary(n) for n in nodes}
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
) -> dict[str, Any]:
    """Search the PDB by free-text keywords (e.g. "CRISPR Cas9", "hemoglobin").

    Args:
        query: Free-text search terms. Quote multi-word phrases for exact match.
        return_type: One of entry, polymer_entity, assembly, etc. (default "entry").
        limit: Max number of hits to return (1-100).
        include_computed_models: Also search computed structure models (AlphaFold etc.).
        enrich: If true, attach title/method/resolution for each entry hit.
    """
    limit = max(1, min(limit, 100))
    body = queries.build_fulltext_query(
        query, return_type=return_type, rows=limit, include_computed=include_computed_models
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched)


@mcp.tool()
async def search_by_attribute(
    attribute: str,
    operator: str,
    value: Any,
    return_type: str = "entry",
    limit: int = 10,
    enrich: bool = True,
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

    Args:
        attribute: A dotted RCSB attribute path (see the Search API attribute list).
        operator: One of exact_match, in, contains_words, contains_phrase,
            greater, greater_or_equal, less, less_or_equal, equals, range.
        value: The comparison value (string, number, list, or {from,to} for range).
        return_type: Result identifier type (default "entry").
        limit: Max hits (1-100).
        enrich: Attach entry metadata when return_type is "entry".
    """
    limit = max(1, min(limit, 100))
    body = queries.build_attribute_query(
        attribute, operator, value, return_type=return_type, rows=limit
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
            for operators and attribute paths).
        logical_operator: Combine all conditions with "and" (default) or "or".
        return_type: Result identifier type (default "entry").
        limit: Max hits (1-100).
        enrich: Attach title/method/resolution for each entry hit.
        sort_by: Attribute to sort by, e.g. "rcsb_entry_info.resolution_combined".
            Omit to sort by relevance score.
        sort_direction: "asc" or "desc" (default "asc").
    """
    limit = max(1, min(limit, 100))
    body = queries.build_combined_query(
        full_text=full_text,
        filters=filters,
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        sort_by=sort_by,
        sort_direction=sort_direction,
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
async def get_entry(pdb_id: str) -> dict[str, Any]:
    """Fetch a metadata summary (title, method, resolution, date) for one PDB ID."""
    summaries = await _fetch_entry_summaries([pdb_id])
    return summaries[0] if summaries else {"id": pdb_id.strip().upper(), "error": "not found"}


@mcp.tool()
async def get_entries(pdb_ids: list[str]) -> dict[str, Any]:
    """Fetch metadata summaries for several PDB entries in one Data API request.

    More efficient than calling get_entry repeatedly. Unknown IDs come back with
    an "error": "not found" marker.

    Args:
        pdb_ids: List of 4-character entry IDs, e.g. ["4HHB", "1MBN"].
    """
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique = [pid for pid in pdb_ids if not (pid.upper() in seen or seen.add(pid.upper()))]
    summaries = await _fetch_entry_summaries(unique)
    return {"count": len(summaries), "entries": summaries}


@mcp.tool()
async def get_polymer_entity(entity_id: str) -> dict[str, Any]:
    """Fetch details for one polymer entity (chain/molecule) from the Data API.

    Polymer entity IDs combine an entry and an entity number, e.g. "4HHB_1".
    These are exactly what search_by_sequence returns, so use this to look up the
    description, sequence, length, and source organism of a sequence-search hit.
    """
    eid = entity_id.strip().upper()
    nodes = await _graphql_nodes(queries.build_polymer_entities_query([eid]), "polymer_entities")
    return _polymer_entity_summary(nodes[0]) if nodes else {"id": eid, "error": "not found"}


@mcp.tool()
async def get_chem_comp(comp_id: str) -> dict[str, Any]:
    """Fetch details for a chemical component / ligand from the Data API.

    Component IDs are the short codes used in PDB files, e.g. "HEM" (heme),
    "ATP", "NAG". Returns name, formula, weight, type, SMILES, and InChIKey.
    """
    cid = comp_id.strip().upper()
    nodes = await _graphql_nodes(queries.build_chem_comps_query([cid]), "chem_comps")
    return _chem_comp_summary(nodes[0]) if nodes else {"id": cid, "error": "not found"}


@mcp.tool()
async def data_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an arbitrary GraphQL query against the RCSB Data API.

    Endpoint: https://data.rcsb.org/graphql . Use this escape hatch for Data API
    objects and fields the typed tools don't cover (assemblies, polymer/branched
    instances, UniProt mappings, interfaces, deeply nested annotations, etc.).
    Returns the raw {"data": ..., "errors": ...} payload so query/validation
    errors are visible.

    Root fields include: entry / entries(entry_ids), polymer_entity /
    polymer_entities(entity_ids), assembly / assemblies(assembly_ids),
    chem_comp / chem_comps(comp_ids), uniprot, interface, branched_entity, ...

    Example:
        query='''query($ids:[String!]!){
          assemblies(assembly_ids:$ids){ rcsb_id rcsb_assembly_info{polymer_entity_instance_count} }
        }'''
        variables={"ids": ["4HHB-1"]}

    Args:
        query: A GraphQL query string. Prefer $variables over inlining values.
        variables: Optional dict of GraphQL variables referenced by the query.
    """
    return await _post_graphql(query, variables)


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
