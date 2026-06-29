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
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.responses import PlainTextResponse

from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES
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

# Every tool in this server is a read-only query against public RCSB/EBI web
# APIs: it never mutates state, repeated calls are safe (idempotent), and it
# reaches external services (open world). Shared by all @mcp.tool decorators.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

# --------------------------------------------------------------------------- #
# Parameter type aliases — closed value sets become JSON-schema enums and numeric
# ranges become minimum/maximum, so each tool's inputSchema advertises its
# constraints to the client. These mirror the validated sets in queries.py; the
# builders keep their own checks as a backstop for direct (non-MCP) callers.
# --------------------------------------------------------------------------- #
ReturnType = Literal[
    "entry", "polymer_entity", "non_polymer_entity",
    "polymer_instance", "assembly", "mol_definition",
]
TextOperator = Literal[
    "exact_match", "in", "contains_words", "contains_phrase", "greater",
    "greater_or_equal", "less", "less_or_equal", "equals", "range", "exists",
]
SequenceType = Literal["protein", "dna", "rna"]
ChemMatchType = Literal[
    "graph-exact", "graph-strict", "graph-relaxed", "graph-relaxed-stereo",
    "fingerprint-similarity", "sub-struct-graph-exact", "sub-struct-graph-strict",
    "sub-struct-graph-relaxed", "sub-struct-graph-relaxed-stereo",
]
DescriptorType = Literal["SMILES", "InChI"]
ChemQueryType = Literal["descriptor", "formula"]
SeqmotifPatternType = Literal["simple", "prosite", "regex"]
AtomPairingScheme = Literal["ALL", "BACKBONE", "SIDE_CHAIN", "PSEUDO_ATOMS"]
MotifPruningStrategy = Literal["NONE", "KRUSKAL"]
LogicalOperator = Literal["and", "or"]
SortDirection = Literal["asc", "desc"]
GroupBy = Literal["seqid_30", "seqid_50", "seqid_70", "seqid_90", "seqid_95", "uniprot"]
GroupByRanking = Literal[
    "resolution", "released_date", "entity_residue_count", "score", "coverage",
]
AttributeSchema = Literal["structure", "chemical"]
SequenceRef = Literal["NCBI_GENOME", "NCBI_PROTEIN", "PDB_ENTITY", "PDB_INSTANCE", "UNIPROT"]
GroupRef = Literal["MATCHING_UNIPROT_ACCESSION", "SEQUENCE_IDENTITY"]
AnnotationRef = Literal["PDB_ENTITY", "PDB_INSTANCE", "PDB_INTERFACE", "UNIPROT"]

# Numeric bounds (Annotated so the parameter default stays on the signature).
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]
ResolverLimit = Annotated[int, Field(ge=1, le=25)]
Tolerance = Annotated[int, Field(ge=0, le=3)]


class AttributeFilter(BaseModel):
    """One structured attribute condition — a single `text`/`text_chem` terminal.

    A list of these expresses a flat multi-attribute query (combined with one
    AND/OR). Find a path/operators with rcsb_list_pdb_search_attributes.
    """

    attribute: str = Field(
        description="Dotted RCSB attribute path, e.g. 'rcsb_entry_info.resolution_combined'."
    )
    operator: TextOperator = Field(
        description="Type-specific operator (see rcsb_list_pdb_search_attributes): strings use "
        "exact_match/in or contains_words/contains_phrase; numbers/dates use greater/"
        "greater_or_equal/less/less_or_equal/equals/range; any type supports exists."
    )
    value: str | int | float | list | dict | None = Field(
        default=None,
        description="Comparison value; omit for 'exists'. A list for 'in'; a "
        "{from,to,include_lower,include_upper} object for 'range'. A numeric string is "
        "coerced to a number for numeric operators; dates take an ISO-8601 string.",
    )
    negation: bool = Field(default=False, description="Invert the match (NOT).")
    case_sensitive: bool = Field(
        default=False, description="Match the value case-sensitively (default insensitive)."
    )


def _filter_dicts(attributes: list[AttributeFilter] | None) -> list[dict[str, Any]] | None:
    """Convert typed AttributeFilter inputs into the plain dicts the builders expect."""
    return [f.model_dump() for f in attributes] if attributes else None

# Hard ceiling for all_hits searches: above this many matches the tool refuses and
# steers to facets/paging, so a broad query can't dump a huge id list into context.
ALL_HITS_MAX = 10000

# Attribute catalogs by schema name (see rcsb_list_pdb_search_attributes).
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

# Organism / taxon resolver — UniProt taxonomy REST (text -> NCBI Taxonomy id). UniProt's
# taxonId IS the NCBI Taxonomy id, which feeds rcsb_entity_source_organism.taxonomy_lineage.id.
UNIPROT_TAXONOMY_SEARCH_URL = "https://rest.uniprot.org/taxonomy/search"

