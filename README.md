# rcsb-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the
[RCSB PDB Search API](https://search.rcsb.org),
[Data API](https://data.rcsb.org/graphql), and
[Sequence Coordinates API](https://sequence-coordinates.rcsb.org/graphql) to LLM
clients (Claude Desktop, MCP Inspector, Cursor, etc.).

## Tools

### Search (search.rcsb.org)

| Tool | What it does |
|------|--------------|
| `list_pdb_search_attributes` | Discover searchable attribute paths, types, and operators. `schema="structure"` (default, ~677) or `schema="chemical"` (~57: `chem_comp.*`, `drugbank_info.*`, ...). |
| `search_fulltext` | Free-text keyword search (e.g. `"CRISPR Cas9"`). |
| `search_by_attribute` | Structured search on an indexed attribute (resolution, organism, release date, ...). Supports `exists`, `negation`, `case_sensitive`, and `chemical=True` (text_chem). |
| `search_combined` | Combine free text + multiple attribute filters (AND/OR) in one query, with optional sort. |
| `search_count` | Return only the **number** of matches — for "how many ..." questions. |
| `search_facets` | Aggregate matches into buckets/statistics (terms, histogram, date_histogram, range, cardinality) — for "distribution / breakdown / per X" questions. |
| `search_by_sequence` | MMseqs2 sequence-similarity search (BLAST-like). |
| `search_by_chemical` | Chemical search by SMILES/InChI descriptor (whole-molecule or substructure) or molecular formula. |
| `search_by_structure` | 3D shape-similarity search against a reference PDB assembly or chain. |
| `search_by_seqmotif` | Short **sequence**-motif search (PROSITE pattern, regex, or simple wildcards). |
| `search_strucmotif` | 3D **structural**-motif search: structures sharing a geometric arrangement of specific residues (e.g. a catalytic triad). |
| `search_advanced` | Escape hatch: run a raw Search API query body (`return_all_hits`, grouped results, deeply nested boolean queries, ...). |

The three text tools (`search_fulltext`, `search_by_attribute`, `search_combined`)
also take `group_by_identity` (100/95/90/70/50/30) to return one representative
per sequence-identity cluster — i.e. non-redundant results. To search
chemical-component attributes, find the path with
`list_pdb_search_attributes(schema="chemical")`, then pass `chemical=True` to
`search_by_attribute` / `search_combined` (usually with `return_type="mol_definition"`).
The chemical catalog is generated from the live metadata schema by
[`scripts/generate_chemical_attributes.py`](scripts/generate_chemical_attributes.py).

### Data (data.rcsb.org/graphql)

There is one tool per Data API GraphQL root field. Each takes a **list of IDs**
(singular lookups = a one-element list) plus an optional `fields` argument to
override the curated default selection with your own GraphQL sub-selection.
Unknown IDs are reported under `not_found`.

| Tool | Object | Example ID                       |
|------|--------|----------------------------------|
| `get_entries` | PDB entries | `"4HHB"`                         |
| `get_entry_annotations` | Entry biological/functional annotations (GO, domains, disease, ...) | `"4HHB"`                         |
| `get_entry_exp_info` | Entry experimental conditions / determination metadata | `"4HHB"`                         |
| `get_polymer_entities` | Polymer entities (protein/NA) | `"4HHB_1"`                       |
| `get_nonpolymer_entities` | Ligand/cofactor entities | `"4HHB_3"`                       |
| `get_branched_entities` | Carbohydrate entities | `"5FMB_2"`                       |
| `get_polymer_entity_instances` | Polymer chains | `"4HHB.A"`                       |
| `get_nonpolymer_entity_instances` | Bound-ligand instances | `"4HHB.E"`                       |
| `get_branched_entity_instances` | Glycan chains | `"5FMB.C"`                       |
| `get_assemblies` | Biological assemblies | `"4HHB-1"`                       |
| `get_interfaces` | Assembly interfaces | `"1BMV-1.1"`                     |
| `get_chem_comps` | Chemical components / ligands | `"HEM"`, `"ATP"`                 |
| `get_entry_groups` | Entry groups | `"G_1002266"`                    |
| `get_polymer_entity_groups` | Polymer entity groups (seq. clusters) | `"85_70"`                        |
| `get_nonpolymer_entity_groups` | Non-polymer entity groups | `"ATP"`                          |
| `get_uniprot` | UniProt record (single) | `"P69905"`                       |
| `get_pubmed` | PubMed record (single, integer) | `6726807`                        |
| `get_group_provenance` | Grouping provenance (single) | `"provenance_sequence_identity"` |
| `data_graphql` | Escape hatch: run any GraphQL query against the Data API. | —                                |

The Search API only returns identifiers, so the search tools optionally
**enrich** entry hits with metadata. Enrichment and all Data API tools query
the GraphQL endpoint, batching every requested ID into one request. All 18
typed tools are generated from a single registry in
[`queries.py`](src/rcsb_mcp/queries.py) (`DATA_OBJECTS`), so adding a field or
endpoint is a one-line change.

### Sequence Coordinates (sequence-coordinates.rcsb.org/graphql)

Maps alignments and positional annotations between sequence reference systems
(`UNIPROT`, `NCBI_PROTEIN`, `NCBI_GENOME`, `PDB_ENTITY`, `PDB_INSTANCE`). Each
tool takes an optional `fields` argument to override the default selection.

This is the **only** RCSB API that cross-references **NCBI** (RefSeq protein /
genome) — the Data API only knows UniProt. So "what NCBI proteins map to a PDB
structure?" is answered by `seqcoord_alignments`, not the Data API. PDB query
ids must be **entity-level** (`4HHB_1`), not a bare entry (`4HHB`); for a whole
entry, query each polymer entity.

| Tool | What it does |
|------|--------------|
| `seqcoord_alignments` | Cross-reference a sequence across PDB / UniProt / NCBI with aligned ranges (e.g. `4HHB_1` → NCBI proteins `NP_000508`, `NP_000549`). |
| `seqcoord_annotations` | Positional features for one sequence, from one or more annotation `sources` (`UNIPROT`, `PDB_ENTITY`, `PDB_INSTANCE`, `PDB_INTERFACE`). |
| `seqcoord_group_alignments` | Alignments among members of a sequence group (`MATCHING_UNIPROT_ACCESSION` / `SEQUENCE_IDENTITY`). |
| `seqcoord_group_annotations` | Annotations across a group; `summary=True` returns a positional summary. |
| `seqcoord_graphql` | Escape hatch: run any GraphQL query against the Sequence Coordinates API. |

## Install

```bash
# from the project root
pip install -e .
# or with uv
uv pip install -e .
```

## Run / test

```bash
# unit tests (no network)
python src/rcsb_mcp/test_queries.py

# run the server over stdio
python -m rcsb_mcp.server
# or, after install:
rcsb-mcp

# inspect interactively
npx @modelcontextprotocol/inspector python -m rcsb_mcp.server
```

## Connect to Claude Desktop

Edit `claude_desktop_config.json`:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "rcsb-pdb": {
      "command": "python",
      "args": ["-m", "rcsb_mcp.server"],
      "cwd": "/absolute/path/to/rcsb-mcp/src"
    }
  }
}
```

Restart Claude Desktop. The tools appear under the connectors (plug) icon.

## Example prompts

- "Find high-resolution human hemoglobin structures." → `search_by_attribute` + `search_fulltext`
- "Human hemoglobin structures better than 2 Å, best resolution first." → `search_combined`
- "What PDB entries match this protein sequence: MTEY..." → `search_by_sequence`
- "Find structures containing a ligand like this SMILES / with formula C8H9NO2." → `search_by_chemical`
- "Which structures have a 3D fold similar to 4HHB?" → `search_by_structure`
- "Find proteins with a zinc-finger motif." → `search_by_seqmotif`
- "Non-redundant human kinase structures (90% identity clusters)." → `search_fulltext` / `search_combined` with `group_by_identity=90`
- "How many human X-ray structures are there?" → `search_count`
- "Break down ribosome structures by experimental method / by release year." → `search_facets`
- "Find structures with the same catalytic-site geometry as residues 162/193/219 of 2MNR." → `search_strucmotif`
- "Find chemical components under 150 Da." → `list_pdb_search_attributes(schema="chemical")` + `search_by_attribute` with `chemical=True`
- "Summarize PDB entries 4HHB, 1MBN and 6VXX." → `get_entries`
- "What's the sequence and organism of entity 4HHB_1?" → `get_polymer_entities`
- "Tell me about the ligand HEM." → `get_chem_comps`
- "What's the composition of the 4HHB biological assembly?" → `get_assemblies`
- "Which PDB entries does P69905 map to?" → `get_uniprot`
- "Which PDB entities align to UniProt P69905, and over what ranges?" → `seqcoord_alignments`
- "What NCBI proteins map to 4HHB?" → `seqcoord_alignments` per entity (`4HHB_1`, `4HHB_2`), `to_ref=NCBI_PROTEIN`
- "Show UniProt features mapped onto PDB entity 4HHB_1." → `seqcoord_annotations`
- "Pull a field GraphQL doesn't expose by default / combine objects." → `data_graphql`

## Notes

- Search endpoint: `https://search.rcsb.org/rcsbsearch/v2/query` (POST, JSON body).
- Data endpoint: `https://data.rcsb.org/graphql` (POST, GraphQL). It returns
  HTTP 200 even for query errors, reporting them in an `errors` array.
- Sequence Coordinates endpoint: `https://sequence-coordinates.rcsb.org/graphql`
  (POST, GraphQL; same HTTP-200-with-`errors` behavior).
- No API key required; the APIs are public. Be considerate with request volume.
- A full list of searchable attributes for `search_by_attribute` is in the
  [Search API attribute reference](https://search.rcsb.org/structure-search-attributes.html);
  the Data API schema is documented at
  [data.rcsb.org/index.html#gql-api](https://data.rcsb.org/index.html#gql-api).

## Instructions prompt

Use [AGENTS.md](./AGENTS.md) as the instruction prompt for your project.