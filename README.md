# rcsb-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the
[RCSB PDB Search API](https://search.rcsb.org) and
[Data API](https://data.rcsb.org/graphql) to LLM clients (Claude Desktop,
MCP Inspector, Cursor, etc.).

## Tools

### Search (search.rcsb.org)

| Tool | What it does |
|------|--------------|
| `search_fulltext` | Free-text keyword search (e.g. `"CRISPR Cas9"`). |
| `search_by_attribute` | Structured search on an indexed attribute (resolution, organism, release date, ...). Supports `exists`, `negation`, and `case_sensitive`. |
| `search_combined` | Combine free text + multiple attribute filters (AND/OR) in one query, with optional sort. |
| `search_by_sequence` | MMseqs2 sequence-similarity search (BLAST-like). |
| `search_by_chemical` | Chemical search by SMILES/InChI descriptor (whole-molecule or substructure) or molecular formula. |
| `search_by_structure` | 3D shape-similarity search against a reference PDB assembly or chain. |
| `search_by_seqmotif` | Short sequence-motif search (PROSITE pattern, regex, or simple wildcards). |
| `search_advanced` | Escape hatch: run a raw Search API query body (facets, `return_all_hits`, `return_counts`, grouped results, strucmotif, ...). |

The three text tools (`search_fulltext`, `search_by_attribute`, `search_combined`)
also take `group_by_identity` (100/95/90/70/50/30) to return one representative
per sequence-identity cluster — i.e. non-redundant results.

### Data (data.rcsb.org/graphql)

There is one tool per Data API GraphQL root field. Each takes a **list of IDs**
(singular lookups = a one-element list) plus an optional `fields` argument to
override the curated default selection with your own GraphQL sub-selection.
Unknown IDs are reported under `not_found`.

| Tool | Object | Example ID |
|------|--------|------------|
| `get_entries` | PDB entries | `"4HHB"` |
| `get_polymer_entities` | Polymer entities (protein/NA) | `"4HHB_1"` |
| `get_nonpolymer_entities` | Ligand/cofactor entities | `"4HHB_3"` |
| `get_branched_entities` | Carbohydrate entities | `"5FMB_2"` |
| `get_polymer_entity_instances` | Polymer chains | `"4HHB.A"` |
| `get_nonpolymer_entity_instances` | Bound-ligand instances | `"4HHB.E"` |
| `get_branched_entity_instances` | Glycan chains | `"5FMB.C"` |
| `get_assemblies` | Biological assemblies | `"4HHB-1"` |
| `get_interfaces` | Assembly interfaces | `"1BMV-1.1"` |
| `get_chem_comps` | Chemical components / ligands | `"HEM"`, `"ATP"` |
| `get_entry_groups` | Entry groups | group ID |
| `get_polymer_entity_groups` | Polymer entity groups (seq. clusters) | `"85_70"` |
| `get_nonpolymer_entity_groups` | Non-polymer entity groups | group ID |
| `get_uniprot` | UniProt record (single) | `"P69905"` |
| `get_pubmed` | PubMed record (single, integer) | `6726807` |
| `get_group_provenance` | Grouping provenance (single) | `"provenance_sequence_identity"` |
| `data_graphql` | Escape hatch: run any GraphQL query against the Data API. | — |

The Search API only returns identifiers, so the search tools optionally
**enrich** entry hits with metadata. Enrichment and all Data API tools query
the GraphQL endpoint, batching every requested ID into one request. All 16
typed tools are generated from a single registry in
[`queries.py`](src/rcsb_mcp/queries.py) (`DATA_OBJECTS`), so adding a field or
endpoint is a one-line change.

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
python tests/test_queries.py

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
- "Summarize PDB entries 4HHB, 1MBN and 6VXX." → `get_entries`
- "What's the sequence and organism of entity 4HHB_1?" → `get_polymer_entities`
- "Tell me about the ligand HEM." → `get_chem_comps`
- "What's the composition of the 4HHB biological assembly?" → `get_assemblies`
- "Which PDB entries does P69905 map to?" → `get_uniprot`
- "Pull a field GraphQL doesn't expose by default / combine objects." → `data_graphql`

## Notes

- Search endpoint: `https://search.rcsb.org/rcsbsearch/v2/query` (POST, JSON body).
- Data endpoint: `https://data.rcsb.org/graphql` (POST, GraphQL). It returns
  HTTP 200 even for query errors, reporting them in an `errors` array.
- No API key required; the APIs are public. Be considerate with request volume.
- A full list of searchable attributes for `search_by_attribute` is in the
  [Search API attribute reference](https://search.rcsb.org/structure-search-attributes.html);
  the Data API schema is documented at
  [data.rcsb.org/index.html#gql-api](https://data.rcsb.org/index.html#gql-api).
