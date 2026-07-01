# AGENTS.md — working on the rcsb-mcp repo

Guidance for AI coding agents (and humans) modifying this repository. This is an
MCP server that lets an LLM **interrogate Protein Data Bank structures** across
three RCSB APIs: Search (REST), Data (GraphQL), and Sequence Coordinates (GraphQL).

> The runtime *assistant* persona and output format are **not** here — they live
> in [`src/rcsb_mcp/prompts/pdb_assistant.md`](src/rcsb_mcp/prompts/pdb_assistant.md),
> served over MCP as the `pdb_assistant` prompt (see "Two layers" below). Keep that split.

## Layout

```
src/rcsb_mcp/
  server.py                  MCP server: @mcp.tool() tools, the @mcp.prompt() persona, HTTP calls, schema introspection
  queries.py                 PURE request-body builders (no network) + the DATA_OBJECTS registry
  search_attributes.py       SEARCH_ATTRIBUTES catalog (structure search schema)
  chemical_search_attributes.py  CHEMICAL_SEARCH_ATTRIBUTES catalog — auto-generated (see scripts/)
  prompts/pdb_assistant.md   Assistant persona + HTML-report format; served as the `pdb_assistant` MCP prompt (package data)
tests/
  test_queries.py            Network-free unit tests for the query builders
  test_server.py             Network-free tests for non-builder server logic (schema flatten), via a synthetic schema
```

## Architecture & conventions

- **Pure builders vs. I/O.** `queries.py` builds request bodies and contains **no
  network code**, so it stays unit-testable. `server.py` does the HTTP and exposes
  the tools. Keep new query-construction logic in `queries.py`.
- **The `DATA_OBJECTS` registry** (`queries.py`) drives every Data API `rcsb_get_*` tool:
  one entry per GraphQL root field (root field, id arg, batch/single, default field
  selection). **Adding a Data API object is ideally a one-line registry entry.**
- **Compact defaults + escape hatches.** Each `rcsb_get_*`/`rcsb_seqcoord_*` tool returns a
  curated compact field selection but accepts a `fields=` override; `rcsb_list_data_fields`
  (flat keyword search over an object's schema), `rcsb_describe_data_object`, and
  `rcsb_describe_seqcoord_object` introspect the live schema for field discovery;
  `rcsb_data_graphql` / `rcsb_seqcoord_graphql` are raw passthroughs. Don't try to make defaults
  exhaustive — and don't invent `fields=` paths; discover them against the live schema first.
- **Server `instructions` = tool-usage guidance only** (routing, chaining, return
  types). Do **not** put application/presentation policy there — it's always-on for
  every client. That belongs in the project prompt.

## Dev workflow

```bash
# Unit tests (no network) — run after touching queries.py or server.py
hatch test                       # or: python tests/test_queries.py; python tests/test_server.py

# Syntax check both core modules
python -m py_compile src/rcsb_mcp/server.py src/rcsb_mcp/queries.py

# Run the server over stdio (entry point: rcsb_mcp.server:main, console script `rcsb-mcp`)
python -m rcsb_mcp.server

# Inspect interactively
npx @modelcontextprotocol/inspector python -m rcsb_mcp.server
```

The package is installed editable, so source edits take effect on the next process
start. Tests live at `tests/test_queries.py` (query builders) and `tests/test_server.py`
(non-builder server logic, e.g. the schema flatten — driven by a synthetic schema, no network).

## The golden rule: validate against the live API before changing field selections

Before editing any default field selection or query body, **run the proposed
selection against the live endpoint** and confirm it returns data. This is how real
bugs were caught in this repo (a non-existent `auth_asym_id` field, id case
sensitivity, `[null]` rows for unknown ids). Pattern:

```python
import asyncio; from rcsb_mcp import server, queries
body = queries.build_data_query("entries", "4HHB", "rcsb_id <your new fields>")
print(asyncio.run(server._graphql_field(body, "entries")))
```

After validating, add/adjust the default and re-run `test_queries.py`.

## Gotchas

- **GraphQL endpoints return HTTP 200 even on query errors** — the error is in the
  `errors` array, not the status code. `_graphql_field` already raises on it.
- **ID case sensitivity.** Entry/entity/chem ids are upper-cased; group and
  `group_provenance` ids are case-sensitive opaque tokens (the `upper=False` flag in
  `DATA_OBJECTS`). Don't blanket-uppercase.
- **Unknown ids** are either dropped or returned as `null` depending on the field;
  batch handling filters `None` and reports `not_found`.
- **Sequence Coordinates: PDB ids must be entity/instance-level** (`4HHB_1`, not
  `4HHB`); only this API cross-references NCBI.
- **Claude Desktop caches MCP processes.** After code changes, fully quit & relaunch
  (⌘Q) — it does not hot-reload, and stale/duplicate processes have caused confusion.

## Two layers (don't merge them)

- **Server `instructions`** (in `server.py`) → how to *drive the tools*; always-on,
  reusable across every client/project.
- **The `pdb_assistant` MCP prompt** (`@mcp.prompt()` in `server.py`, text in
  [`prompts/pdb_assistant.md`](src/rcsb_mcp/prompts/pdb_assistant.md)) → assistant
  persona + output format (HTML report, columns, conventions); application-specific,
  **opt-in** (the user invokes it from their client's prompt menu), client-agnostic.

The markdown file is the single source of truth — `@mcp.prompt() pdb_assistant`
loads it via `Path(__file__).parent / "prompts"` and it ships as package data, so
edit the `.md` to change the persona; no code change needed. Don't fold this into
`instructions` (that would force presentation policy on every client, always).
