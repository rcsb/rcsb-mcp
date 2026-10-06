<!-- mcp-name: io.github.rcsb/rcsb-mcp -->

# rcsb-mcp

An [MCP](https://modelcontextprotocol.io) server for **interrogating Protein Data
Bank structures** — discover, inspect, and cross-reference — from LLM clients
(Claude Desktop, MCP Inspector, Cursor, etc.). It spans three RCSB APIs:

- **Discover** — find structures with the [Search API](https://search.rcsb.org)
  (keyword, attribute, sequence, chemistry, 3D shape, motif).
- **Inspect** — fetch entry / entity / assembly / ligand details and annotations
  from the [Data API](https://data.rcsb.org/graphql).
- **Relate** — map sequences and positional features across PDB, UniProt, and NCBI
  with the [Sequence Coordinates API](https://sequence-coordinates.rcsb.org/graphql).

## Tools

### Search (search.rcsb.org)

Searching is **two steps**: build a query with an `rcsb_query_*` tool, then execute it with
`rcsb_search_request`. The builders are pure — they return a query document (readable JSON
plus a digest) and touch no network, so **nothing is searched until you call
`rcsb_search_request`**. `rcsb_query_composer` joins two or more documents with AND/OR,
which is also how a single search mixes services (e.g. sequence similarity AND an organism
filter).

**Build**

| Tool | What it does |
|------|--------------|
| `rcsb_query_fulltext` | Free-text keyword query (e.g. `"CRISPR Cas9"`). |
| `rcsb_query_attribute` | Structured query on one or more indexed attributes (resolution, organism, release date, ...) joined by a single `logical_operator`. Each condition supports `exists`, `negation`, `case_sensitive`; `chemical_attributes=True` selects the chemical-component catalog. |
| `rcsb_query_sequence` | MMseqs2 sequence-similarity query (BLAST-like), with identity / e-value cutoffs. |
| `rcsb_query_chemical` | Chemical query by SMILES/InChI descriptor (whole-molecule or substructure) or molecular formula. |
| `rcsb_query_structure` | 3D shape-similarity query against a reference PDB assembly or chain. |
| `rcsb_query_seqmotif` | Short **sequence**-motif query (PROSITE pattern, regex, or simple wildcards). |
| `rcsb_query_strucmotif` | 3D **structural**-motif query: a geometric arrangement of specific residues (e.g. a catalytic triad). |
| `rcsb_query_composer` | Join 2+ query documents with AND/OR — nested boolean logic, and the only way to combine different services in one search. |

**Run**

| Tool | What it does |
|------|--------------|
| `rcsb_search_request` | Execute a query document and return matching **identifiers only**. Carries every output option: `return_type`, `limit`/`offset`, `all_hits`, `facets`, `sort_by`/`sort_direction`, `group_by`/`group_by_ranking`, `include_computed_models`. |

**Discover**

| Tool | What it does |
|------|--------------|
| `rcsb_list_pdb_search_attributes` | Discover searchable attribute paths, types, and operators. `schema="structure"` (default, ~683) or `schema="chemical"` (~61: `chem_comp.*`, `drugbank_info.*`, ...). Records also carry `enum` (closed value sets) and `nested_group` (attributes stored in nested objects — see below). |
| `rcsb_find_go_terms` | Resolve a free-text molecular function / biological process / cellular component to Gene Ontology ids (via EBI QuickGO), annotated with PDB entry counts — then search by `rcsb_polymer_entity_annotation.annotation_lineage.id`. |
| `rcsb_find_interpro_domains` | Resolve a free-text protein domain / family / fold to InterPro and Pfam ids (via EBI Search), annotated with PDB entry counts — then search by `rcsb_polymer_entity_annotation.annotation_id`. |
| `rcsb_find_enzyme_classes` | Resolve a free-text enzyme / reaction to Enzyme Commission (EC) numbers (via EBI Search/IntEnz), annotated with PDB entry counts — then search by `rcsb_polymer_entity.rcsb_ec_lineage.id` (hierarchical). |
| `rcsb_find_disease_terms` | Resolve a free-text disease / condition to MONDO ids (via EBI OLS), annotated with PDB entry counts — then search by `rcsb_uniprot_annotation.annotation_lineage.id` (hierarchical, UniProt-based). |
| `rcsb_find_organisms` | Resolve a free-text organism / common name / clade to NCBI Taxonomy ids (via UniProt taxonomy), annotated with PDB entry counts — then search by `rcsb_entity_source_organism.taxonomy_lineage.id` (hierarchical: a clade id matches every organism beneath it). |

Both attribute catalogs are generated from the live metadata schemas by
[`scripts/generate_search_attributes.py`](scripts/generate_search_attributes.py). To search
chemical-component attributes, find the path with
`rcsb_list_pdb_search_attributes(schema="chemical")`, pass `chemical_attributes=True` to
`rcsb_query_attribute`, and usually set `return_type="mol_definition"`.

**Nested attributes.** An object can hold many annotations, many binding affinities, many
citations. For attributes carrying a `nested_group`, the query shape selects the semantics:
conditions built in **one** `rcsb_query_attribute` call, with nothing else in it, must hold on
the **same** record; conditions in separate calls are matched independently against any
record. Both are valid and mean different things — `type=Kd` with `value<1` describes one
measurement, while an InterPro id and a GO type are necessarily two different annotations.

**Counting and faceting** are output options on `rcsb_search_request`, not separate tools:
every response includes `total_count` (the full match count — for "how many ..." run the
search with `limit=1` and read it), and passing `facets` returns a breakdown
(terms/histogram/date_histogram/range/cardinality) instead of hits. A terms facet also tells
you what your hits **share**, which is how a handful of results becomes a re-searchable value.

**Grouping.** `group_by` returns one representative per cluster — `seqid_30` … `seqid_95`
for sequence-identity clusters, or `uniprot` to collapse by accession — with
`group_by_ranking` choosing the representative. Requires `return_type="polymer_entity"`;
the response reports `group_count` alongside `total_count`.

**Sorting.** `sort_by` (an attribute path) + `sort_direction` (`asc`/`desc`) replaces the
default score ordering (for similarity searches this overrides the similarity-ranked order).
Only attributes indexed for sorting work — those exposing `exact_match` (strings) or `equals`
(numbers/dates) in `rcsb_list_pdb_search_attributes`; sorting is not available for
`return_type="mol_definition"`.

**Paging.** `rcsb_search_request` accepts `limit` (1–100, default 10) and `offset`
(default 0), and each response reports `total_count`, `has_more`, and `next_offset` — call
again with the same query document and `offset=next_offset`. For an explicit "ALL ..."
request, `all_hits=True` returns the complete set in one call (refused above 10,000 hits,
and it cannot be combined with `offset`).

### Data (data.rcsb.org/graphql)

There is one tool per Data API GraphQL root field. Each takes a **list of IDs**
(singular lookups = a one-element list) plus an optional `fields` argument to
override the curated default selection with your own GraphQL sub-selection.
Unknown IDs are reported under `not_found`. Discover the paths to put in `fields`
with `rcsb_describe_data_object` — browse a level, drill into a nested object with
`into=`, or search the schema by keyword with `query=` + `max_depth=`. Every path it
returns is verified against the live schema, so don't guess field names.

| Tool | Object | Example ID                       |
|------|--------|----------------------------------|
| `rcsb_get_entries` | PDB entries | `"4HHB"`                         |
| `rcsb_get_polymer_entities` | Polymer entities (protein/NA) | `"4HHB_1"`                       |
| `rcsb_get_nonpolymer_entities` | Ligand/cofactor entities | `"4HHB_3"`                       |
| `rcsb_get_branched_entities` | Carbohydrate entities | `"5FMB_2"`                       |
| `rcsb_get_polymer_entity_instances` | Polymer chains | `"4HHB.A"`                       |
| `rcsb_get_nonpolymer_entity_instances` | Bound-ligand instances | `"4HHB.E"`                       |
| `rcsb_get_branched_entity_instances` | Glycan chains | `"5FMB.C"`                       |
| `rcsb_get_assemblies` | Biological assemblies | `"4HHB-1"`                       |
| `rcsb_get_interfaces` | Assembly interfaces | `"1BMV-1.1"`                     |
| `rcsb_get_chem_comps` | Chemical components / ligands | `"HEM"`, `"ATP"`                 |
| `rcsb_get_entry_groups` | Entry groups | `"G_1002266"`                    |
| `rcsb_get_polymer_entity_groups` | Polymer entity groups (seq. clusters) | `"85_70"`                        |
| `rcsb_get_nonpolymer_entity_groups` | Non-polymer entity groups | `"ATP"`                          |
| `rcsb_get_uniprot` | UniProt record (single) | `"P69905"`                       |
| `rcsb_get_pubmed` | PubMed record (single, integer) | `6726807`                        |
| `rcsb_get_group_provenance` | Grouping provenance (single) | `"provenance_sequence_identity"` |
| `rcsb_describe_data_object` | Introspect an object's live GraphQL schema to build a `fields=` selection: browse a level, drill into a nested object with `into=`, or search by keyword with `query=` + `max_depth=` (flat, incl. nested + cross-object paths). Returns verified dotted paths. The Data API analogue of `rcsb_list_pdb_search_attributes`. | —                                |

The Search API only returns identifiers, so a search is the first step: batch the
returned ids into the matching `rcsb_get_*` tool to fetch titles, organisms, and
other metadata (these tools query the GraphQL endpoint, batching every requested ID
into one request). All 16 typed tools are generated from a single registry in
[`queries.py`](src/rcsb_mcp/queries.py) (`DATA_OBJECTS`), so adding a field or
endpoint is a one-line change.

### Sequence Coordinates (sequence-coordinates.rcsb.org/graphql)

Maps alignments and positional annotations between sequence reference systems
(`UNIPROT`, `NCBI_PROTEIN`, `NCBI_GENOME`, `PDB_ENTITY`, `PDB_INSTANCE`). Each
tool takes an optional `fields` argument to override the default selection; use
`rcsb_describe_seqcoord_object` to discover what fields are available.

This is the **only** RCSB API that cross-references **NCBI** (RefSeq protein /
genome) — the Data API only knows UniProt. So "what NCBI proteins map to a PDB
structure?" is answered by `rcsb_seqcoord_alignments`, not the Data API. PDB query
ids must be **entity-level** (`4HHB_1`), not a bare entry (`4HHB`); for a whole
entry, query each polymer entity.

| Tool | What it does |
|------|--------------|
| `rcsb_seqcoord_alignments` | Cross-reference a sequence across PDB / UniProt / NCBI with aligned ranges (e.g. `4HHB_1` → NCBI proteins `NP_000508`, `NP_000549`). |
| `rcsb_seqcoord_annotations` | Positional features for one sequence, from one or more annotation `sources` (`UNIPROT`, `PDB_ENTITY`, `PDB_INSTANCE`, `PDB_INTERFACE`). |
| `rcsb_seqcoord_group_alignments` | Alignments among members of a sequence group (`MATCHING_UNIPROT_ACCESSION` / `SEQUENCE_IDENTITY`). |
| `rcsb_seqcoord_group_annotations` | Annotations across a group; `summary=True` returns a positional summary. |
| `rcsb_describe_seqcoord_object` | Introspect the live schema to discover fields available on a seqcoord object (for use with `fields=`). |

### Report

| Tool | What it does |
|------|--------------|
| `rcsb_render_report` | Render a structured report of search results — title, columns, rows and evidence — into a formatted HTML document for the user. |

## Install

RCSB hosts the server, so **most clients need no install** — point them at
`https://mcp-beta.rcsb.org/mcp` (see [Connect an agent](#connect-an-agent)). Install only
to run it yourself, pin a version, or develop against it:

```bash
# run the published package without installing
uvx rcsb-mcp
# or install it
pip install rcsb-mcp
```

`rcsb-mcp` is listed in the [Official MCP Registry](https://registry.modelcontextprotocol.io)
as `io.github.rcsb/rcsb-mcp`, so registry-aware clients can discover it directly.

For local development, install from the project root instead:

```bash
pip install -e .
# or with uv
uv pip install -e .
```

## Run / test

```bash
# unit tests (no network)
hatch test          # or: python tests/test_queries.py

# run the server over stdio
python -m rcsb_mcp.server
# or, after install:
rcsb-mcp

# inspect interactively
npx @modelcontextprotocol/inspector python -m rcsb_mcp.server
```

There are two **evaluation suites** ([`evals/`](evals/)): `rcsb_pdb_eval.xml`, 14
read-only, stable questions measuring how well an LLM can drive these tools to answer real
PDB questions, and [`evals/tool_selection/`](evals/tool_selection/), a first-tool-call A/B
harness for catching routing regressions after a docstring edit. See
[`evals/README.md`](evals/README.md) to run either.

## Connect an agent

### Hosted (beta)

```
https://mcp-beta.rcsb.org/mcp
```

Streamable HTTP, no install, no API key, no account. The deployment is **stateless** — any
replica answers any request, so no session header is needed and there is nothing to keep
alive between calls. It serves the same 38 tools and the `rcsb_search_assistant` prompt as
a local run.

**Claude Code**

```bash
claude mcp add --transport http rcsb-mcp https://mcp-beta.rcsb.org/mcp
```

**Claude Desktop** — Settings → Connectors → Add custom connector, and paste the URL.

**Any client that takes a URL** (`.mcp.json`, Cursor, VS Code, Zed, …):

```json
{
  "mcpServers": {
    "rcsb-mcp": {
      "type": "http",
      "url": "https://mcp-beta.rcsb.org/mcp"
    }
  }
}
```

**Stdio-only clients** can bridge with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote):

```json
{
  "mcpServers": {
    "rcsb-mcp": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp-beta.rcsb.org/mcp"]
    }
  }
}
```

**Check it by hand** — a bare `initialize` needs no session setup:

```bash
curl -s https://mcp-beta.rcsb.org/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18","capabilities":{},
        "clientInfo":{"name":"curl","version":"0"}}}'
```

`GET /healthz` returns 200 for liveness checks.

> **Beta.** The endpoint, the tool surface and the tool descriptions may change without
> notice, and there is no stability guarantee — pin `uvx rcsb-mcp==<version>` and run it
> yourself if you need a fixed surface. When reporting a problem, include the
> `serverInfo.version` from the `initialize` response so the build is identifiable.

### Local (stdio)

Run the server as a subprocess instead — for development, or to pin a version.

Edit `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "rcsb-mcp": {
      "command": "uvx",
      "args": ["rcsb-mcp"]
    }
  }
}
```

For a local source checkout, point at the module instead:

```json
{
  "mcpServers": {
    "rcsb-mcp": {
      "command": "python",
      "args": ["-m", "rcsb_mcp.server"],
      "cwd": "/absolute/path/to/rcsb-mcp/src"
    }
  }
}
```

Restart Claude Desktop. The tools appear under the connectors (plug) icon.

## Example prompts

- "Find high-resolution human hemoglobin structures." → `rcsb_query_fulltext` + `rcsb_query_attribute` → `rcsb_query_composer` → `rcsb_search_request`
- "Human hemoglobin structures better than 2 Å, best resolution first." → same, with `sort_by` on `rcsb_search_request`
- "What PDB entries match this protein sequence: MTEY..." → `rcsb_query_sequence` → `rcsb_search_request`
- "Find structures containing a ligand like this SMILES / with formula C8H9NO2." → `rcsb_query_chemical` → `rcsb_search_request`
- "Which structures have a 3D fold similar to 4HHB?" → `rcsb_query_structure` → `rcsb_search_request`
- "Find proteins with a zinc-finger motif." → `rcsb_query_seqmotif` → `rcsb_search_request`
- "Structures of proteins with kinase activity / involved in DNA repair / in the mitochondrial membrane." → `rcsb_find_go_terms` → `rcsb_query_attribute` on `rcsb_polymer_entity_annotation.annotation_lineage.id`
- "Structures containing an SH2 domain / immunoglobulin fold." → `rcsb_find_interpro_domains` → `rcsb_query_attribute` on `rcsb_polymer_entity_annotation.annotation_id`
- "Alcohol dehydrogenase structures / any EC 3.4.21 serine protease." → `rcsb_find_enzyme_classes` → `rcsb_query_attribute` on `rcsb_polymer_entity.rcsb_ec_lineage.id`
- "Structures of proteins associated with cystic fibrosis / breast cancer." → `rcsb_find_disease_terms` → `rcsb_query_attribute` on `rcsb_uniprot_annotation.annotation_lineage.id`
- "Structures from mammals / from a particular organism or clade." → `rcsb_find_organisms` → `rcsb_query_attribute` on `rcsb_entity_source_organism.taxonomy_lineage.id`
- "Non-redundant human kinase structures (90% identity clusters)." → `rcsb_search_request` with `group_by="seqid_90"`, `return_type="polymer_entity"`
- "How many human X-ray structures are there?" → `rcsb_query_attribute` → `rcsb_search_request` with `limit=1` (read `total_count`)
- "Break down ribosome structures by experimental method / by release year." → `rcsb_search_request` with `facets`
- "Find structures with the same catalytic-site geometry as residues 162/193/219 of 2MNR." → `rcsb_query_strucmotif` → `rcsb_search_request`
- "Find chemical components under 150 Da." → `rcsb_list_pdb_search_attributes(schema="chemical")` → `rcsb_query_attribute` with `chemical_attributes=True` → `rcsb_search_request` with `return_type="mol_definition"`
- "Summarize PDB entries 4HHB, 1MBN and 6VXX." → `rcsb_get_entries`
- "What's the sequence and organism of entity 4HHB_1?" → `rcsb_get_polymer_entities`
- "Tell me about the ligand HEM." → `rcsb_get_chem_comps`
- "What's the composition of the 4HHB biological assembly?" → `rcsb_get_assemblies`
- "Which PDB entries does P69905 map to?" → `rcsb_get_uniprot`
- "Which PDB entities align to UniProt P69905, and over what ranges?" → `rcsb_seqcoord_alignments`
- "What NCBI proteins map to 4HHB?" → `rcsb_seqcoord_alignments` per entity (`4HHB_1`, `4HHB_2`), `to_ref=NCBI_PROTEIN`
- "Show UniProt features mapped onto PDB entity 4HHB_1." → `rcsb_seqcoord_annotations`
- "Pull a field the compact defaults don't include." → `rcsb_describe_data_object` to find the path, then the matching `rcsb_get_*` tool with `fields=`

## Notes

- Search endpoint: `https://search.rcsb.org/rcsbsearch/v2/query` (POST, JSON body).
- Data endpoint: `https://data.rcsb.org/graphql` (POST, GraphQL). It returns
  HTTP 200 even for query errors, reporting them in an `errors` array.
- Sequence Coordinates endpoint: `https://sequence-coordinates.rcsb.org/graphql`
  (POST, GraphQL; same HTTP-200-with-`errors` behavior).
- The `rcsb_find_*` resolvers map free text to ontology ids via EBI services — the non-RCSB
  dependencies: GO via QuickGO (`.../QuickGO/services/ontology/go/search`), InterPro and Pfam
  via EBI Search (`.../ebisearch/ws/rest/interpro7`), EC via EBI Search/IntEnz
  (`.../ebisearch/ws/rest/intenz`), disease via OLS/MONDO (`.../ols4/api/search?ontology=mondo`),
  and organisms via UniProt (`.../rest.uniprot.org/taxonomy/search`). The resolved ids then drive
  RCSB annotation searches (`rcsb_polymer_entity_annotation.*`, `rcsb_polymer_entity.rcsb_ec_lineage.id`,
  `rcsb_uniprot_annotation.annotation_lineage.id`).
- No API key required; the APIs are public. Be considerate with request volume.
- Every outbound request sends `User-Agent: rcsb-mcp/<version> (https://github.com/rcsb/rcsb-mcp)`,
  `<version>` being the installed package's (`pyproject.toml`'s) version. Set
  `RCSB_MCP_USER_AGENT` to override it (printable ASCII; a `{version}` in it is filled in the
  same way); the Helm chart does, so the hosted service's traffic is distinguishable from
  local installs in upstream logs.
- A full list of searchable attributes for `rcsb_query_attribute` is in the
  [Search API attribute reference](https://search.rcsb.org/structure-search-attributes.html);
  the Data API schema is documented at
  [data.rcsb.org/index.html#gql-api](https://data.rcsb.org/index.html#gql-api).

## Prompt

The server exposes one MCP **prompt**, `rcsb_search_assistant` ("RCSB PDB search
assistant") — the search requirements plus the HTML-report output format. Because it is
served over the protocol's `prompts` capability, any MCP client can list and invoke it
(Claude Desktop surfaces server prompts in the `+` / prompt menu); there's nothing to
copy-paste. The text lives in
[`src/rcsb_mcp/prompts/rcsb_search_assistant.md`](src/rcsb_mcp/prompts/rcsb_search_assistant.md)
and ships with the package.

Invoke it when you want answers formatted as a PDB report. It is **not** required for the
tools to work: every routing rule, gotcha and cross-reference lives on the tool descriptions
themselves, which the protocol always delivers. A server `instructions` block and a second
`rcsb_mcp_guide` prompt both used to carry that guidance and were retired — `instructions`
because clients truncate or drop it, the prompt because it is opt-in and may never be loaded.
`prompts/rcsb_mcp_guide.md` is kept on disk, unserved, as a source to rescue prose from.