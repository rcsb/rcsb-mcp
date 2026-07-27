"""An MCP server for interrogating Protein Data Bank structures.

Spans three RCSB APIs so an LLM can take a question from discovery through detail:
- DISCOVER: search the Protein Data Bank (https://search.rcsb.org) by keyword,
  structural attribute, sequence, chemistry, 3D shape, or motif.
- INSPECT: fetch entry / entity / assembly / ligand metadata and annotations from
  the Data API (https://data.rcsb.org/graphql).
- RELATE: map alignments and positional annotations between sequence reference
  systems (UniProt, NCBI, PDB entity/instance) via the Sequence Coordinates API
  (https://sequence-coordinates.rcsb.org/graphql).

The Search API returns only identifiers, so a search is the first step: batch the
returned ids into the matching Data API tool for metadata, and an entry's component
ids let the agent drill top-down into its entities, assemblies, and ligands.

Run locally (stdio, for Claude Desktop / MCP Inspector):
    python -m rcsb_mcp.server
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

# GraphQL execution lives in rcsb_mcp.graphql (the shared layer above client, which imports
# nothing back from here); _fetch_report_rows below resolves _graphql_field by bare name.
from rcsb_mcp.graphql import _graphql_field  # noqa: E402


# --------------------------------------------------------------------------- #
# HTTP transport security (DNS-rebinding Host/Origin validation)
# --------------------------------------------------------------------------- #
def _transport_security() -> TransportSecuritySettings:
    """Host/Origin validation policy for the streamable-HTTP deployment.

    FastMCP auto-enables DNS-rebinding protection when `host` is a loopback address
    (its default) and no explicit policy is given, allow-listing only
    127.0.0.1/localhost. Behind an ingress that forwards the real Host header
    (e.g. rcsb-mcp.k8s.rcsb.org), that host then fails validation and every
    POST /mcp is rejected with 421 "Invalid Host header" — so no client can connect.

    This server is a public, TLS-terminated, read-only proxy meant to be added to
    arbitrary MCP clients (including browser-hosted agents whose Origin can't be
    enumerated), so validation is DISABLED by default. Set RCSB_MCP_ALLOWED_HOSTS
    (comma-separated) to lock it down to known hosts instead — note that enabling it
    also turns on Origin validation, which rejects browser clients unless their
    origins are listed in RCSB_MCP_ALLOWED_ORIGINS.
    """
    hosts = [h.strip() for h in os.getenv("RCSB_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    origins = [o.strip() for o in os.getenv("RCSB_MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


mcp = FastMCP(
    name="rcsb_mcp",
    instructions="""You are an assistant for interrogating Protein Data Bank structures via the
RCSB Search, Data, and Sequence Coordinates APIs. You can:
- DISCOVER structures — find identifiers with the rcsb_search_* tools (keyword, attribute,
  sequence, chemical, 3D shape, structural/sequence motif). Every search response carries
  total_count (the full match count); pass `facets` to any rcsb_search_* tool to get a
  breakdown into buckets instead of hits.
- INSPECT structures — fetch detailed properties, experimental info, and annotations with
  the rcsb_get_* tools; discover further fields to request with rcsb_describe_data_object
  (browse a level, or search the object's schema by keyword with query= and max_depth=).
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
  STRUCTURED search: NEVER invent, guess, or infer attribute paths, if you don't already know the exact attribute path, 
  call rcsb_list_pdb_search_attributes to find it, then use rcsb_search_by_attribute (it takes one
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
  "uniprot" (one per UniProt accession). Choose the representative with group_by_ranking:
    - resolution: ranks each group member by experimental resolution, best first.
    - released_date: ranks each group member by initial release date, most recent first.
    - entity_residue_count: ranks each group member by the length of the reported (sample)
      sequence, longest first — this is the deposited construct, so expression tags and
      fusion partners count toward it.
    - score: ranks each group member by ElasticSearch score, highest first. This score does not 
      measure biological relevance or quility of the structure.
    - coverage: ranks each group member by sequence coverage of the UniProt protein, largest first.
  When group_by="uniprot", PREFER group_by_ranking="coverage" — it keeps the most relevant biological sequence
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
  all its descendants); for ONLY that exact term (no descendants) use
  rcsb_polymer_entity_annotation.annotation_id exact_match "GO:..." instead (add .type="GO" to be
  explicit). This is far more precise than keyword search. Prefer terms with a higher
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
- Search responses carry identifiers + scores ONLY — no titles, organisms, or other metadata.
  To present or reason about hits, take the returned ids and call the matching rcsb_get_* tool
  above (batch ALL ids into a single call) to get details — do not loop one id at a time.
- The rcsb_get_* and rcsb_seqcoord_* tools return a compact default field set. Field paths
  shown in these tools' own descriptions/examples are already verified — use them directly. But
  NEVER invent, guess, or infer any OTHER field name for `fields=` (or for rcsb_data_graphql /
  rcsb_seqcoord_graphql) from memory, naming convention, or another API — an unverified path
  fails GraphQL schema validation and wastes the call. If you need a property that is neither in
  the defaults nor documented in the tool's description, FIRST confirm the exact field path
  against the live schema, THEN pass it to the tool's `fields=` argument:
    - Data API: rcsb_describe_data_object(object_key, ...) — the fastest way is
      query="<keyword>" with max_depth=3, a flat keyword search over the object's schema (incl.
      nested and cross-object fields) returning verified dotted paths with descriptions. Omit
      max_depth to list one level at a time, and use into= to drill into (or scope the search
      to) a specific nested object.
    - Sequence Coordinates: rcsb_describe_seqcoord_object(into=, query=).
  `fields=` accepts EITHER dotted attribute paths
  (e.g. "rcsb_polymer_entity.pdbx_description") OR GraphQL nested-brace syntax
  (e.g. "rcsb_polymer_entity { pdbx_description }"), the two may be mixed, and multiple
  paths are separated by spaces or commas.
