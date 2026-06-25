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

| Tool | What it does |
|------|--------------|
| `rcsb_list_pdb_search_attributes` | Discover searchable attribute paths, types, and operators. `schema="structure"` (default, ~677) or `schema="chemical"` (~57: `chem_comp.*`, `drugbank_info.*`, ...). |
| `rcsb_find_go_terms` | Resolve a free-text molecular function / biological process / cellular component to Gene Ontology ids (via EBI QuickGO), annotated with PDB entry counts — then search by `rcsb_polymer_entity_annotation.annotation_lineage.id`. |
| `rcsb_find_interpro_domains` | Resolve a free-text protein domain / family / fold to InterPro ids (via EBI InterPro API), annotated with PDB entry counts — then search by `rcsb_polymer_entity_annotation.annotation_id`. |
| `rcsb_find_enzyme_classes` | Resolve a free-text enzyme / reaction to Enzyme Commission (EC) numbers (via EBI Search/IntEnz), annotated with PDB entry counts — then search by `rcsb_polymer_entity.rcsb_ec_lineage.id` (hierarchical). |
| `rcsb_find_disease_terms` | Resolve a free-text disease / condition to MONDO ids (via EBI OLS), annotated with PDB entry counts — then search by `rcsb_uniprot_annotation.annotation_lineage.id` (hierarchical, UniProt-based). |
| `rcsb_find_organisms` | Resolve a free-text organism / common name / clade to NCBI Taxonomy ids (via UniProt taxonomy), annotated with PDB entry counts — then search by `rcsb_entity_source_organism.taxonomy_lineage.id` (hierarchical: a clade id matches every organism beneath it). |
| `rcsb_search_fulltext` | Free-text keyword search (e.g. `"CRISPR Cas9"`). |
| `rcsb_search_by_attribute` | Structured search on an indexed attribute (resolution, organism, release date, ...). Supports `exists`, `negation`, `case_sensitive`, and `chemical=True` (text_chem). |
| `rcsb_search_combined` | Combine free text + multiple attribute filters (AND/OR) in one query, with optional sort. |
| `rcsb_search_count` | Return only the **number** of matches — for "how many ..." questions. |
| `rcsb_search_facets` | Aggregate matches into buckets/statistics (terms, histogram, date_histogram, range, cardinality) — for "distribution / breakdown / per X" questions. |
| `rcsb_search_by_sequence` | MMseqs2 sequence-similarity search (BLAST-like). |
| `rcsb_search_by_chemical` | Chemical search by SMILES/InChI descriptor (whole-molecule or substructure) or molecular formula. |
| `rcsb_search_by_structure` | 3D shape-similarity search against a reference PDB assembly or chain. |
| `rcsb_search_by_seqmotif` | Short **sequence**-motif search (PROSITE pattern, regex, or simple wildcards). |
| `rcsb_search_strucmotif` | 3D **structural**-motif search: structures sharing a geometric arrangement of specific residues (e.g. a catalytic triad). |
| `rcsb_search_advanced` | Escape hatch: run a raw Search API query body (`return_all_hits`, grouped results, deeply nested boolean queries, ...). |

The three text tools (`rcsb_search_fulltext`, `rcsb_search_by_attribute`, `rcsb_search_combined`)
also take `group_by_identity` (100/95/90/70/50/30) to return one representative
per sequence-identity cluster — i.e. non-redundant results. To search
chemical-component attributes, find the path with
`rcsb_list_pdb_search_attributes(schema="chemical")`, then pass `chemical=True` to
`rcsb_search_by_attribute` / `rcsb_search_combined` (usually with `return_type="mol_definition"`).
The chemical catalog is generated from the live metadata schema by
[`scripts/generate_chemical_attributes.py`](scripts/generate_chemical_attributes.py).

**Paging.** Every search tool that returns hits accepts `limit` (1–100, default
10) and `offset` (default 0). Each response reports `total_count`, `has_more`,
and `next_offset`; to fetch the next page, call the tool again with the same
query and `offset` set to the returned `next_offset`.

### Data (data.rcsb.org/graphql)

There is one tool per Data API GraphQL root field. Each takes a **list of IDs**
(singular lookups = a one-element list) plus an optional `fields` argument to
override the curated default selection with your own GraphQL sub-selection.
Unknown IDs are reported under `not_found`.

| Tool | Object | Example ID                       |
|------|--------|----------------------------------|
| `rcsb_get_entries` | PDB entries | `"4HHB"`                         |
| `rcsb_get_entry_annotations` | Entry biological/functional annotations (GO, domains, disease, ...) | `"4HHB"`                         |
| `rcsb_get_entry_exp_info` | Entry experimental conditions / determination metadata | `"4HHB"`                         |
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
| `rcsb_data_graphql` | Escape hatch: run any GraphQL query against the Data API. | —                                |

The Search API only returns identifiers, so the search tools optionally
**enrich** entry hits with metadata. Enrichment and all Data API tools query
the GraphQL endpoint, batching every requested ID into one request. All 18
typed tools are generated from a single registry in
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
| `rcsb_seqcoord_graphql` | Escape hatch: run any GraphQL query against the Sequence Coordinates API. |
| `rcsb_describe_seqcoord_object` | Introspect the live schema to discover fields available on a seqcoord object (for use with `fields=`). |

