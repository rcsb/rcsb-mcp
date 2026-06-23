"""An MCP server for interrogating Protein Data Bank structures.

Spans three RCSB APIs so an LLM can take a question from discovery through detail:
- DISCOVER: search the Protein Data Bank (https://search.rcsb.org) by keyword,
  structural attribute, sequence, chemistry, 3D shape, or motif.
- INSPECT: fetch entry / entity / assembly / ligand metadata and annotations from
  the Data API (https://data.rcsb.org/graphql).
- RELATE: map alignments and positional annotations between sequence reference
  systems (UniProt, NCBI, PDB entity/instance) via the Sequence Coordinates API
  (https://sequence-coordinates.rcsb.org/graphql).

The Search API returns only identifiers, so search tools optionally enrich entry
hits with metadata from the Data API, and an entry's component ids let the agent
drill top-down into its entities, assemblies, and ligands.

Run locally (stdio, for Claude Desktop / MCP Inspector):
    python -m rcsb_mcp.server
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse

from rcsb_mcp.search_attibutes import SEARCH_ATTRIBUTES
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES
from rcsb_mcp import queries

SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
DATA_GRAPHQL_URL = "https://data.rcsb.org/graphql"
SEQCOORD_GRAPHQL_URL = "https://sequence-coordinates.rcsb.org/graphql"
# Interactive editors — links surfaced in tool responses so a report can show the
# exact query behind each API call (built server-side for correct URL-encoding).
SEARCH_EDITOR_URL = "https://search.rcsb.org/query-editor.html"
DATA_GRAPHIQL_URL = "https://data.rcsb.org/graphiql/index.html"
SEQCOORD_GRAPHIQL_URL = "https://sequence-coordinates.rcsb.org/graphiql/index.html"
USER_AGENT = "rcsb-mcp/0.1 (https://github.com/rcsb/rcsb-mcp)"
TIMEOUT = httpx.Timeout(30.0)

# Attribute catalogs by schema name (see list_pdb_search_attributes).
ATTRIBUTE_CATALOGS = {"structure": SEARCH_ATTRIBUTES, "chemical": CHEMICAL_SEARCH_ATTRIBUTES}

# Gene Ontology resolver (EBI QuickGO) + friendly aspect/namespace aliases.
QUICKGO_SEARCH_URL = "https://www.ebi.ac.uk/QuickGO/services/ontology/go/search"
GO_ASPECTS = {
    "molecular_function": "molecular_function", "function": "molecular_function", "mf": "molecular_function",
    "biological_process": "biological_process", "process": "biological_process", "bp": "biological_process",
    "cellular_component": "cellular_component", "component": "cellular_component",
    "location": "cellular_component", "cc": "cellular_component",
}

# InterPro domain/family resolver (EBI InterPro REST API) + friendly type aliases.
INTERPRO_SEARCH_URL = "https://www.ebi.ac.uk/interpro/api/entry/interpro/"
INTERPRO_TYPES = {
    "domain": "domain", "family": "family",
    "homologous_superfamily": "homologous_superfamily", "superfamily": "homologous_superfamily",
    "repeat": "repeat", "conserved_site": "conserved_site",
    "binding_site": "binding_site", "active_site": "active_site", "ptm": "ptm",
}

# Enzyme Commission (EC) resolver — EBI Search over the IntEnz database (text -> EC number).
INTENZ_SEARCH_URL = "https://www.ebi.ac.uk/ebisearch/ws/rest/intenz"

# Disease resolver — EBI Ontology Lookup Service (OLS4) over MONDO (text -> MONDO id).
OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"

mcp = FastMCP(
    name="rcsb-pdb",
    instructions="""You are an assistant for interrogating Protein Data Bank structures via the
RCSB Search, Data, and Sequence Coordinates APIs. You can:
- DISCOVER structures — find identifiers with the search_* tools (keyword, attribute,
  sequence, chemical, 3D shape, structural/sequence motif), count them (search_count),
  or aggregate them into buckets (search_facets).
- INSPECT structures — fetch detailed properties, experimental info, and annotations with
  the get_* tools; use describe_data_object to discover further fields to request.
- RELATE sequences — map alignments and positional features across PDB, UniProt, and NCBI
  with the seqcoord_* tools.

Interrogation is usually multi-step; chain tools rather than relying on a single call:
- Find then detail: a search returns ids of ONE return_type — batch them into the matching
  get_* tool for details (see "Return types and fetching details" below).
- Top-down: get_entries returns an entry's component ids (rcsb_entry_container_identifiers:
  polymer/non-polymer/branched entity ids and assembly ids) — compose them with the entry id
  and feed them to get_polymer_entities / get_nonpolymer_entities / get_assemblies, etc.
- Cross-reference: map an entry/entity to UniProt or NCBI with seqcoord_alignments, and pull
  positional features with seqcoord_annotations.

Choosing a search tool:
- When the request resolves to a clear attribute and value (e.g. resolution < 2 Å,
  organism = Homo sapiens, method = X-RAY DIFFRACTION, released after a date), prefer a
  STRUCTURED search: if you don't already know the exact attribute path, call
  list_pdb_search_attributes to find it, then use search_by_attribute (or
  search_combined when several conditions apply). This is more precise than keyword search.
- Use search_fulltext only for broad or exploratory keyword lookups where no specific
  attribute and value apply, or when the right search terms aren't yet known.

Other capabilities:
- For "how many ..." questions, use search_count (count only) rather than fetching and
  counting hits.
- For "break down / distribution / per X" questions (e.g. structures per experimental
  method, per release year, per organism), use search_facets to aggregate matches into
  buckets instead of paging through results.
- search_strucmotif finds structures sharing a 3D arrangement of specific residues (a
  geometric motif); this is different from search_by_structure (whole-shape similarity).
- To search chemical-component attributes (chem_comp.*, drugbank_info.*, rcsb_chem_comp_*),
  call list_pdb_search_attributes(schema="chemical") to find the path, then pass chemical=True
  to search_by_attribute / search_combined (usually with return_type="mol_definition").