- Every search/Data/Sequence-Coordinates tool response includes an `editor` object — an
  un-encoded {url, params} descriptor of the interactive query editor for that exact
  request. When you show your work, pass that `editor` object to rcsb_render_report
  verbatim; never construct or percent-encode these URLs yourself.""",
    # HTTP deployment runs 2-6 load-balanced replicas with no session affinity, so
    # run stateless (any pod can serve any request — no per-session state to lose)
    # and answer with plain JSON instead of long-lived SSE streams. Both flags are
    # ignored by the stdio transport (local/console use).
    stateless_http=True,
    json_response=True,
    # Accept the real Host header seen behind the ingress (see _transport_security).
    transport_security=_transport_security(),
)

from rcsb_mcp.data import register_data_tools
from rcsb_mcp.report.routes import register_report_routes
from rcsb_mcp.report.tools import register_report_tools
from rcsb_mcp.resolvers import register_resolver_tools
from rcsb_mcp.search import register_search_tools
from rcsb_mcp.seqcoord import register_seqcoord_tools


async def _fetch_report_rows(query: str, root_field: str, ids: list[str]) -> list[dict[str, Any]]:
    """Fetch a report table spec's derivable cells for `ids` in one round trip.

    Generic over the spec (report/tables.py supplies the query and root field), so
    adding a result type needs no change here. Injected into the report tool (via
    register_report_tools) so the report package stays HTTP-free — the concrete
    GraphQL-backed fetcher lives here at the composition root, using `_graphql_field`
    imported from rcsb_mcp.graphql (the shared layer, which imports nothing back).
    """
    nodes = await _graphql_field({"query": query, "variables": {"ids": ids}}, root_field)
    if nodes is None:
        # A 200 whose JSON carries neither `data.entries` nor `errors` (a WAF/CDN block
        # page, a maintenance body, a field rename) must NOT look like "resolved, no such
        # entries" — that would blank every cell in the table. Raise so the caller treats
        # it as a failed chunk and keeps what the agent supplied.
        raise RuntimeError(f"Data API returned no `{root_field}` field")
    return nodes


register_report_tools(mcp, entry_fetcher=_fetch_report_rows)
register_report_routes(mcp)
register_resolver_tools(mcp)
register_search_tools(mcp)
register_seqcoord_tools(mcp)
register_data_tools(mcp)


# --------------------------------------------------------------------------- #
# Server prompt — the runtime assistant persona + HTML-report output format.
# This is the client-agnostic counterpart to a pasted system prompt: any MCP
# client can list and invoke it (the MCP `prompts` capability). Kept OUT of the
# `instructions` above — those are always-on, tool-routing guidance for every
# client — because this is opt-in application/presentation policy. The text is
# package data (prompts/rcsb_search_assistant.md), the single source of truth, so it
# ships with the wheel and stays editable without touching code.
# --------------------------------------------------------------------------- #
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


@mcp.prompt(
    name="rcsb_search_assistant",
    title="RCSB PDB search assistant",
    description="Persona and report output format for answering Protein Data "
    "Bank search questions with the rcsb_* tools. Invoke to start a PDB search session.",
)
def rcsb_search_assistant() -> str:
    """Structural-biology assistant instructions: persona + report output format."""
    return _load_prompt("rcsb_search_assistant.md")


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
    app = mcp.streamable_http_app()
    # Browser-based ("web") agents call POST /mcp with fetch(), which triggers a CORS
    # preflight and requires CORS response headers; FastMCP's app adds none for /mcp,
    # so without this a browser blocks the request before it is ever sent. This is a
    # public, unauthenticated, read-only server, so any origin is allowed. Expose
    # Mcp-Session-Id so a browser client can read the session header when present.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
        max_age=86400,
    )
    return app


def main() -> None:
    mcp.run()  # stdio transport by default (local clients / console script)


if __name__ == "__main__":
    main()