## Install

```bash
# run the published package without installing (recommended for clients)
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

There is also an end-to-end **evaluation suite** ([`evals/`](evals/)) — 10
read-only, stable questions that measure how well an LLM can drive these tools to
answer real PDB questions. See [`evals/README.md`](evals/README.md) to run it.

## Connect to Claude Desktop

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

- "Find high-resolution human hemoglobin structures." → `rcsb_search_by_attribute` + `rcsb_search_fulltext`
- "Human hemoglobin structures better than 2 Å, best resolution first." → `rcsb_search_combined`
- "What PDB entries match this protein sequence: MTEY..." → `rcsb_search_by_sequence`
- "Find structures containing a ligand like this SMILES / with formula C8H9NO2." → `rcsb_search_by_chemical`
- "Which structures have a 3D fold similar to 4HHB?" → `rcsb_search_by_structure`
- "Find proteins with a zinc-finger motif." → `rcsb_search_by_seqmotif`
- "Structures of proteins with kinase activity / involved in DNA repair / in the mitochondrial membrane." → `rcsb_find_go_terms` → `rcsb_search_by_attribute` on `rcsb_polymer_entity_annotation.annotation_lineage.id`
- "Structures containing an SH2 domain / immunoglobulin fold." → `rcsb_find_interpro_domains` → `rcsb_search_by_attribute` on `rcsb_polymer_entity_annotation.annotation_id`
- "Alcohol dehydrogenase structures / any EC 3.4.21 serine protease." → `rcsb_find_enzyme_classes` → `rcsb_search_by_attribute` on `rcsb_polymer_entity.rcsb_ec_lineage.id`
- "Structures of proteins associated with cystic fibrosis / breast cancer." → `rcsb_find_disease_terms` → `rcsb_search_by_attribute` on `rcsb_uniprot_annotation.annotation_lineage.id`
- "Structures from mammals / from a particular organism or clade." → `rcsb_find_organisms` → `rcsb_search_by_attribute` on `rcsb_entity_source_organism.taxonomy_lineage.id`
- "Non-redundant human kinase structures (90% identity clusters)." → `rcsb_search_fulltext` / `rcsb_search_combined` with `group_by_identity=90`
- "How many human X-ray structures are there?" → `rcsb_search_count`
- "Break down ribosome structures by experimental method / by release year." → `rcsb_search_facets`
- "Find structures with the same catalytic-site geometry as residues 162/193/219 of 2MNR." → `rcsb_search_strucmotif`
- "Find chemical components under 150 Da." → `rcsb_list_pdb_search_attributes(schema="chemical")` + `rcsb_search_by_attribute` with `chemical=True`
- "Summarize PDB entries 4HHB, 1MBN and 6VXX." → `rcsb_get_entries`
- "What's the sequence and organism of entity 4HHB_1?" → `rcsb_get_polymer_entities`
- "Tell me about the ligand HEM." → `rcsb_get_chem_comps`
- "What's the composition of the 4HHB biological assembly?" → `rcsb_get_assemblies`
- "Which PDB entries does P69905 map to?" → `rcsb_get_uniprot`
- "Which PDB entities align to UniProt P69905, and over what ranges?" → `rcsb_seqcoord_alignments`
- "What NCBI proteins map to 4HHB?" → `rcsb_seqcoord_alignments` per entity (`4HHB_1`, `4HHB_2`), `to_ref=NCBI_PROTEIN`
- "Show UniProt features mapped onto PDB entity 4HHB_1." → `rcsb_seqcoord_annotations`
- "Pull a field GraphQL doesn't expose by default / combine objects." → `rcsb_data_graphql`

## Notes

- Search endpoint: `https://search.rcsb.org/rcsbsearch/v2/query` (POST, JSON body).
- Data endpoint: `https://data.rcsb.org/graphql` (POST, GraphQL). It returns
  HTTP 200 even for query errors, reporting them in an `errors` array.
- Sequence Coordinates endpoint: `https://sequence-coordinates.rcsb.org/graphql`
  (POST, GraphQL; same HTTP-200-with-`errors` behavior).
- The `rcsb_find_*` resolvers map free text to ontology ids via EBI services — the non-RCSB
  dependencies: GO via QuickGO (`.../QuickGO/services/ontology/go/search`), InterPro
  (`.../interpro/api/entry/interpro/`), EC via EBI Search/IntEnz (`.../ebisearch/ws/rest/intenz`),
  and disease via OLS/MONDO (`.../ols4/api/search?ontology=mondo`). The resolved ids then drive
  RCSB annotation searches (`rcsb_polymer_entity_annotation.*`, `rcsb_polymer_entity.rcsb_ec_lineage.id`,
  `rcsb_uniprot_annotation.annotation_lineage.id`).
- No API key required; the APIs are public. Be considerate with request volume.
- A full list of searchable attributes for `rcsb_search_by_attribute` is in the
  [Search API attribute reference](https://search.rcsb.org/structure-search-attributes.html);
  the Data API schema is documented at
  [data.rcsb.org/index.html#gql-api](https://data.rcsb.org/index.html#gql-api).

## Instructions prompt

Use [prompts/pdb-assistant.md](./prompts/pdb-assistant.md) as the instruction prompt for your project.