mcp = FastMCP(
    name="rcsb_mcp",
    instructions="""You are an assistant for interrogating Protein Data Bank structures via the
RCSB Search, Data, and Sequence Coordinates APIs. You can:
- DISCOVER structures — find identifiers with the rcsb_search_* tools (keyword, attribute,
  sequence, chemical, 3D shape, structural/sequence motif). Every search response carries
  total_count (the full match count); pass `facets` to any rcsb_search_* tool to get a
  breakdown into buckets instead of hits.
- INSPECT structures — fetch detailed properties, experimental info, and annotations with
  the rcsb_get_* tools; use rcsb_describe_data_object to discover further fields to request.
- RELATE sequences — map alignments and positional features across PDB, UniProt, and NCBI
  with the rcsb_seqcoord_* tools.

Interrogation is usually multi-step; chain tools rather than relying on a single call:
- Find then detail: a search returns ids of ONE return_type — batch them into the matching
  rcsb_get_* tool for details (see "Return types and fetching details" below).
- Top-down: rcsb_get_entries returns an entry's component ids (rcsb_entry_container_identifiers:
  polymer/non-polymer/branched entity ids and assembly ids) — compose them with the entry id
  and feed them to rcsb_get_polymer_entities / rcsb_get_nonpolymer_entities / rcsb_get_assemblies, etc.
- Cross-reference: map an entry/entity to UniProt or NCBI with rcsb_seqcoord_alignments, and pull
  positional features with rcsb_seqcoord_annotations.

Choosing a search tool:
- When the request resolves to a clear attribute and value (e.g. resolution < 2 Å,
  organism = Homo sapiens, method = X-RAY DIFFRACTION, released after a date), prefer a
  STRUCTURED search: if you don't already know the exact attribute path, call
  rcsb_list_pdb_search_attributes to find it, then use rcsb_search_by_attribute (it takes one
  or more attribute conditions combined with a single AND/OR; add a free-text keyword to them
  with rcsb_search_fulltext). This is more precise than a fulltext (keyword) search alone.
- Use rcsb_search_fulltext only for broad or exploratory keyword lookups where no specific
  attribute and value apply, or when the right search terms aren't yet known.
- A protein or gene NAME is a structured attribute, not a keyword — don't default to fulltext.
  For a protein name use rcsb_polymer_entity.rcsb_macromolecular_names_combined.name
  contains_phrase "<name>" (the deposited molecule name; broadest coverage), optionally OR'd with
  rcsb_uniprot_protein.name.value (canonical UniProt name, UniProt-mapped entries only). For a gene
  name/symbol use rcsb_entity_source_organism.rcsb_gene_name.value exact_match "<symbol>". These
  match the actual molecule/gene, not every annotation that mentions the word (e.g. "hemoglobin"
  -> ~750 real structures vs ~9000 fulltext hits). Combine with other attributes in one query; if
  the attribute search returns nothing useful, first try broadening it (contains_words, the
  UniProt name, a synonym) before resorting to fulltext.
- The specialized searches are chosen by INTENT: rcsb_search_by_sequence (sequence similarity),
  rcsb_search_by_chemical (SMILES/InChI/formula), rcsb_search_by_structure (whole 3D shape),
  rcsb_search_by_seqmotif (sequence pattern), rcsb_search_strucmotif (residue geometry). Each also
  accepts optional `attributes` (+ `logical_operator`) to AND/OR structured filters onto the match
  — e.g. sequence-similar AND from human AND resolution < 2 Å — in one call; reach for
  rcsb_search_advanced only to combine several of these services or for nested boolean logic.
- Searches return up to `limit` hits (default 10, max 100) plus pagination fields
  (offset/has_more/next_offset). For more results, re-issue the same query with offset set to
  the response's next_offset — don't just raise limit past 100.
- When the user asks for ALL matches (to enumerate or batch-fetch a complete set), set
  all_hits=True on any rcsb_search_* tool to get the whole set in one call instead of paging.
  It is capped at 10000 hits; above that, narrow the query, or read total_count / pass `facets`
  to summarize, instead.

Other capabilities:
- For "how many ..." questions, do NOT page hits: every search response includes total_count
  (the full match count, not just the returned page). Run the matching rcsb_search_* tool with
  limit=1 and read total_count.
- For "break down / distribution / per X" questions (e.g. structures per experimental method,
  per release year, per organism), pass `facets` to any rcsb_search_* tool to aggregate the
  matches into buckets instead of returning hits; the response is {total_count, facets:[{name,
  buckets:[{label, population}]}]}. Each facet spec is a dict {"name", "aggregation_type",
  "attribute", ...}:
    - "terms": count entries per distinct value. Optional min_interval_population (drop small
      buckets), max_num_intervals.
    - "histogram": numeric buckets — requires "interval" (bucket width, a number).
    - "date_histogram": calendar buckets — requires "interval": "year".
    - "range" / "date_range": requires "ranges": [{"from": x, "to": y}, ...] (from inclusive,
      to exclusive; dates as ISO strings).
    - "cardinality": count of distinct values (returns {name, value}).
  A facet may carry a nested "facets" list to sub-aggregate within each bucket. Example:
  facets=[{"name":"Methods","aggregation_type":"terms","attribute":"exptl.method"}].
- To DE-DUPLICATE redundant hits (one representative per cluster), set group_by on any
  rcsb_search_* tool (requires return_type="polymer_entity"):
  "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95" (cluster by sequence-identity %) or
  "uniprot" (one per UniProt accession). Choose the representative with group_by_ranking
  (resolution / released_date / entity_residue_count / score). When group_by="uniprot", PREFER
  group_by_ranking="coverage" — it keeps the most relevant biological sequence 
  covering the most of the UniProt protein (coverage is valid only with group_by="uniprot").
- rcsb_search_strucmotif finds structures sharing a 3D arrangement of specific residues (a
  geometric motif); this is different from rcsb_search_by_structure (whole-shape similarity).
- To search chemical-component attributes (chem_comp.*, drugbank_info.*, rcsb_chem_comp_*),
  call rcsb_list_pdb_search_attributes(schema="chemical") to find the path, then pass chemical=True
  to rcsb_search_by_attribute / rcsb_search_fulltext (usually with return_type="mol_definition").
- If request refers to assembly / complex / assembled complex / multi-subunit machine / multimer (or any
  other term indicating a structure composed of multiple subunits / proteins), add rcsb_assembly_info.* 
  composition to attributes to the appropiate rcsb_search_* tool:
    - rcsb_assembly_info.polymer_entity_instance_count_protein >= N (total protein chains),
    - rcsb_assembly_info.polymer_entity_count_protein >= M (distinct subunits),
    - rcsb_assembly_info.polymer_composition exact_match "heteromeric protein" | "homomeric protein"
  combine these as needed.
- For requests about a molecular FUNCTION ("kinase activity"), biological PROCESS ("DNA repair"),
  or cellular COMPONENT / location ("mitochondrial membrane"), first call rcsb_find_go_terms to resolve
  the phrase to a Gene Ontology id, then search with
  rcsb_polymer_entity_annotation.annotation_lineage.id exact_match "GO:..." (matches the term and
  all its descendants). This is far more precise than keyword search. Prefer terms with a higher
  pdb_entry_count; use the "in" operator with several GO ids to broaden.
- For requests referencing a protein DOMAIN, FAMILY, or fold ("SH2 domain", "immunoglobulin fold",
  "kinase domain"), first call rcsb_find_interpro_domains to resolve it to an InterPro id, then search
  with rcsb_polymer_entity_annotation.annotation_id exact_match "IPR..." (add .type="InterPro" to be
  explicit; "in" with several IPR ids to broaden). Note: for InterPro use annotation_id (NOT
  annotation_lineage.id — its hierarchy is not expanded). Prefer higher pdb_entry_count.
- For requests about an ENZYME activity / class ("alcohol dehydrogenase", "DNA polymerase", "EC
  3.4.21"), first call rcsb_find_enzyme_classes to resolve it to an EC number, then search with
  rcsb_polymer_entity.rcsb_ec_lineage.id exact_match "<EC>" (hierarchical: a full EC finds that
  enzyme, a partial EC like "3.4.21" finds the whole sub-subclass; "in" with several to broaden).
  Prefer higher pdb_entry_count.
- For requests about a DISEASE or condition ("cystic fibrosis", "breast cancer"), first call
  rcsb_find_disease_terms to resolve it to a MONDO id, then search with
  rcsb_uniprot_annotation.annotation_lineage.id exact_match "MONDO:..." (UniProt-based disease
  annotation; lineage matches the disease and its subtypes; "in" with several to broaden).
  Prefer higher pdb_entry_count.
- For requests restricting by SOURCE ORGANISM or a higher taxon ("human", "mouse", "mammals",
  "bacteria", "Escherichia coli"), first call rcsb_find_organisms to resolve it to an NCBI taxon
  id, then search with rcsb_entity_source_organism.taxonomy_lineage.id exact_match "<taxId>" —
  pass the id as a STRING ("9606", not 9606). The lineage is each entity's full ancestor chain,
  so a species id finds that species and a clade id (e.g. "40674" = Mammalia) finds every
  organism beneath it; "in" with several to broaden. For a known exact species,
  ncbi_scientific_name exact_match also works. Prefer higher pdb_entry_count.
- FALLBACK: if a rcsb_find_* resolver returns no usable match (count 0, or all results have
  pdb_entry_count 0), the concept isn't covered by that ontology — fall back to a keyword search
  (rcsb_search_fulltext, optionally with attribute filters) for it. The resolver's response
  carries a "note" saying so. Also use full text for concepts no ontology covers (tissues, broad
  phenotypes, free-text descriptors).

Return types and fetching details:
- Every search returns identifiers of ONE return_type. The six valid types — with an example
  id and the Data API tool that fetches their full details — are:
    entry              whole structure      "4HHB"     -> rcsb_get_entries
    polymer_entity     one molecule         "4HHB_1"   -> rcsb_get_polymer_entities
    non_polymer_entity ligand entity        "4HHB_3"   -> rcsb_get_nonpolymer_entities
    polymer_instance   one chain            "4HHB.A"   -> rcsb_get_polymer_entity_instances
    assembly           biological assembly  "4HHB-1"   -> rcsb_get_assemblies
    mol_definition     chemical component   "HEM"      -> rcsb_get_chem_comps
- The search tools' `enrich` flag auto-attaches entry metadata ONLY when return_type="entry".
  For any other return_type, take the returned ids and call the matching rcsb_get_* tool above
  (batch all ids into a single call) to get details — do not loop one id at a time.
- The rcsb_get_* and rcsb_seqcoord_* tools return a compact default field set. If you need a property
  they don't return, call rcsb_describe_data_object (Data API) or rcsb_describe_seqcoord_object
  (Sequence Coordinates) with [into=, query=] to find the exact field path, then pass it to
  the tool's `fields=` argument.
- Every search/Data/Sequence-Coordinates tool response includes a link to the interactive
  query editor for that exact request — `query_editor_url` (search) or `graphiql_url`
  (GraphQL). When you show your work, surface that link verbatim; never construct these
  URLs yourself."""
)


