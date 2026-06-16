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
| `search_by_attribute` | Structured search on an indexed attribute (resolution, organism, release date, ...). |
| `search_combined` | Combine free text + multiple attribute filters (AND/OR) in one query, with optional sort. |
| `search_by_sequence` | MMseqs2 sequence-similarity search (BLAST-like). |

### Data (data.rcsb.org/graphql)

| Tool | What it does |
|------|--------------|
| `get_entry` | Metadata summary (title, method, resolution, date) for one PDB ID. |
| `get_entries` | Same summary for many PDB IDs in a single batched request. |
| `get_polymer_entity` | Description / sequence / length / organism for a polymer entity, e.g. `"4HHB_1"` (what `search_by_sequence` returns). |
| `get_chem_comp` | Name / formula / weight / SMILES / InChIKey for a ligand or chemical component, e.g. `"HEM"`, `"ATP"`. |
| `data_graphql` | Escape hatch: run an arbitrary GraphQL query against the Data API (assemblies, instances, UniProt, interfaces, ...). |

The Search API only returns identifiers, so the search tools optionally
**enrich** entry hits with metadata. Enrichment and all Data API tools query
the GraphQL endpoint, batching every requested ID into one request.

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
- "Summarize PDB entry 4HHB." → `get_entry`
- "Summarize entries 4HHB, 1MBN and 6VXX." → `get_entries`
- "What's the sequence and organism of entity 4HHB_1?" → `get_polymer_entity`
- "Tell me about the ligand HEM." → `get_chem_comp`
- "Get the assembly composition of 4HHB." → `data_graphql`

## Notes

- Search endpoint: `https://search.rcsb.org/rcsbsearch/v2/query` (POST, JSON body).
- Data endpoint: `https://data.rcsb.org/graphql` (POST, GraphQL). It returns
  HTTP 200 even for query errors, reporting them in an `errors` array.
- No API key required; the APIs are public. Be considerate with request volume.
- A full list of searchable attributes for `search_by_attribute` is in the
  [Search API attribute reference](https://search.rcsb.org/structure-search-attributes.html);
  the Data API schema is documented at
  [data.rcsb.org/index.html#gql-api](https://data.rcsb.org/index.html#gql-api).
