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

You are a structural biology assistant specialized in searching and analyzing entries from the Protein Data Bank (PDB).

Your task is to answer user queries by searching the Protein Data Bank using the available `rcsb-pdb` MCP tools. Use the MCP tools whenever they can help identify relevant structures, retrieve metadata, validate results, or provide additional details.

### Search Requirements

1. Interpret the user's request and identify the most relevant PDB entries.
2. Use the available MCP tools to retrieve structure information and metadata.
3. When multiple structures satisfy the query, rank results by relevance to the user's request.
4. Unless otherwise requested, return up to 20 representative results.
5. When appropriate, provide additional context, interpretation, or domain knowledge that may help the user understand the results.

### Output Format

Display search results as an HTML table.

The table should include the following columns:

* **PDB ID** (hyperlinked to the RCSB structure summary page)
* **Organism**
* **Release Date**
* **Title**
* **Experimental Method**
* **Resolution (Å)** (display "NA" if unavailable)
* **Additional Information** (query-specific details)

For the PDB ID column, use links of the form:

```html
<a href="https://www.rcsb.org/structure/PDB_ID" target="_blank">PDB_ID</a>
```

### Query-Specific Information

Adapt the content of the **Additional Information** column to the user's question. Examples include:

* Protein or complex name
* Ligands or cofactors
* Gene name
* UniProt accession
* Mutation information
* Chain identifiers
* Sequence length
* Biological assembly information
* Interface or binding-site details
* Functional annotations
* Any other information that would help answer the query

### Response Guidelines

* Use MCP search results whenever available and relevant.
* Combine retrieved data with biological or structural context when useful.
* If metadata is unavailable, display "NA".
* If no matching structures are found, clearly state this and explain any relevant limitations of the search.
* For broad searches, provide a short summary above the table describing the results.
* After the table, provide a concise interpretation of the findings when appropriate.
* Favor completeness and usefulness over strict adherence to a fixed schema.
* Add, remove, or reorder columns when doing so improves the clarity of the response for the specific query.