# --------------------------------------------------------------------------- #
# Server prompt — the runtime assistant persona + HTML-report output format.
# This is the client-agnostic counterpart to a pasted system prompt: any MCP
# client can list and invoke it (the MCP `prompts` capability). Kept OUT of the
# `instructions` above — those are always-on, tool-routing guidance for every
# client — because this is opt-in application/presentation policy. The text is
# package data (prompts/pdb_assistant.md), the single source of truth, so it
# ships with the wheel and stays editable without touching code.
# --------------------------------------------------------------------------- #
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


@mcp.prompt(
    name="pdb_assistant",
    title="PDB structure assistant",
    description="Persona and HTML-report output format for answering Protein Data "
    "Bank questions with the rcsb_* tools. Invoke to start a PDB analysis session.",
)
def pdb_assistant() -> str:
    """Structural-biology assistant instructions: persona + report output format."""
    return _load_prompt("pdb_assistant.md")


# --------------------------------------------------------------------------- #
# Low-level HTTP helpers
# --------------------------------------------------------------------------- #
def _check_response(resp: httpx.Response, service: str) -> None:
    """Raise a clear, actionable error for a non-2xx response.

    Replaces httpx's terse ``raise_for_status``: maps the status codes these
    public APIs actually return to messages that tell the agent what to do next
    (e.g. a 400 from a bad attribute path, a 429 rate limit). Returns silently
    for any 2xx (callers handle 204 before calling this).
    """
    if resp.is_success:
        return
    code = resp.status_code
    if code == 400:
        # The body usually explains the rejection (bad attribute, operator, or
        # value type); surface a trimmed copy plus how to fix a search query.
        detail = " ".join((resp.text or "").split())
        msg = f"{service} rejected the request (HTTP 400)."
        if detail:
            msg += f" Details: {detail[:300]}"
        if "search" in service.lower():
            msg += (" Verify the attribute path and operator with "
                    "rcsb_list_pdb_search_attributes and that the value type matches.")
        raise ValueError(msg)
    if code in (401, 403):
        raise RuntimeError(f"{service} denied the request (HTTP {code}).")
    if code == 404:
        raise RuntimeError(f"{service} resource not found (HTTP 404).")
    if code == 429:
        raise RuntimeError(
            f"{service} rate limit exceeded (HTTP 429). Wait a few seconds and retry."
        )
    if code >= 500:
        raise RuntimeError(f"{service} is unavailable (HTTP {code}); try again shortly.")
    raise RuntimeError(f"{service} request failed (HTTP {code}).")