- For requests about a molecular FUNCTION ("kinase activity"), biological PROCESS ("DNA repair"),
  or cellular COMPONENT / location ("mitochondrial membrane"), first call find_go_terms to resolve
  the phrase to a Gene Ontology id, then search with
  rcsb_polymer_entity_annotation.annotation_lineage.id exact_match "GO:..." (matches the term and
  all its descendants). This is far more precise than keyword search. Prefer terms with a higher
  pdb_entry_count; use the "in" operator with several GO ids to broaden.
- For requests referencing a protein DOMAIN, FAMILY, or fold ("SH2 domain", "immunoglobulin fold",
  "kinase domain"), first call find_interpro_domains to resolve it to an InterPro id, then search
  with rcsb_polymer_entity_annotation.annotation_id exact_match "IPR..." (add .type="InterPro" to be
  explicit; "in" with several IPR ids to broaden). Note: for InterPro use annotation_id (NOT
  annotation_lineage.id — its hierarchy is not expanded). Prefer higher pdb_entry_count.
- For requests about an ENZYME activity / class ("alcohol dehydrogenase", "DNA polymerase", "EC
  3.4.21"), first call find_enzyme_classes to resolve it to an EC number, then search with
  rcsb_polymer_entity.rcsb_ec_lineage.id exact_match "<EC>" (hierarchical: a full EC finds that
  enzyme, a partial EC like "3.4.21" finds the whole sub-subclass; "in" with several to broaden).
  Prefer higher pdb_entry_count.
- For requests about a DISEASE or condition ("cystic fibrosis", "breast cancer"), first call
  find_disease_terms to resolve it to a MONDO id, then search with
  rcsb_uniprot_annotation.annotation_lineage.id exact_match "MONDO:..." (UniProt-based disease
  annotation; lineage matches the disease and its subtypes; "in" with several to broaden).
  Prefer higher pdb_entry_count.

Return types and fetching details:
- Every search returns identifiers of ONE return_type. The six valid types — with an example
  id and the Data API tool that fetches their full details — are:
    entry              whole structure      "4HHB"     -> get_entries
    polymer_entity     one molecule         "4HHB_1"   -> get_polymer_entities
    non_polymer_entity ligand entity        "4HHB_3"   -> get_nonpolymer_entities
    polymer_instance   one chain            "4HHB.A"   -> get_polymer_entity_instances
    assembly           biological assembly  "4HHB-1"   -> get_assemblies
    mol_definition     chemical component   "HEM"      -> get_chem_comps
- The search tools' `enrich` flag auto-attaches entry metadata ONLY when return_type="entry".
  For any other return_type, take the returned ids and call the matching get_* tool above
  (batch all ids into a single call) to get details — do not loop one id at a time.
- The get_* and seqcoord_* tools return a compact default field set. If you need a property
  they don't return, call describe_data_object (Data API) or describe_seqcoord_object
  (Sequence Coordinates) with [into=, query=] to find the exact field path, then pass it to
  the tool's `fields=` argument.
- Every search/Data/Sequence-Coordinates tool response includes a link to the interactive
  query editor for that exact request — `query_editor_url` (search) or `graphiql_url`
  (GraphQL). When you show your work, surface that link verbatim; never construct these
  URLs yourself."""
)


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


def _search_editor_url(body: dict[str, Any]) -> str:
    """Link opening this Search API query body in the RCSB query editor."""
    return f"{SEARCH_EDITOR_URL}?json=" + quote(json.dumps(body, separators=(",", ":")), safe="")


def _graphiql_url(base: str, body: dict[str, Any]) -> str:
    """Link opening this GraphQL query (+ variables) in a GraphiQL editor."""
    url = f"{base}?query=" + quote(body["query"], safe="")
    variables = body.get("variables")
    if variables:
        url += "&variables=" + quote(json.dumps(variables, separators=(",", ":")), safe="")
    return url


# --------------------------------------------------------------------------- #
# GraphQL schema introspection (powers describe_data_object / describe_seqcoord_object)
# --------------------------------------------------------------------------- #
# Cached per endpoint so repeated describe_* calls don't re-hit the service. Each
# schema is effectively static per process.
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}
_TYPE_REF = "type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"


def _unwrap_type(type_ref: dict[str, Any] | None) -> tuple[str | None, str | None, bool]:
    """Unwrap a GraphQL type reference to (named_type, named_kind, is_list)."""
    is_list = False
    while type_ref:
        kind = type_ref.get("kind")
        if kind == "LIST":
            is_list = True
        if kind not in ("LIST", "NON_NULL"):
            return type_ref.get("name"), kind, is_list
        type_ref = type_ref.get("ofType")
    return None, None, is_list


def _field_descriptor(f: dict[str, Any]) -> dict[str, Any]:
    """Flatten one introspected field into {name, kind, type, list, description}."""
    name, kind, is_list = _unwrap_type(f.get("type"))
    return {
        "name": f.get("name"),
        "kind": "scalar" if kind in ("SCALAR", "ENUM") else "object",
        "type": name,
        "list": is_list,
        "description": f.get("description") or None,
    }


async def _root_field_types(url: str = DATA_GRAPHQL_URL) -> dict[str, str]:
    """Map each root Query field -> its (unwrapped) return type name, for one endpoint. Cached."""
    cache = _SCHEMA_CACHE.setdefault(url, {})
    if "root_types" not in cache:
        q = "{ __schema { queryType { fields { name %s } } } }" % _TYPE_REF
        payload = await _post_graphql(q, url=url)
        fields = (((payload.get("data") or {}).get("__schema") or {})
                  .get("queryType") or {}).get("fields") or []
        cache["root_types"] = {f["name"]: _unwrap_type(f["type"])[0] for f in fields}
    return cache["root_types"]


async def _type_fields(type_name: str, url: str = DATA_GRAPHQL_URL) -> list[dict[str, Any]]:
    """Introspect one type's fields (name/type/description) on one endpoint. Cached per type."""
    cache = _SCHEMA_CACHE.setdefault(url, {}).setdefault("types", {})
    if type_name not in cache:
        q = '{ __type(name: "%s") { fields { name description %s } } }' % (type_name, _TYPE_REF)
        payload = await _post_graphql(q, url=url)
        t = (payload.get("data") or {}).get("__type")
        cache[type_name] = (t or {}).get("fields") or []
    return cache[type_name]


async def _describe_object(
    root_field: str, url: str, into: str | None, query: str | None
) -> dict[str, Any]:
    """Introspect the type returned by `root_field` on `url`; walk `into`; filter by `query`.

    Shared by describe_data_object and describe_seqcoord_object.
    """
    type_name = (await _root_field_types(url)).get(root_field)
    if not type_name:
        raise ValueError(f"could not resolve a GraphQL type for root field {root_field!r}")
    path = [type_name]
    for seg in (into.split(".") if into else []):
        seg = seg.strip()
        if not seg:
            continue
        match = next((f for f in await _type_fields(type_name, url) if f.get("name") == seg), None)
        if match is None:
            raise ValueError(f"field {seg!r} not found on type {type_name!r}")
        nxt, kind, _ = _unwrap_type(match.get("type"))
        if kind in ("SCALAR", "ENUM"):
            raise ValueError(f"field {seg!r} is a scalar ({nxt}); nothing to drill into")
        type_name = nxt
        path.append(type_name)
    fields = [_field_descriptor(f) for f in await _type_fields(type_name, url)]
    if query and query.strip():
        ql = query.strip().lower()
        fields = [
            d for d in fields
            if ql in (d["name"] or "").lower() or ql in (d["description"] or "").lower()
        ]
    return {
        "graphql_type": type_name,
        "path": " -> ".join(path),
        "field_count": len(fields),
        "fields": fields,
    }


async def _query_batch(
    object_key: str, ids: list[str], fields: str | None
) -> dict[str, Any]:
    """Fetch a batch Data API object, returning {count, <object>: [...], not_found?}.

    The API silently drops unknown ids, so we report which requested ids did
    not come back. Returned field selections are passed through as-is.
    """
    spec = queries.DATA_OBJECTS[object_key]
    body = queries.build_data_query(object_key, ids, fields)
    nodes = await _graphql_field(body, spec.root_field)
    # Unknown ids are either dropped or returned as null depending on the field.
    nodes = [n for n in (nodes or []) if n is not None]
    returned = {str(n.get("rcsb_id", "")).upper() for n in nodes}
    requested = [str(i).strip().upper() for i in ids if str(i).strip()]
    missing = [i for i in requested if i not in returned]
    result: dict[str, Any] = {"count": len(nodes), spec.root_field: nodes}
    if missing:
        result["not_found"] = missing
    result["graphiql_url"] = _graphiql_url(DATA_GRAPHIQL_URL, body)
    return result


async def _query_single(
    object_key: str, id_value: Any, fields: str | None
) -> dict[str, Any]:
    """Fetch a singleton Data API object, or a not-found marker."""
    spec = queries.DATA_OBJECTS[object_key]
    body = queries.build_data_query(object_key, id_value, fields)
    node = await _graphql_field(body, spec.root_field)
    if node is None:
        return {"id": id_value, "error": "not found"}
    return {**node, "graphiql_url": _graphiql_url(DATA_GRAPHIQL_URL, body)}


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


def _format(
    raw: dict[str, Any], enriched: list[dict[str, Any]] | None, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    hits = [
        {"id": r["identifier"], "score": round(r.get("score", 0.0), 3)}
        for r in raw.get("result_set", [])
    ]
    result = {"total_count": raw.get("total_count", 0), "returned": len(hits), "hits": hits}
    if enriched is not None:
        result["details"] = enriched
    if body is not None:
        result["query_editor_url"] = _search_editor_url(body)
    return result


def _format_facet(facet: dict[str, Any]) -> dict[str, Any]:
    """Normalize one facet from a search response (bucket list or single metric)."""
    if "buckets" in facet:
        buckets = []
        for b in facet.get("buckets") or []:
            bucket = {"label": b.get("label"), "population": b.get("population")}
            if b.get("facets"):  # nested sub-facets
                bucket["facets"] = [_format_facet(f) for f in b["facets"]]
            buckets.append(bucket)
        return {"name": facet.get("name"), "buckets": buckets}
    # cardinality / single-value metric facet
    return {"name": facet.get("name"), "value": facet.get("value")}


def _format_facets(raw: dict[str, Any], body: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "total_count": raw.get("total_count", 0),
        "facets": [_format_facet(f) for f in raw.get("facets", [])],
    }
    if body is not None:
        result["query_editor_url"] = _search_editor_url(body)
    return result


async def _annotation_pdb_count(attribute: str, value: str) -> int | None:
    """Count PDB entries whose polymer-entity annotation `attribute` equals `value`. Best-effort."""
    body = queries.build_count_query(
        filters=[{"attribute": attribute, "operator": "exact_match", "value": value}],
        return_type="entry",
    )
    try:
        raw = await _post_search(body)
        return raw.get("total_count", 0)
    except httpx.HTTPError:
        return None


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

    Best for broad or exploratory keyword lookups. When the request resolves to a
    clear attribute and value (resolution, organism, experimental method, ligand,
    release date, sequence length, ...), prefer `search_by_attribute` (or
    `search_combined`) instead — call `list_pdb_search_attributes` first to find the
    exact attribute path and operators. Attribute search is more precise and avoids
    spurious keyword matches.

    Args:
        query: Free-text search terms. Quote multi-word phrases for exact match.
        return_type: What to return (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition (see the
            "Return types and fetching details" note in the server instructions).
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
    return _format(raw, enriched, body)

@mcp.tool()
async def list_pdb_search_attributes(
    query: str | None = None, schema: str = "structure"
) -> list[dict[str, Any]]:
    """Discover the RCSB PDB Search schema: attribute paths, value types, and operators.

    Call this FIRST whenever the request resolves to a clear attribute and value but
    you don't already know the exact attribute path. Pick the matching attribute here,
    then run `search_by_attribute` (or `search_combined`). Prefer this structured path
    over `search_fulltext` whenever a specific attribute and value apply.

    Each returned attribute includes:
    - attribute: RCSB/PDB attribute path, e.g. "rcsb_entry_info.resolution_combined"
    - type: value type — string, number, integer, or date
    - operators: supported query operators (e.g. exact_match, greater, range, exists)
    - description: human-readable description

    Args:
        query: Optional case-insensitive keyword to filter the catalog, matched against
            the attribute path and description. Omit to return everything.
            e.g. query="resolution", query="organism".
        schema: Which attribute catalog to search:
            - "structure" (default, ~677 attrs): entry/entity/assembly/instance attributes
              for structure searches. Use with search_by_attribute / search_combined.
            - "chemical" (~57 attrs): chemical-component attributes (chem_comp.*,
              drugbank_info.*, rcsb_chem_comp_*). To search these, pass chemical=True to
              search_by_attribute / search_combined (usually return_type="mol_definition").

    Returns:
        Matching searchable attributes (all of them when query is omitted).
    """
    try:
        catalog = ATTRIBUTE_CATALOGS[schema]
    except KeyError:
        raise ValueError(f'schema must be one of {sorted(ATTRIBUTE_CATALOGS)}') from None
    if not query or not query.strip():
        return catalog
    q = query.strip().lower()
    return [
        a for a in catalog
        if q in a["attribute"].lower() or q in (a.get("description") or "").lower()
    ]


@mcp.tool()
async def find_go_terms(
    query: str,
    namespace: str | None = None,
    limit: int = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text function / process / location to Gene Ontology (GO) terms,
    so you can run precise GO-based PDB searches instead of keyword guessing.

    Use this whenever a request involves a molecular FUNCTION (what a protein does, e.g.
    "kinase activity"), a biological PROCESS (e.g. "DNA repair"), or a cellular
    COMPONENT / location (e.g. "mitochondrial membrane"). Resolve the phrase to a GO id
    here, then search by it.

    To search by a resolved GO id (attributes are rcsb_polymer_entity_annotation.*;
    return_type is usually "entry" or "polymer_entity"):
    - PREFER `rcsb_polymer_entity_annotation.annotation_lineage.id` exact_match "GO:..." —
      matches the term AND all of its more-specific descendants (e.g. "kinase activity"
      also catches "protein serine/threonine kinase activity"). Best for functional queries.
    - Use `rcsb_polymer_entity_annotation.annotation_id` exact_match "GO:..." for ONLY that
      exact term. Optionally add a `.type` = "GO" filter to be explicit.

    Args:
        query: Free-text function / process / location, e.g. "kinase activity", "DNA repair".
        namespace: Optional GO aspect to restrict to — "molecular_function" (aka "function"),
            "biological_process" ("process"), or "cellular_component" ("location"/"component").
        limit: Max GO terms to return (1-25).
        with_pdb_counts: If true (default), annotate each term with pdb_entry_count (PDB
            entries carrying it, via annotation_lineage.id) so you can prefer well-represented
            terms and avoid empty searches.

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
    limit = max(1, min(limit, 25))
    # Over-fetch when filtering by aspect so the post-filter still fills `limit`.
    fetch = min(limit * 5, 50) if aspect else limit
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    ) as client:
        resp = await client.get(QUICKGO_SEARCH_URL, params={"query": query, "limit": fetch, "page": 1})
    resp.raise_for_status()
    results = resp.json().get("results") or []
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
    return {"query": query, "namespace": aspect, "count": len(terms), "terms": terms}


@mcp.tool()
async def find_interpro_domains(
    query: str,
    entry_type: str | None = None,
    limit: int = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text protein domain / family description to InterPro entries, for
    precise InterPro-based PDB searches instead of keyword guessing.

    Use this when a request references a protein DOMAIN, FAMILY, or fold (e.g. "SH2 domain",
    "immunoglobulin fold", "protein kinase domain", "Rossmann fold"). Resolve the phrase to an
    InterPro accession (IPRxxxxxx) here, then search by it:
    `rcsb_polymer_entity_annotation.annotation_id` exact_match "IPRxxxxxx" (add a
    `.type` = "InterPro" filter to be explicit; use the `in` operator with several IPR ids to
    broaden). Unlike GO, use annotation_id — InterPro's hierarchy is not expanded by lineage.

    Args:
        query: Free-text domain/family name, e.g. "SH2 domain", "immunoglobulin".
        entry_type: Optional InterPro type filter — one of domain, family,
            homologous_superfamily (aka superfamily), repeat, conserved_site, binding_site,
            active_site, ptm. Omit to return all types.
        limit: Max entries to return (1-25).
        with_pdb_counts: If true (default), annotate each entry with pdb_entry_count (PDB
            entries carrying it) so you can prefer well-represented entries and avoid empty searches.

    Returns:
        {query, entry_type, count, entries:[{id, name, type, pdb_entry_count?}]}.
    """
    etype = None
    if entry_type:
        etype = INTERPRO_TYPES.get(entry_type.strip().lower())
        if etype is None:
            raise ValueError(f"entry_type must be one of {sorted(set(INTERPRO_TYPES.values()))}")
    limit = max(1, min(limit, 25))
    params: dict[str, Any] = {"search": query, "page_size": limit}
    if etype:
        params["type"] = etype
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    ) as client:
        resp = await client.get(INTERPRO_SEARCH_URL, params=params)
    resp.raise_for_status()
    results = resp.json().get("results") or []
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
    return {"query": query, "entry_type": etype, "count": len(entries), "entries": entries}


@mcp.tool()
async def find_enzyme_classes(
    query: str,
    limit: int = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text enzyme / reaction description to Enzyme Commission (EC) numbers,
    for precise EC-based PDB searches instead of keyword guessing.

    Use this when a request references an enzyme activity or class (e.g. "alcohol dehydrogenase",
    "protein tyrosine kinase", "DNA polymerase"). Resolve the phrase to an EC number here, then
    search by it:
    `rcsb_polymer_entity.rcsb_ec_lineage.id` exact_match "<EC>" — EC is hierarchical and this
    matches the number AND its descendants, so a full EC ("1.1.1.1") finds that exact enzyme while
    a partial EC ("3.4.21") finds the whole sub-subclass. Use the `in` operator with several EC
    numbers to broaden.

    Args:
        query: Free-text enzyme / reaction, e.g. "alcohol dehydrogenase", "protein kinase".
        limit: Max EC numbers to return (1-25).
        with_pdb_counts: If true (default), annotate each with pdb_entry_count (PDB entries carrying
            it, via rcsb_ec_lineage.id) so you can prefer well-represented enzyme classes.

    Returns:
        {query, count, enzymes:[{ec, name, pdb_entry_count?}]}.
    """
    limit = max(1, min(limit, 25))
    # Over-fetch a little so dropping transferred/deleted entries still fills `limit`.
    fetch = min(limit + 5, 30)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    ) as client:
        resp = await client.get(
            INTENZ_SEARCH_URL, params={"query": query, "format": "json", "size": fetch, "fields": "name"}
        )
    resp.raise_for_status()
    enzymes: list[dict[str, Any]] = []
    for e in resp.json().get("entries") or []:
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
    return {"query": query, "count": len(enzymes), "enzymes": enzymes}


@mcp.tool()
async def find_disease_terms(
    query: str,
    limit: int = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text disease / condition to MONDO ontology ids, for precise
    disease-based PDB searches instead of keyword guessing.

    Use this when a request references a disease or condition (e.g. "cystic fibrosis",
    "breast cancer", "Parkinson disease"). Resolve the phrase to a MONDO id here, then
    search by it:
    `rcsb_uniprot_annotation.annotation_lineage.id` exact_match "MONDO:..." — disease
    annotations are UniProt-derived, and lineage matches the term AND its subtypes (e.g.
    "cancer" catches specific cancers). Use the `in` operator with several MONDO ids to broaden.

    Note this attribute is rcsb_uniprot_annotation.* (UniProt-based), unlike the GO/InterPro
    resolvers which use rcsb_polymer_entity_annotation.*.

    Args:
        query: Free-text disease / condition, e.g. "cystic fibrosis", "breast cancer".
        limit: Max MONDO terms to return (1-25).
        with_pdb_counts: If true (default), annotate each with pdb_entry_count (PDB entries
            carrying it, via annotation_lineage.id) so you can prefer well-represented diseases.

    Returns:
        {query, count, diseases:[{id, name, pdb_entry_count?}]}.
    """
    limit = max(1, min(limit, 25))
    # Over-fetch so de-duplication and obsolete-filtering still fill `limit`.
    fetch = min(limit * 3, 50)
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    ) as client:
        resp = await client.get(
            OLS_SEARCH_URL,
            params={"q": query, "ontology": "mondo", "rows": fetch,
                    "fieldList": "obo_id,label,is_obsolete"},
        )
    resp.raise_for_status()
    docs = ((resp.json().get("response") or {}).get("docs")) or []
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
    return {"query": query, "count": len(diseases), "diseases": diseases}


@mcp.tool()
async def search_by_attribute(
    attribute: str,
    operator: str,
    value: str | int | float | list | dict | None = None,
    return_type: str = "entry",
    limit: int = 10,
    enrich: bool = True,
    negation: bool = False,
    case_sensitive: bool = False,
    group_by_identity: int | None = None,
    chemical: bool = False,
) -> dict[str, Any]:
    """Search by a specific structural attribute — preferred over search_fulltext
    whenever the request resolves to a clear attribute and value. If you don't know
    the exact attribute path or its operators, call `list_pdb_search_attributes` first.

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
        attribute: A dotted RCSB attribute path (see the Search API attribute list: https://search.rcsb.org/structure-search-attributes.html). The `list_pdb_search_attributes` tool can be used to retrieve the list of all available attributes.
        operator: Operators are TYPE-SPECIFIC — use one of the operators that
            list_pdb_search_attributes reports for this attribute. As a guide:
            strings use contains_words/contains_phrase (free text) or exact_match/in
            (enumerated values); numbers and dates use greater, greater_or_equal, less,
            less_or_equal, equals, range; any type supports exists.
        value: The comparison value — a string/number, a list (for the "in" operator),
            or a range object {from, to, include_lower, include_upper} (bounds are
            EXCLUSIVE unless include_lower/include_upper are true). Omit for "exists".
            Dates take a full ISO-8601 timestamp, e.g. "2024-01-01T00:00:00Z".
        return_type: What to return (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition (see the
            server instructions). E.g. return_type="entry" with a ligand attribute
            finds the structures that contain it.
        limit: Max hits (1-100).
        enrich: Attach entry metadata when return_type is "entry".
        negation: Invert the match (e.g. "not Homo sapiens").
        case_sensitive: Match the value case-sensitively (default insensitive).
        group_by_identity: If set (100/95/90/70/50/30), return one representative per
            sequence-identity cluster; forces return_type to "polymer_entity".
        chemical: Set True for a chemical-component attribute (a path from
            list_pdb_search_attributes(schema="chemical"), e.g. "chem_comp.formula_weight").
            Switches to the text_chem service; usually pair with return_type="mol_definition".
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
        chemical=chemical,
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched, body)


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
    chemical: bool = False,
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
        logical_operator: Combine ALL conditions with a single "and" (default) or "or".
            Nested logic like "(A or B) and C" is NOT expressible here — use
            search_advanced with a nested group query for that.
        return_type: What to return (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition (see the
            server instructions).
        limit: Max hits (1-100).
        enrich: Attach title/method/resolution for each entry hit (return_type="entry" only).
        sort_by: Attribute to sort by, e.g. "rcsb_entry_info.resolution_combined".
            Omit to sort by relevance score.
        sort_direction: "asc" or "desc" (default "asc").
        group_by_identity: If set (100/95/90/70/50/30), return one representative per
            sequence-identity cluster; forces return_type to "polymer_entity".
        chemical: Set True when the filters target chemical-component attributes (paths
            from list_pdb_search_attributes(schema="chemical")); switches them to the
            text_chem service. The full_text term always uses full-text search.
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
        chemical=chemical,
    )
    raw = await _post_search(body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched, body)


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
        limit: Max hits (1-100). Returns polymer_entity IDs like "4HHB_1" — fetch their
            details with get_polymer_entities.
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
    return _format(raw, None, body)


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
        match_type: Graph/fingerprint criterion for descriptor queries, one of:
            graph-exact, graph-strict, graph-relaxed (default), graph-relaxed-stereo
            (whole-molecule matches, strict->relaxed = stricter->looser); the
            sub-struct-graph-* variants of each (substructure search); or
            fingerprint-similarity (similar molecules).
        match_subset: Formula queries only — match formulas that merely contain the
            requested atoms.
        return_type: What to return (default "mol_definition" = the chemical component).
            Use return_type="entry" to instead get the PDB structures that contain a
            matching component. Other types from the server instructions also apply.
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
    return _format(raw, None, body)


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
        return_type: What to return; defaults to "assembly" for an assembly reference or
            "polymer_instance" for a chain reference. May be overridden with any of the
            six types (see server instructions).
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
    return _format(raw, None, body)


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
        return_type: What to return (default "polymer_entity"); one of the six types
            (see server instructions). Default hits feed get_polymer_entities.
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
    return _format(raw, None, body)


@mcp.tool()
async def search_advanced(query_body: dict[str, Any]) -> dict[str, Any]:
    """Run a raw RCSB Search API query body (escape hatch).

    Endpoint: https://search.rcsb.org/rcsbsearch/v2/query . The typed search_*
    tools cover the common cases (including search_facets, search_count, and
    search_strucmotif); use this for features they don't expose — return_all_hits,
    group_by "groups", or deeply nested boolean queries. The body must follow the
    Search API query language ({"query": ..., "return_type": ..., "request_options": ...}).
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
    return _format(raw, None, query_body)


@mcp.tool()
async def search_count(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    chemical: bool = False,
    include_computed_models: bool = False,
) -> dict[str, Any]:
    """Return only the NUMBER of matches — use this for "how many ..." questions.

    Far cheaper than fetching hits just to count them. Takes the same conditions as
    search_combined (free text and/or attribute filters). With no conditions it counts
    every structure of `return_type`.

    Examples:
        - "How many human structures?" full_text=None, filters=[{"attribute":
          "rcsb_entity_source_organism.ncbi_scientific_name", "operator":"exact_match",
          "value":"Homo sapiens"}]
        - "How many entries mention CRISPR?" full_text="CRISPR"

    Args:
        full_text: Optional free-text term.
        filters: List of {attribute, operator, value} dicts (see search_by_attribute).
        logical_operator: Combine conditions with "and" (default) or "or".
        return_type: What to count (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition.
        chemical: Set True when filters target chemical-component attributes (text_chem).
        include_computed_models: Also count computed structure models (AlphaFold etc.).
    """
    body = queries.build_count_query(
        full_text=full_text,
        filters=filters,
        logical_operator=logical_operator,
        return_type=return_type,
        chemical=chemical,
        include_computed=include_computed_models,
    )
    raw = await _post_search(body)
    return {"total_count": raw.get("total_count", 0), "query_editor_url": _search_editor_url(body)}


@mcp.tool()
async def search_facets(
    facets: list[dict[str, Any]],
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    chemical: bool = False,
    include_computed_models: bool = False,
) -> dict[str, Any]:
    """Aggregate matches into buckets/statistics — for "distribution / breakdown / per X"
    questions (e.g. structures per experimental method, per release year, per organism).

    Returns {total_count, facets:[{name, buckets:[{label, population}]}]} and NO hit list.
    Takes the same optional conditions as search_combined to first narrow the set; with no
    conditions the facets run over all structures.

    Each entry in `facets` is a dict:
        {"name": <label>, "aggregation_type": <type>, "attribute": <attribute path>, ...}
    aggregation_type and its extra keys:
        - "terms": count entries per distinct value. Optional: min_interval_population (drop
          small buckets), max_num_intervals.
        - "histogram": numeric buckets — requires "interval" (bucket width, a number).
        - "date_histogram": calendar buckets — requires "interval": "year".
        - "range" / "date_range": requires "ranges": [{"from": x, "to": y}, ...] (from
          inclusive, to exclusive; dates as ISO strings).
        - "cardinality": count of distinct values (returns {name, value}).
    A facet may carry a nested "facets" list to sub-aggregate within each bucket.

    Examples:
        - Experimental methods breakdown of all entries:
          facets=[{"name":"Methods","aggregation_type":"terms","attribute":"exptl.method"}]
        - Human structures by release year:
          full_text=None,
          filters=[{"attribute":"rcsb_entity_source_organism.ncbi_scientific_name",
                    "operator":"exact_match","value":"Homo sapiens"}],
          facets=[{"name":"ByYear","aggregation_type":"date_histogram",
                   "attribute":"rcsb_accession_info.initial_release_date","interval":"year"}]
        - Resolution distribution (0.5 Å bins):
          facets=[{"name":"Res","aggregation_type":"histogram",
                   "attribute":"rcsb_entry_info.resolution_combined","interval":0.5}]

    Args:
        facets: One or more facet specs (see above). At least one is required.
        full_text: Optional free-text term to narrow the set before aggregating.
        filters: Optional list of {attribute, operator, value} dicts.
        logical_operator: Combine conditions with "and" (default) or "or".
        return_type: What to aggregate over (default "entry"); one of the six types
            (see server instructions).
        chemical: Set True when filters target chemical-component attributes (text_chem).
        include_computed_models: Also include computed structure models (AlphaFold etc.).
    """
    body = queries.build_facet_query(
        facets,
        full_text=full_text,
        filters=filters,
        logical_operator=logical_operator,
        return_type=return_type,
        chemical=chemical,
        include_computed=include_computed_models,
    )
    raw = await _post_search(body)
    return _format_facets(raw, body)


@mcp.tool()
async def search_strucmotif(
    entry_id: str,
    residue_ids: list[dict[str, Any]],
    backbone_distance_tolerance: int = 1,
    side_chain_distance_tolerance: int = 1,
    angle_tolerance: int = 1,
    rmsd_cutoff: float = 2.0,
    atom_pairing_scheme: str = "SIDE_CHAIN",
    motif_pruning_strategy: str = "KRUSKAL",
    return_type: str = "polymer_entity",
    limit: int = 10,
) -> dict[str, Any]:
    """Find structures containing a 3D STRUCTURAL MOTIF — a geometric arrangement of
    specific residues — like the one in a reference structure.

    This is geometry-based and DIFFERENT from search_by_structure (whole-shape similarity)
    and from search_by_seqmotif (sequence pattern). Use it for catalytic triads, binding
    sites, metal-coordination geometries, etc.

    Args:
        entry_id: Reference PDB entry defining the motif, e.g. "2MNR".
        residue_ids: 2-10 residues defining the motif, each a dict
            {"label_asym_id": <chain>, "label_seq_id": <int>, "struct_oper_id"?: <str>}.
            IMPORTANT: these are the mmCIF *label* identifiers (the internal numbering),
            which often DIFFER from the author residue numbers seen in papers/the PDB
            site. If you only have author numbering, resolve the label_asym_id/label_seq_id
            first (e.g. via get_polymer_entity_instances) — author numbers give wrong/no hits.
            Example (enolase catalytic residues):
            [{"label_asym_id":"A","label_seq_id":162},
             {"label_asym_id":"A","label_seq_id":193},
             {"label_asym_id":"A","label_seq_id":219}]
        backbone_distance_tolerance: Backbone distance tolerance in Å, integer 0-3 (default 1).
        side_chain_distance_tolerance: Side-chain distance tolerance in Å, integer 0-3 (default 1).
        angle_tolerance: Angle tolerance in multiples of 20°, integer 0-3 (default 1).
        rmsd_cutoff: Maximum RMSD of accepted hits (default 2.0).
        atom_pairing_scheme: ALL, BACKBONE, SIDE_CHAIN (default), or PSEUDO_ATOMS.
        motif_pruning_strategy: NONE or KRUSKAL (default).
        return_type: What to return (default "polymer_entity"); one of the six types
            (see server instructions).
        limit: Max hits (1-100).
    """
    limit = max(1, min(limit, 100))
    body = queries.build_strucmotif_query(
        entry_id,
        residue_ids,
        backbone_distance_tolerance=backbone_distance_tolerance,
        side_chain_distance_tolerance=side_chain_distance_tolerance,
        angle_tolerance=angle_tolerance,
        rmsd_cutoff=rmsd_cutoff,
        atom_pairing_scheme=atom_pairing_scheme,
        motif_pruning_strategy=motif_pruning_strategy,
        return_type=return_type,
        rows=limit,
    )
    raw = await _post_search(body)
    return _format(raw, None, body)


# --------------------------------------------------------------------------- #
# Data API tools — one per GraphQL root field (singular forms are covered by
# their batch tool, called with a single-element list). Each returns the raw
# selected GraphQL node(s); pass `fields` to override the curated default
# selection with your own GraphQL sub-selection (omit the surrounding braces).
# --------------------------------------------------------------------------- #
@mcp.tool()
async def describe_data_object(
    object_key: str, into: str | None = None, query: str | None = None
) -> dict[str, Any]:
    """Discover the fields available on a Data API object, from the live GraphQL schema.

    Use this to find exactly what to request in a get_* tool's `fields=` argument (or
    in data_graphql). The get_* default selections are compact summaries, but the
    underlying GraphQL types have far more (e.g. CoreEntry has ~100 fields). This tool
    walks the schema so you can build a precise selection instead of guessing.

    Workflow: describe_data_object("entries") -> spot a nested object field such as
    "rcsb_entry_info" -> describe_data_object("entries", into="rcsb_entry_info") to list
    its leaves -> call get_entries(ids, fields="rcsb_entry_info{ ... }").

    Each returned field has:
    - name: the GraphQL field name
    - kind: "scalar" (a leaf you can select directly) or "object" (drill in with `into`)
    - type: the field's GraphQL type name
    - list: whether the field returns a list
    - description: schema description, when present

    Args:
        object_key: Which object to describe — a key matching the get_* tools, e.g.
            "entries", "polymer_entities", "assemblies", "chem_comps", "interfaces",
            "uniprot", ... (entry_annotations/entry_exp_info also map to the entry type).
        into: Optional dot-path of nested object field(s) to drill into, e.g.
            "rcsb_entry_info" or "polymer_entities.rcsb_polymer_entity".
        query: Optional case-insensitive keyword to filter fields by name/description.

    Returns:
        {object_key, graphql_type, path, field_count, fields:[...]}.
    """
    if object_key not in queries.DATA_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(queries.DATA_OBJECTS)}")
    root_field = queries.DATA_OBJECTS[object_key].root_field
    return {
        "object_key": object_key,
        **await _describe_object(root_field, DATA_GRAPHQL_URL, into, query),
    }


@mcp.tool()
async def get_entries(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch metadata for one or more PDB entries (title, method, resolution, size,
    dates, primary citation, and publication abstract).

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]. Unknown IDs are
    listed under "not_found". For a single entry pass a one-element list.

    The response also lists the entry's component ids under
    rcsb_entry_container_identifiers — use these to drill into the structure. They are
    bare numbers; compose them with the entry id to call the matching get_* tool:
    polymer_entity_ids/non_polymer_entity_ids "N" -> "<ENTRY>_N" (get_polymer_entities /
    get_nonpolymer_entities); assembly_ids "N" -> "<ENTRY>-N" (get_assemblies).

    For fields beyond this summary, use describe_data_object("entries") to find the
    path and pass it via `fields`.
    """
    return await _query_batch("entries", entry_ids, fields)

@mcp.tool()
async def get_entry_annotations(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological and functional annotations for one or more PDB entries, including Gene Ontology terms (molecular function, biological process, and cellular component), protein domain classifications, disease associations, antibody annotations, gene product information, and other biological annotations.

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]. Unknown IDs are
    listed under "not_found". For a single entry pass a one-element list.
    """
    return await _query_batch("entry_annotations", entry_ids, fields)

@mcp.tool()
async def get_entry_exp_info(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch detailed experimental conditions and structure-determination metadata for one or more PDB entries, including sample temperature, pH, pressure, experimental method, diffraction data, and other reported experimental parameters.

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]. Unknown IDs are
    listed under "not_found". For a single entry pass a one-element list.
    """
    return await _query_batch("entry_exp_info", entry_ids, fields)


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
    payload = await _post_graphql(query, variables)
    if isinstance(payload, dict):
        payload["graphiql_url"] = _graphiql_url(
            DATA_GRAPHIQL_URL, {"query": query, "variables": variables}
        )
    return payload


# --------------------------------------------------------------------------- #
# Sequence Coordinates API tools (https://sequence-coordinates.rcsb.org/graphql)
# Map alignments and positional annotations between sequence reference systems
# (UniProt, NCBI, PDB entity/instance). Each returns the raw selected GraphQL
# node(s); pass `fields` to override the default selection (use
# describe_seqcoord_object to discover what to request).
# --------------------------------------------------------------------------- #
# The five Sequence Coordinates root fields, for describe_seqcoord_object.
SEQCOORD_OBJECTS = {
    "alignments", "annotations",
    "group_alignments", "group_annotations", "group_annotations_summary",
}


@mcp.tool()
async def describe_seqcoord_object(
    object_key: str, into: str | None = None, query: str | None = None
) -> dict[str, Any]:
    """Discover the fields available on a Sequence Coordinates object, from the live schema.

    The Sequence Coordinates analogue of describe_data_object. The seqcoord_* tools
    return a compact default selection; use this to find what else you can request via
    their `fields=` argument (or via seqcoord_graphql).

    Workflow: describe_seqcoord_object("alignments") -> spot a nested object such as
    "target_alignments" -> describe_seqcoord_object("alignments", into="target_alignments")
    to list its leaves -> call seqcoord_alignments(..., fields="target_alignments{ ... }").

    Each returned field has name, kind ("scalar" leaf or "object" — drill in with `into`),
    type, list (whether it's a list), and description (when present).

    Args:
        object_key: A Sequence Coordinates root field — one of: alignments, annotations,
            group_alignments, group_annotations, group_annotations_summary. (alignments and
            group_alignments share the SequenceAlignments type; the annotation roots share
            SequenceAnnotations.)
        into: Optional dot-path of nested object field(s) to drill into, e.g.
            "target_alignments" or "features.feature_positions".
        query: Optional case-insensitive keyword to filter fields by name/description.

    Returns:
        {object_key, graphql_type, path, field_count, fields:[...]}.
    """
    if object_key not in SEQCOORD_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(SEQCOORD_OBJECTS)}")
    return {
        "object_key": object_key,
        **await _describe_object(object_key, SEQCOORD_GRAPHQL_URL, into, query),
    }


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
    graphiql_url = _graphiql_url(SEQCOORD_GRAPHIQL_URL, body)
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
            "graphiql_url": graphiql_url,
        }
    return {**data, "graphiql_url": graphiql_url}


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
    return {
        "count": len(data),
        "annotations": data,
        "graphiql_url": _graphiql_url(SEQCOORD_GRAPHIQL_URL, body),
    }


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
    graphiql_url = _graphiql_url(SEQCOORD_GRAPHIQL_URL, body)
    data = await _graphql_field(body, "group_alignments", url=SEQCOORD_GRAPHQL_URL)
    if data is None:
        return {"group_id": group_id, "error": "no alignment found", "graphiql_url": graphiql_url}
    return {**data, "graphiql_url": graphiql_url}


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
    return {
        "count": len(data),
        "annotations": data,
        "graphiql_url": _graphiql_url(SEQCOORD_GRAPHIQL_URL, body),
    }


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
    payload = await _post_graphql(query, variables, url=SEQCOORD_GRAPHQL_URL)
    if isinstance(payload, dict):
        payload["graphiql_url"] = _graphiql_url(
            SEQCOORD_GRAPHIQL_URL, {"query": query, "variables": variables}
        )
    return payload


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    """Liveness/readiness probe endpoint — 200 OK when the HTTP server is up."""
    return PlainTextResponse("ok")


def create_app():
    """ASGI app factory for HTTP deployment (the Docker image).

    Serves the MCP over the streamable-HTTP transport at POST /mcp (plus GET /healthz
    for Kubernetes probes). Built only when called, so importing this module for local
    stdio use (main() / the `rcsb-mcp` console script) constructs nothing.
    Run with: uvicorn rcsb_mcp.server:create_app --factory
    """
    return mcp.streamable_http_app()


def main() -> None:
    mcp.run()  # stdio transport by default (local clients / console script)


if __name__ == "__main__":
    main()