async def _post_search(body: dict[str, Any]) -> dict[str, Any]:
    """POST a query to the Search API. Returns a normalized result dict."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.post(SEARCH_URL, json=body)
    except httpx.TimeoutException:
        raise RuntimeError("RCSB Search API timed out; try again or narrow the query.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"RCSB Search API connection error ({type(exc).__name__}).") from None
    # The API returns 204 No Content when nothing matches.
    if resp.status_code == 204:
        return {"total_count": 0, "result_set": []}
    _check_response(resp, "RCSB Search API")
    return resp.json()


async def _post_graphql(
    query: str, variables: dict[str, Any] | None = None, url: str = DATA_GRAPHQL_URL
) -> dict[str, Any]:
    """POST a GraphQL query to an RCSB GraphQL endpoint. Returns the raw {data, errors} payload.

    These endpoints reply 200 even for query/validation errors, surfacing them in
    an ``errors`` array, so callers must inspect that rather than HTTP status.
    """
    body = {"query": query, "variables": variables or {}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.post(url, json=body)
    except httpx.TimeoutException:
        raise RuntimeError("RCSB GraphQL API timed out; try again or simplify the query.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"RCSB GraphQL API connection error ({type(exc).__name__}).") from None
    _check_response(resp, "RCSB GraphQL API")
    return resp.json()


async def _get_json(url: str, params: dict[str, Any], service: str) -> dict[str, Any]:
    """GET a JSON resource (shared headers/timeout) with friendly errors.

    Used by the ontology resolvers (rcsb_find_* tools) that call EBI and UniProt web services.
    """
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        ) as client:
            resp = await client.get(url, params=params)
    except httpx.TimeoutException:
        raise RuntimeError(f"{service} timed out; try again shortly.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{service} connection error ({type(exc).__name__}).") from None
    _check_response(resp, service)
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
# GraphQL schema introspection (powers rcsb_describe_data_object / rcsb_describe_seqcoord_object)
# --------------------------------------------------------------------------- #
# Cached per endpoint so repeated rcsb_describe_* calls don't re-hit the service. Each
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

    Shared by rcsb_describe_data_object and rcsb_describe_seqcoord_object.
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
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        # Enrichment is best-effort: never fail the search because of it.
        return [{"id": pid, "error": str(exc)} for pid in entry_ids]


def _format(
    raw: dict[str, Any],
    enriched: list[dict[str, Any]] | None,
    body: dict[str, Any] | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    hits = [
        {"id": r["identifier"], "score": round(r.get("score", 0.0), 3)}
        for r in raw.get("result_set", [])
    ]
    total = raw.get("total_count", 0)
    result: dict[str, Any] = {"total_count": total, "returned": len(hits)}
    if offset is not None:
        # Paging metadata: a single typed-search page is capped at 100 hits, so
        # callers step `offset` forward by `next_offset` to fetch the next page.
        has_more = offset + len(hits) < total
        result["offset"] = offset
        result["has_more"] = has_more
        result["next_offset"] = offset + len(hits) if has_more else None
    result["hits"] = hits
    if enriched is not None:
        result["details"] = enriched
    if body is not None:
        result["query_editor_url"] = _search_editor_url(body)
    return result


async def _guard_all_hits(body: dict[str, Any], offset: int = 0) -> None:
    """Validate an all_hits search before issuing it.

    all_hits returns the COMPLETE set via return_all_hits, which the Search API
    forbids combining with pagination — so reject a non-zero offset up front. Then
    pre-count the query (cheap; return_counts only) so a broad keyword/attribute query
    can't return a massive id list that would swamp the agent's context. Raises
    ValueError with an actionable next step.
    """
    if offset:
        raise ValueError(
            "all_hits returns the complete result set and can't be combined with offset "
            "paging (the Search API rejects it). Drop offset, or page with all_hits=False."
        )
    count_body = {
        "query": body["query"],
        "return_type": body["return_type"],
        "request_options": {
            "return_counts": True,
            "results_content_type": body["request_options"].get(
                "results_content_type", ["experimental"]
            ),
        },
    }
    total = (await _post_search(count_body)).get("total_count", 0)
    if total > ALL_HITS_MAX:
        raise ValueError(
            f"all_hits would return {total} hits, above the {ALL_HITS_MAX} cap. "
            "Narrow the query (add filters), aggregate by passing `facets`, or "
            "page through results with limit + offset."
        )


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
    except (httpx.HTTPError, ValueError, RuntimeError):
        return None


def _resolver_fallback_note(items: list[dict[str, Any]], label: str) -> str | None:
    """Advise a keyword fallback when an ontology resolver finds nothing usable."""
    if not items:
        return (f"No {label} matched this concept. Fall back to a keyword search "
                "(rcsb_search_fulltext, optionally with attribute filters) for it.")
    if all("pdb_entry_count" in it for it in items) and not any(it["pdb_entry_count"] for it in items):
        return (f"Matched {label}(s) but none are annotated in the PDB (pdb_entry_count 0). "
                "A keyword search (rcsb_search_fulltext) may still surface relevant structures.")
    return None


# --------------------------------------------------------------------------- #
# Search API Tools
# --------------------------------------------------------------------------- #
@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_fulltext(
    query: str,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    return_type: ReturnType = "entry",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    include_computed_models: bool = False,
    enrich: bool = True,
    chemical: bool = False,
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Search the PDB by free-text keywords (e.g. "CRISPR Cas9", "hemoglobin"), optionally
    refined with structured attribute filters.

    Best for broad or exploratory keyword lookups. Pass `attributes` to AND/OR the keyword
    with structured conditions (organism, resolution, method, dates, ...) in one query. When
    a request has NO keyword (only attributes), use rcsb_search_by_attribute; when it resolves
    to a clear attribute and value, prefer structured search — call
    rcsb_list_pdb_search_attributes first to find the exact path and operators (more precise,
    avoids spurious keyword matches). For NESTED boolean logic or other services
    (sequence/structure/chemical/motif), use rcsb_search_advanced.

    BEFORE keyword-searching a biological CONCEPT, try to resolve it to an ontology id first
    and filter on the annotation (far more precise):
      - disease / condition (e.g. "diabetes", "cancer")   -> rcsb_find_disease_terms
      - molecular function / process / location            -> rcsb_find_go_terms
      - protein domain / family / fold                     -> rcsb_find_interpro_domains
      - enzyme / catalyzed reaction                        -> rcsb_find_enzyme_classes
      - organism common name / clade (e.g. "human", "mammals") -> rcsb_find_organisms
    Each returns ids to use as an `attributes` filter on the matching annotation attribute.
    If a resolver finds no usable match (count 0, or all pdb_entry_count 0), the concept isn't
    covered by that ontology — THEN fall back to a plain keyword search here for the concept.

    For search for an assembly / complex / multi-subunit machine / multimer (or any other term indicating a structure
    composed of multiple subunits / proteins) add rcsb_assembly_info.* to `attributes`:
    - rcsb_assembly_info.polymer_entity_instance_count_protein >= N (total protein chains),
    - rcsb_assembly_info.polymer_entity_count_protein >= M (distinct subunits),
    - rcsb_assembly_info.polymer_composition exact_match "heteromeric protein" | "homomeric protein"
    combine these as needed to search for multimeric structures.

    Matching spans ALL text annotations, so a hit may be a spurious keyword match rather than a
    real answer. After searching, JUDGE each hit's relevance yourself: read its title (in
    `details` when enrich=True) and, for borderline cases, fetch its PubMed abstract
    (rcsb_get_entries -> pubmed.rcsb_pubmed_abstract_text); decide whether that text actually
    supports the user's question, and treat a low `score` as only a weak hint.

    Args:
        query: Free-text terms matched (case-insensitively) against all text annotations.
            Quote a multi-word phrase to require the words adjacent/in order (e.g.
            '"DNA polymerase"'); separate words narrow the results (most must match).
            Trailing '*' is a prefix wildcard. AND/OR/NOT are NOT boolean operators here —
            for boolean logic across conditions use `attributes` (flat) or rcsb_search_advanced.
        attributes: Optional structured conditions combined with the keyword — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (see
            rcsb_search_by_attribute / rcsb_list_pdb_search_attributes for paths and operators).
        logical_operator: Combine the keyword and all attribute conditions with "and"
            (default) or "or".
        return_type: What to return (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition (see the
            "Return types and fetching details" note in the server instructions).
        limit: Max number of hits to return (1-100).
        offset: Number of hits to skip, for paging (default 0). The response's
            next_offset/has_more report whether more pages remain; pass next_offset
            back here with the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call, for an explicit "ALL ..."
            request. Ignores limit and omits the paging fields; can't be combined with
            offset (the Search API rejects pagination here). Refused above 10000 hits —
            narrow the query, aggregate by passing `facets`, or page instead. enrich
            still annotates only the first 25 hits.
        include_computed_models: Also search computed structure models (AlphaFold etc.).
        enrich: If true, attach title/method/resolution for each entry hit.
        chemical: Set True when `attributes` target chemical-component attributes (the
            text_chem service; usually pair with return_type="mol_definition").
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
        sort_by: Attribute path to sort by (e.g. "rcsb_entry_info.resolution_combined");
            omit to sort by relevance score.
        sort_direction: "asc" (default) or "desc" for sort_by.
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.
    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; "details" (per-entry title/method/resolution) is added when enrich.
        With all_hits, the offset/has_more/next_offset paging fields are omitted. With `facets`,
        instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_combined_query(
        full_text=query,
        filters=_filter_dicts(attributes),
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        include_computed=include_computed_models,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
        chemical=chemical,
        facets=facets,
    )
    if all_hits:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_list_pdb_search_attributes(
    query: str | None = None, schema: AttributeSchema = "structure"
) -> list[dict[str, Any]]:
    """Discover the RCSB PDB Search schema: attribute paths, value types, and operators.

    Call this FIRST whenever the request resolves to a clear attribute and value but
    you don't already know the exact attribute path. Pick the matching attribute here,
    then run `rcsb_search_by_attribute`
    (or any `rcsb_search_*` to add an attribute+value to `attributes`). Prefer this
    structured path over `rcsb_search_fulltext` whenever a specific attribute and value apply.

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
              for structure searches. Use with rcsb_search_by_attribute / rcsb_search_fulltext.
            - "chemical" (~57 attrs): chemical-component attributes (chem_comp.*,
              drugbank_info.*, rcsb_chem_comp_*). To search these, pass chemical=True to
              rcsb_search_by_attribute / rcsb_search_fulltext (usually return_type="mol_definition").

    Returns:
        A list of {attribute, type, operators, description} dicts — one per matching
        attribute (fields described above); all of them when query is omitted.
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_find_go_terms(
    query: str,
    namespace: str | None = None,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text molecular function, biological process, or cellular component /
    location (e.g. kinase activity, ATP binding, DNA repair, apoptosis, signal transduction,
    mitochondrial membrane, nucleus) to Gene Ontology (GO) terms, so you can run precise
    GO-based PDB searches instead of keyword guessing.

    Use this whenever a request involves what a protein DOES or where it acts — including
    "proteins that <do X> / are involved in / participate in / are responsible for ...",
    or "localized to / located in ...". Covers a molecular FUNCTION ("kinase activity",
    "ATP binding"), a biological PROCESS ("DNA repair", "apoptosis", "cell signaling"), or a
    cellular COMPONENT / location ("mitochondrial membrane", "nucleus"). Resolve the phrase to
    a GO id here, then search by it.

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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_find_interpro_domains(
    query: str,
    entry_type: str | None = None,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text protein domain, family, or fold (e.g. SH2 domain, immunoglobulin
    fold, zinc finger, beta-barrel, WD40 repeat, kinase domain) to InterPro entries, for
    precise InterPro-based PDB searches instead of keyword guessing.

    Use this when a request references a protein DOMAIN, FAMILY, or fold — including
    "structures containing / with a <domain>", "<domain>-containing proteins", or
    "members of the <family> family" (e.g. "SH2 domain", "immunoglobulin fold", "protein
    kinase domain", "Rossmann fold", "zinc finger"). Resolve the phrase to an InterPro
    accession (IPRxxxxxx) here, then search by it:
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_find_enzyme_classes(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text enzyme, enzyme class, or catalyzed reaction (e.g. alcohol
    dehydrogenase, protease, kinase, DNA polymerase, hydrolase, oxidoreductase) to Enzyme
    Commission (EC) numbers, for precise EC-based PDB searches instead of keyword guessing.

    Use this when a request references an enzyme, enzyme class, or reaction — including
    "enzymes that catalyze / break down / degrade / synthesize / hydrolyze / phosphorylate ..."
    (e.g. "alcohol dehydrogenase", "protein tyrosine kinase", "DNA polymerase", "serine
    protease", "EC 3.4.21"). Resolve the phrase to an EC number here, then
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_find_disease_terms(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text disease, disorder, syndrome, or condition (e.g. diabetes, cancer,
    Alzheimer disease, cystic fibrosis) to MONDO ontology ids, for precise disease-based PDB
    searches instead of keyword guessing.

    Use this for ANY request that mentions a disease/disorder/syndrome/condition — including
    "structures involved in / associated with / linked to <disease>", or "proteins implicated
    in <disease>". Examples: "diabetes", "type 2 diabetes", "cancer", "breast cancer",
    "Alzheimer disease", "Parkinson disease", "cystic fibrosis", "asthma". Resolve the phrase
    to a MONDO id here, then search by it:
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_find_organisms(
    query: str,
    limit: ResolverLimit = 10,
    with_pdb_counts: bool = True,
) -> dict[str, Any]:
    """Resolve a free-text organism, common name, or clade (e.g. human, mouse, baker's yeast,
    Escherichia coli, mammals, bacteria, primates) to NCBI Taxonomy ids, for precise
    taxonomy-based PDB searches instead of keyword guessing.

    Use this whenever a request restricts structures by SOURCE ORGANISM or any higher taxon —
    "structures from <organism>", "<clade> proteins", a common name you want as a canonical
    taxon ("human", "fruit fly"), or "members of the <family/order/class> ...". Resolve the
    phrase to an NCBI taxon id here, then search by it:
    `rcsb_entity_source_organism.taxonomy_lineage.id` exact_match "<taxId>" — each entity's
    taxonomy_lineage is its full NCBI ancestor chain, so this matches the taxon AND every
    organism beneath it (a species id like "9606" finds Homo sapiens; a clade id like "40674"
    finds all of Mammalia). Pass the id as a STRING: the attribute is string-typed, so
    value="9606" works while value=9606 is rejected. Use the `in` operator with several ids to
    broaden. (`rcsb_entity_source_organism.taxonomy_lineage.name` is the string-name equivalent;
    prefer the id.)

    For a known exact binomial (e.g. "Homo sapiens"), a direct
    `rcsb_entity_source_organism.ncbi_scientific_name` exact_match search also works — this tool
    is most valuable for common names and for CLADES, which a plain name search cannot expand.

    Args:
        query: Free-text organism / clade / common name, e.g. "human", "mammals", "E. coli".
        limit: Max taxa to return (1-25).
        with_pdb_counts: If true (default), annotate each taxon with pdb_entry_count (PDB
            entries from it or any organism beneath it, via taxonomy_lineage.id) so you can
            prefer well-represented taxa — this also disambiguates a species from its strains.

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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_by_attribute(
    attributes: list[AttributeFilter],
    logical_operator: LogicalOperator = "and",
    return_type: ReturnType = "entry",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    enrich: bool = True,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
    chemical: bool = False,
    facets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Search by one or more structured attribute conditions combined with a single AND/OR —
    preferred over rcsb_search_fulltext whenever the request resolves to clear attribute(s)
    and value(s). If you don't know a path or its operators, call rcsb_list_pdb_search_attributes
    first. For NESTED boolean logic use rcsb_search_advanced.

    For a biological concept, resolve it to an ontology id first:
        - disease -> rcsb_find_disease_terms;
        - function/process/location -> rcsb_find_go_terms;
        - domain/family/fold -> rcsb_find_interpro_domains;
        - enzyme/reaction -> rcsb_find_enzyme_classes;
        - organism common name/clade -> rcsb_find_organisms.
    and use it on the matching annotation attribute, see rcsb_list_pdb_search_attributes.
    If a resolver returns no usable id, or a concept/annotation filter yields no hits, fall
    back to rcsb_search_fulltext for the concept. (For ordinary constraints — resolution, organism,
    dates — an empty result is a valid answer: report it, don't keyword-search instead.)

    Example ("human X-ray structures better than 2 A"):
        attributes=[
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "exptl.method", "operator": "exact_match", "value": "X-RAY DIFFRACTION"},
            {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0},
        ]
    Single-condition examples: a released-after-date filter ->
    {"attribute": "rcsb_accession_info.initial_release_date", "operator": "greater",
    "value": "2024-01-01T00:00:00Z"}; has any ligand (no value) ->
    {"attribute": "rcsb_nonpolymer_entity.pdbx_description", "operator": "exists"}.

    Args:
        attributes: One or more AttributeFilter conditions, each {attribute, operator, value,
            negation?, case_sensitive?}. Operators are TYPE-SPECIFIC (strings use
            exact_match/in or contains_words/contains_phrase; numbers/dates use greater/
            greater_or_equal/less/less_or_equal/equals/range; any type supports exists). A
            numeric value may be a number or a numeric string; a range value is a
            {from, to, include_lower, include_upper} object (bounds EXCLUSIVE unless the
            include flags are true). See rcsb_list_pdb_search_attributes for paths/operators.
        logical_operator: Combine the conditions with "and" (default) or "or".
        return_type: What to return (default "entry"); one of entry, polymer_entity,
            non_polymer_entity, polymer_instance, assembly, mol_definition (see the
            server instructions). E.g. return_type="entry" with a ligand attribute
            finds the structures that contain it.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call, for an explicit "ALL ..."
            request. Ignores limit and omits the paging fields; can't be combined with
            offset (the Search API rejects pagination here). Refused above 10000 hits —
            narrow the query, aggregate by passing `facets`, or page instead. enrich
            still annotates only the first 25 hits.
        enrich: Attach entry metadata when return_type is "entry".
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.
        chemical: Set True for chemical-component attributes (paths from
            rcsb_list_pdb_search_attributes(schema="chemical"), e.g. "chem_comp.formula_weight").
            Switches to the text_chem service; usually pair with return_type="mol_definition".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; "details" (per-entry title/method/resolution) is added when enrich.
        With all_hits, the offset/has_more/next_offset paging fields are omitted. With `facets`,
        instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_combined_query(
        full_text=None,
        filters=_filter_dicts(attributes),
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
        chemical=chemical,
        facets=facets,
    )
    if all_hits:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    ids = [r["identifier"] for r in raw.get("result_set", [])]
    enriched = await _enrich(ids) if (enrich and return_type == "entry" and ids) else None
    return _format(raw, enriched, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_by_sequence(
    sequence: str,
    sequence_type: SequenceType = "protein",
    identity_cutoff: Annotated[float, Field(ge=0.0, le=1.0)] = 0.3,
    evalue_cutoff: Annotated[float, Field(ge=0.0)] = 1.0,
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find PDB polymer entities similar to a given sequence (MMseqs2, BLAST-like).

    Args:
        sequence: The query sequence in one-letter code.
        sequence_type: "protein", "dna", or "rna".
        identity_cutoff: Minimum sequence identity as a fraction 0-1 (e.g. 0.3 = 30%).
        evalue_cutoff: Maximum E-value to report.
        limit: Max hits (1-100). Returns polymer_entity IDs like "4HHB_1" — fetch their
            details with rcsb_get_polymer_entities.
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.

        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; with `facets`, instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_sequence_query(
        sequence,
        sequence_type=sequence_type,
        identity_cutoff=identity_cutoff,
        evalue_cutoff=evalue_cutoff,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, None, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_by_chemical(
    value: str,
    query_type: ChemQueryType = "descriptor",
    descriptor_type: DescriptorType = "SMILES",
    match_type: ChemMatchType = "graph-relaxed",
    match_subset: bool = False,
    return_type: ReturnType = "mol_definition",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
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
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.

        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; with `facets`, instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_chemical_query(
        value,
        query_type=query_type,
        descriptor_type=descriptor_type,
        match_type=match_type,
        match_subset=match_subset,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, None, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_by_structure(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
    return_type: ReturnType | None = None,
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
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
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.

        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
         group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; with `facets`, instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_structure_query(
        entry_id,
        assembly_id=assembly_id,
        asym_id=asym_id,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, None, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_by_seqmotif(
    pattern: str,
    pattern_type: SeqmotifPatternType = "prosite",
    sequence_type: SequenceType = "protein",
    return_type: ReturnType = "polymer_entity",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find polymers containing a short sequence motif (PROSITE / regex / simple).

    Args:
        pattern: The motif, e.g. "C-x(2,4)-C-x(3)-[LIVMFYWC]-x(8)-H-x(3,5)-H"
            (prosite), "C..H[LIVF]" (regex), or "NXS" (simple wildcards).
        pattern_type: "prosite" (default), "regex", or "simple".
        sequence_type: "protein" (default), "dna", or "rna".
        return_type: What to return (default "polymer_entity"); one of the six types
            (see server instructions). Default hits feed rcsb_get_polymer_entities.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.

        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; with `facets`, instead returns {total_count, facets, query_editor_url}.
    """
    body = queries.build_seqmotif_query(
        pattern,
        pattern_type=pattern_type,
        sequence_type=sequence_type,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, None, body, None if all_hits else offset)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_advanced(query_body: dict[str, Any]) -> dict[str, Any]:
    """Run a raw RCSB Search API query body (escape hatch).

    Endpoint: https://search.rcsb.org/rcsbsearch/v2/query . The typed rcsb_search_* tools cover
    the common cases (each carries total_count and takes `attributes` + `facets`); use this for
    anything they don't — return_all_hits, group_by "groups", arbitrarily NESTED and/or
    boolean groups, and queries that COMBINE several non-text services (sequence, structure,
    chemical, seqmotif, strucmotif) under one group (e.g. a sequence-similarity match AND a
    chemical-descriptor match — a single non-text service can already be refined with
    `attributes` on its rcsb_search_by_* tool). Build the query from "group"
    nodes (logical_operator + nodes) and "terminal" nodes (service + parameters); full query
    language: https://search.rcsb.org/ . The body is {"query", "return_type",
    "request_options"} and returns the normalized {total_count, returned, hits} result.

    Example — "(Homo sapiens OR Mus musculus) AND released after 2019-08-20":
        query_body={"query": {"type": "group", "logical_operator": "and", "nodes": [
          {"type": "group", "logical_operator": "or", "nodes": [
            {"type": "terminal", "service": "text", "parameters": {
              "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
              "operator": "exact_match", "value": "Homo sapiens"}},
            {"type": "terminal", "service": "text", "parameters": {
              "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
              "operator": "exact_match", "value": "Mus musculus"}}]},
          {"type": "terminal", "service": "text", "parameters": {
            "attribute": "rcsb_accession_info.initial_release_date",
            "operator": "greater", "value": "2019-08-20"}}]},
          "return_type": "polymer_entity"}
    """
    raw = await _post_search(query_body)
    return _format(raw, None, query_body)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_search_strucmotif(
    entry_id: str,
    residue_ids: list[dict[str, Any]],
    backbone_distance_tolerance: Tolerance = 1,
    side_chain_distance_tolerance: Tolerance = 1,
    angle_tolerance: Tolerance = 1,
    rmsd_cutoff: Annotated[float, Field(ge=0.0)] = 2.0,
    atom_pairing_scheme: AtomPairingScheme = "SIDE_CHAIN",
    motif_pruning_strategy: MotifPruningStrategy = "KRUSKAL",
    return_type: ReturnType = "polymer_entity",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find structures containing a 3D STRUCTURAL MOTIF — a geometric arrangement of
    specific residues — like the one in a reference structure.

    This is geometry-based and DIFFERENT from rcsb_search_by_structure (whole-shape similarity)
    and from rcsb_search_by_seqmotif (sequence pattern). Use it for catalytic triads, binding
    sites, metal-coordination geometries, etc.

    Args:
        entry_id: Reference PDB entry defining the motif, e.g. "2MNR".
        residue_ids: 2-10 residues defining the motif, each a dict
            {"label_asym_id": <chain>, "label_seq_id": <int>, "struct_oper_id"?: <str>}.
            IMPORTANT: these are the mmCIF *label* identifiers (the internal numbering),
            which often DIFFER from the author residue numbers seen in papers/the PDB
            site. If you only have author numbering, resolve the label_asym_id/label_seq_id
            first (e.g. via rcsb_get_polymer_entity_instances) — author numbers give wrong/no hits.
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
        offset: Number of hits to skip, for paging (default 0); pass the response's
            next_offset back with the same query to fetch the next page.

        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution of the matches instead of
            hits (see the faceting note in the server instructions for the spec).
        group_by: Collapse redundant polymer_entity hits into clusters, returning one
            representative each — "seqid_30"/"seqid_50"/"seqid_70"/"seqid_90"/"seqid_95"
            (cluster by that sequence-identity %) or "uniprot" (one per UniProt accession).
            Only available with return_type="polymer_entity".
        group_by_ranking: Which member to keep as each cluster's representative (each ranking
            has a fixed direction): "resolution" (best resolution structure), "released_date" (most recent),
            "entity_residue_count" (longest), "score" (best ElasticSearch score), or "coverage" (most
            relevant biological sequence — requires group_by="uniprot", and recommended
            there). Omit for RCSB's default.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        query_editor_url}; with `facets`, instead returns {total_count, facets, query_editor_url}.
    """
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
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, None, body, None if all_hits else offset)


# --------------------------------------------------------------------------- #
# Data API tools — one per GraphQL root field (singular forms are covered by
# their batch tool, called with a single-element list). Each returns the raw
# selected GraphQL node(s); pass `fields` to override the curated default
# selection with your own GraphQL sub-selection (omit the surrounding braces).
# --------------------------------------------------------------------------- #
@mcp.tool(annotations=READ_ONLY)
async def rcsb_describe_data_object(
    object_key: str, into: str | None = None, query: str | None = None
) -> dict[str, Any]:
    """Discover the fields available on a Data API object, from the live GraphQL schema.

    Use this to find exactly what to request in a rcsb_get_* tool's `fields=` argument (or
    in rcsb_data_graphql). The rcsb_get_* default selections are compact summaries, but the
    underlying GraphQL types have far more (e.g. CoreEntry has ~100 fields). This tool
    walks the schema so you can build a precise selection instead of guessing.

    Workflow: rcsb_describe_data_object("entries") -> spot a nested object field such as
    "rcsb_entry_info" -> rcsb_describe_data_object("entries", into="rcsb_entry_info") to list
    its leaves -> call rcsb_get_entries(ids, fields="rcsb_entry_info{ ... }").

    Each returned field has:
    - name: the GraphQL field name
    - kind: "scalar" (a leaf you can select directly) or "object" (drill in with `into`)
    - type: the field's GraphQL type name
    - list: whether the field returns a list
    - description: schema description, when present

    Args:
        object_key: Which object to describe — a key matching the rcsb_get_* tools, e.g.
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_entries(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch metadata for one or more PDB entries (title, method, resolution, size,
    dates, primary citation, and publication abstract).

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]. Unknown IDs are
    listed under "not_found". For a single entry pass a one-element list.

    The response also lists the entry's component ids under
    rcsb_entry_container_identifiers — use these to drill into the structure. They are
    bare numbers; compose them with the entry id to call the matching rcsb_get_* tool:
    polymer_entity_ids/non_polymer_entity_ids "N" -> "<ENTRY>_N" (rcsb_get_polymer_entities /
    rcsb_get_nonpolymer_entities); assembly_ids "N" -> "<ENTRY>-N" (rcsb_get_assemblies).

    For fields beyond this summary, use rcsb_describe_data_object("entries") to find the
    path and pass it via `fields`.
    """
    return await _query_batch("entries", entry_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_entry_annotations(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological and functional annotations for one or more PDB entries —
    Gene Ontology terms (molecular function, biological process, cellular component),
    protein-domain classifications, disease associations, antibody and gene-product
    annotations, and more.

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]; for a single entry pass a
    one-element list. Unknown IDs are returned under "not_found"; pass `fields` to
    request other properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("entry_annotations", entry_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_entry_exp_info(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch detailed experimental conditions and structure-determination metadata for
    one or more PDB entries — sample temperature, pH, pressure, experimental method,
    diffraction data, and other reported parameters.

    IDs are 4-character entry codes, e.g. ["4HHB", "1MBN"]; for a single entry pass a
    one-element list. Unknown IDs are returned under "not_found"; pass `fields` to
    request other properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("entry_exp_info", entry_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_polymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entities (protein/nucleic-acid molecules).

    IDs combine entry + entity number, e.g. ["4HHB_1"] — exactly what
    rcsb_search_by_sequence returns. Default fields: description, sequence, length,
    weight, and source organism. Unknown IDs are returned under "not_found"; pass
    `fields` to request other properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("polymer_entities", entity_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_nonpolymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer (ligand/cofactor) entities, e.g. ["4HHB_3"].

    Default fields: description, weight, copy count, and the bound chemical
    component ID. Use rcsb_get_chem_comps for the chemistry of that component.
    Unknown IDs are returned under "not_found"; pass `fields` to request other
    properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("nonpolymer_entities", entity_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_branched_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched (carbohydrate / oligosaccharide) entities, e.g. ["5FMB_2"].

    Default fields: description, weight, copy count, branch type, and component count.
    Unknown IDs are returned under "not_found"; pass `fields` to request other
    properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("branched_entities", entity_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_polymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity instances (individual chains), e.g. ["4HHB.A"] (entry.asym_id).

    Default fields: the entry/entity/chain identifiers and modeled-residue count.
    Unknown IDs are returned under "not_found"; pass `fields` to request other
    properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("polymer_entity_instances", instance_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_nonpolymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity instances (individual bound ligands), e.g. ["4HHB.E"].

    Default fields: the entry/entity/chain identifiers, bound component id, and author
    seq id. Unknown IDs are returned under "not_found"; pass `fields` to request other
    properties (paths via rcsb_describe_data_object).
    """
    return await _query_batch("nonpolymer_entity_instances", instance_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_branched_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched entity instances (individual glycan chains), e.g. ["5FMB.C"].

    Default fields: the entry/entity/chain identifiers. Unknown IDs are returned under
    "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("branched_entity_instances", instance_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_assemblies(assembly_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological assemblies, e.g. ["4HHB-1"] (entry-assembly).

    Default fields: composition counts and oligomeric state. Unknown IDs are returned
    under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("assemblies", assembly_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_interfaces(interface_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch assembly interfaces, e.g. ["1BMV-1.1"] (entry-assembly.interface).

    Default fields: buried area, character, composition, residue count. Unknown IDs are
    returned under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("interfaces", interface_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_chem_comps(comp_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch chemical components / ligands by their short codes, e.g. ["HEM", "ATP"].

    Default fields: name, formula, weight, type, SMILES, InChIKey. Unknown IDs are
    returned under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("chem_comps", comp_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_entry_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch entry groups (clusters of related entries) by group ID.

    Default fields: group name, description, member count, and member ids. Unknown IDs
    are returned under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("entry_groups", group_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_polymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity groups (e.g. sequence clusters), e.g. ["85_70"].

    Default fields: group name, description, member count, and member ids. Unknown IDs
    are returned under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("polymer_entity_groups", group_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_nonpolymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity groups (clusters of related ligands) by group ID.

    Default fields: group name, description, member count, and member ids. Unknown IDs
    are returned under "not_found"; pass `fields` to request other properties (paths via
    rcsb_describe_data_object).
    """
    return await _query_batch("nonpolymer_entity_groups", group_ids, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_uniprot(uniprot_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch the UniProt record RCSB maps to an accession, e.g. "P69905".

    Default fields give a functional snapshot: accession(s), entry name, protein and gene
    names, EC number, the UniProt function comment, source organism, and keywords (which
    often summarize biology directly, e.g. "ATP-binding", "Viral attachment to host entry
    receptor").

    RCSB's UniProt integration is rich — `fields` can also pull the heavier annotation sets
    (kept out of the default because they can run to hundreds of entries):
    `rcsb_uniprot_annotation` (GO terms, InterPro, disease associations),
    `rcsb_uniprot_feature` (domains, sites, binding sites, sequence variants), and
    `rcsb_uniprot_external_reference`. Discover exact paths with rcsb_describe_data_object.
    """
    return await _query_single("uniprot", uniprot_id, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_pubmed(pubmed_id: int, fields: str | None = None) -> dict[str, Any]:
    """Fetch the PubMed record for a citation by its integer ID, e.g. 6726807.

    Default fields: PubMed Central ID, DOI, abstract text. Pass `fields` to request
    other properties (paths via rcsb_describe_data_object).
    """
    return await _query_single("pubmed", pubmed_id, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_get_group_provenance(group_provenance_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch provenance/method metadata for a grouping, e.g. "provenance_sequence_identity".

    Default fields: the aggregation method/type and provenance id. Pass `fields` to
    request other properties (paths via rcsb_describe_data_object).
    """
    return await _query_single("group_provenance", group_provenance_id, fields)


@mcp.tool(annotations=READ_ONLY)
async def rcsb_data_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an arbitrary GraphQL query against the RCSB Data API (escape hatch).

    Endpoint: https://data.rcsb.org/graphql . The rcsb_get_* tools cover every root
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
# rcsb_describe_seqcoord_object to discover what to request).
# --------------------------------------------------------------------------- #
# The five Sequence Coordinates root fields, for rcsb_describe_seqcoord_object.
SEQCOORD_OBJECTS = {
    "alignments", "annotations",
    "group_alignments", "group_annotations", "group_annotations_summary",
}


@mcp.tool(annotations=READ_ONLY)
async def rcsb_describe_seqcoord_object(
    object_key: str, into: str | None = None, query: str | None = None
) -> dict[str, Any]:
    """Discover the fields available on a Sequence Coordinates object, from the live schema.

    The Sequence Coordinates analogue of rcsb_describe_data_object. The rcsb_seqcoord_* tools
    return a compact default selection; use this to find what else you can request via
    their `fields=` argument (or via rcsb_seqcoord_graphql).

    Workflow: rcsb_describe_seqcoord_object("alignments") -> spot a nested object such as
    "target_alignments" -> rcsb_describe_seqcoord_object("alignments", into="target_alignments")
    to list its leaves -> call rcsb_seqcoord_alignments(..., fields="target_alignments{ ... }").

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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_seqcoord_alignments(
    query_id: str,
    from_ref: SequenceRef,
    to_ref: SequenceRef,
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_seqcoord_annotations(
    query_id: str,
    reference: SequenceRef,
    sources: list[AnnotationRef],
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_seqcoord_group_alignments(
    group: GroupRef,
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_seqcoord_group_annotations(
    group: GroupRef,
    group_id: str,
    sources: list[AnnotationRef],
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
        filters: Optional filter dicts (see rcsb_seqcoord_annotations).
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


@mcp.tool(annotations=READ_ONLY)
async def rcsb_seqcoord_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an arbitrary GraphQL query against the RCSB Sequence Coordinates API.

    Endpoint: https://sequence-coordinates.rcsb.org/graphql . Escape hatch for
    fields/arguments the typed rcsb_seqcoord_* tools don't expose. Root fields:
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
