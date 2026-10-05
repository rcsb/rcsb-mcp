# AGENTS.md — working on the rcsb-mcp repo

Guidance for AI coding agents (and humans) modifying this repository. This is an
MCP server that lets an LLM **interrogate Protein Data Bank structures** across
three RCSB APIs: Search (REST), Data (GraphQL), and Sequence Coordinates (GraphQL).

> The runtime *assistant* persona and output format are **not** here — they live
> in [`src/rcsb_mcp/prompts/rcsb_search_assistant.md`](src/rcsb_mcp/prompts/rcsb_search_assistant.md),
> served over MCP as the `rcsb_search_assistant` prompt (see "Guidance channels" below).
> Keep that split.

## Layout

```
src/rcsb_mcp/
  server.py                  composition root: builds the FastMCP app, registers each tool
                             package, serves the prompt, mounts the report route
  search.py                  rcsb_query_* builders, rcsb_query_composer, rcsb_search_request,
                             rcsb_list_pdb_search_attributes + local filter validation
  data.py                    rcsb_get_* tools (one per Data API root field) + rcsb_describe_data_object
  resolvers.py               rcsb_find_* free-text -> ontology-id resolvers (EBI/UniProt backends)
  seqcoord.py                rcsb_seqcoord_* tools + rcsb_describe_seqcoord_object
  report/                    rcsb_render_report: models, render, link packing, routes, store
  queries.py                 PURE request-body builders (no network) + the DATA_OBJECTS registry
  query_doc.py               the query document passed between builders and rcsb_search_request
  client.py                  endpoint URLs + HTTP (search POST, GraphQL POST)
  graphql.py                 GraphQL execution, schema introspection/flatten, error enrichment
  tooling.py                 shared tool-registration helpers
  attribute_types.py         SearchAttribute / operator / scope types shared by the catalogs
  search_attributes.py       SEARCH_ATTRIBUTES catalog        — auto-generated (see scripts/)
  chemical_search_attributes.py  CHEMICAL_SEARCH_ATTRIBUTES   — auto-generated (see scripts/)
  attribute_scopes.py        which object each attribute hangs off, + nested/repeating roots
                                                              — auto-generated (see scripts/)
  prompts/rcsb_search_assistant.md   served as the `rcsb_search_assistant` MCP prompt (package data)
  prompts/rcsb_mcp_guide.md          NOT served; kept as a source to rescue prose from
tests/                       31 network-free test modules; see "Dev workflow"
scripts/                     generate_search_attributes.py, generate_attribute_scopes.py
evals/                       end-to-end accuracy suite + tool_selection A/B probe harness
```

## Architecture & conventions

- **Pure builders vs. I/O.** `queries.py` builds request bodies and contains **no
  network code**, so it stays unit-testable. `client.py` / `graphql.py` do the HTTP; the
  per-domain modules expose the tools. Keep new query-construction logic in `queries.py`.
- **Search is two layers: build, then execute.** The `rcsb_query_*` tools are pure and
  return a *query document* (readable JSON + digest, see `query_doc.py`); nothing is
  searched until `rcsb_search_request` runs one. `rcsb_query_composer` joins documents
  with AND/OR. Every output option (`return_type`, paging, `all_hits`, `facets`, `sort_by`,
  `group_by`) lives on `rcsb_search_request` and **nowhere else** — a parameter advertised
  on a builder is a bug, and `tests/test_doc_claims.py` exists because that drifted once.
- **The `DATA_OBJECTS` registry** (`queries.py`) drives every Data API `rcsb_get_*` tool:
  one entry per GraphQL root field (root field, id arg, batch/single, default field
  selection). **Adding a Data API object is ideally a one-line registry entry.**
- **Compact defaults + `fields=` overrides.** Each `rcsb_get_*`/`rcsb_seqcoord_*` tool returns a
  curated compact field selection but accepts a `fields=` override; `rcsb_describe_data_object`
  (browse a level, drill in with `into=`, or keyword-search the schema with `query=` +
  `max_depth=`) and `rcsb_describe_seqcoord_object` introspect the live schema for field
  discovery. There is no raw-GraphQL passthrough tool. Don't try to make defaults
  exhaustive — and don't invent `fields=` paths; discover them against the live schema first.
- **Generated data is never hand-edited.** The three catalogs above come from the live
  metadata schemas. Change the generator and re-run it; `scripts/generate_attribute_scopes.py`
  has a `--check` mode for CI-style verification.

## Guidance channels (there is only one guaranteed one)

- **Tool descriptions** are the only channel the protocol always delivers, so every routing
  rule, gotcha and cross-reference lives on the tool that needs it. That is why some
  docstrings are long: they are load-bearing, and
  [`tests/test_tool_descriptions.py`](tests/test_tool_descriptions.py) pins the phrases a
  trim must not silently delete.
- **The `rcsb_search_assistant` prompt** (`@mcp.prompt()` in `server.py`, text in
  [`prompts/rcsb_search_assistant.md`](src/rcsb_mcp/prompts/rcsb_search_assistant.md)) carries
  the search requirements and HTML-report format. It is **opt-in** — the user invokes it from
  their client's prompt menu — so nothing a client needs in order to drive the tools may live
  only here.
- **A server `instructions` block no longer exists.** It was retired because clients truncate
  or drop it (Claude Code cuts at 2048 chars, discarding ~85% of what was there). A second
  `rcsb_mcp_guide` prompt was retired for the same reason the assistant prompt can't be
  relied on: opt-in. Do not reintroduce either as the home for tool guidance.

## Dev workflow

```bash
# Unit tests, no network. Run after touching anything under src/.
hatch test                       # 3.11, the Docker floor — this is the one that gates shipping
python -m pytest tests/ -q       # same suite on the dev interpreter
python tests/test_queries.py     # individual modules still run standalone

# Syntax check the package
python -m compileall -q src/rcsb_mcp

# Regenerate the derived catalogs after a schema change
python scripts/generate_search_attributes.py
python scripts/generate_attribute_scopes.py --check

# Run the server over stdio (entry point: rcsb_mcp.server:main, console script `rcsb-mcp`)
python -m rcsb_mcp.server

# Inspect interactively
npx @modelcontextprotocol/inspector python -m rcsb_mcp.server
```

**Test on 3.11 before shipping.** The dev venv is newer than the Docker image; a
3.12-only construct passes locally and CrashLoopBackOffs the pod. `hatch test` is the
3.11 run.

The package is installed editable, so source edits take effect on the next process start.

## The golden rule: validate against the live API before changing field selections

Before editing any default field selection or query body, **run the proposed
selection against the live endpoint** and confirm it returns data. This is how real
bugs were caught in this repo (a non-existent `auth_asym_id` field, id case
sensitivity, `[null]` rows for unknown ids). Pattern:

```python
import asyncio; from rcsb_mcp import graphql, queries
body = queries.build_data_query("entries", ["4HHB"], "rcsb_id <your new fields>")
print(asyncio.run(graphql._graphql_field(body, "entries")))
```

For the Search API, post a body and read `total_count`; when a change is supposed to
*narrow* a result, check the count went DOWN. Several bugs here announced themselves as a
count that grew when a restriction was added.

After validating, add/adjust the default and re-run the suite.

## Gotchas

- **GraphQL endpoints return HTTP 200 even on query errors** — the error is in the
  `errors` array, not the status code. `graphql._graphql_field` already raises on it, and
  `_enrich_field_errors` rewrites an undefined-field error (a bad `fields=` guess) into a
  self-correcting hint: where that field actually lives + the discovery tool. Keep that
  enrichment OUT of model-facing prose — telling the model wrong guesses get auto-corrected
  would undercut the "discover fields first, don't invent them" rule.
- **Nested attributes: query shape selects the semantics, deliberately.** For the ~22% of
  attributes carrying a `nested_group`, conditions in ONE group (with nothing else in it)
  must hold on the SAME record; conditions in separate groups are matched independently.
  Both are valid and mean different things, so this is **not** something to normalise away —
  `queries._pins_a_nested_record` stops `rcsb_query_composer` splicing a group the caller
  built on purpose. `tests/test_nested_record_coherence.py` carries the measurements.
- **Never compose an id by convention.** `<ENTRY>_1`, `<ENTRY>.A` and `<ENTRY>-1` almost
  always exist, so a guessed id returns real data about the wrong molecule and never lands
  in `not_found`. Take ids from a search hit or from `rcsb_get_entries`. The tool
  descriptions say this; don't weaken them.
- **ID case sensitivity.** Entry/entity/chem ids are upper-cased; group and
  `group_provenance` ids are case-sensitive opaque tokens (the `upper=False` flag in
  `DATA_OBJECTS`). Don't blanket-uppercase.
- **Unknown ids** are either dropped or returned as `null` depending on the field;
  batch handling filters `None` and reports `not_found`.
- **Sequence Coordinates: PDB ids must be entity/instance-level** (`4HHB_1`, not
  `4HHB`); only this API cross-references NCBI.
- **A wrong filter VALUE used to fail silently** (`"cryo-EM"` vs `ELECTRON MICROSCOPY`
  returns 0 hits, reading as "no such structures"). The catalogs carry `enum` for the ~15%
  of attributes with closed vocabularies and `rcsb_query_attribute` rejects a value outside
  it. Keep that validation local — the API's own error is less legible.
- **Claude Desktop caches MCP processes.** After code changes, fully quit & relaunch
  (⌘Q) — it does not hot-reload, and stale/duplicate processes have caused confusion.
- **The markdown docs drift, and only the cheap half is guarded.**
  `tests/test_tool_inventory.py` checks that every tool name `README.md` and this file cite
  is registered, and that the README mentions every registered tool — so a rename or removal
  fails CI. Nothing checks whether the *prose* is still true: this file once described a
  two-module layout, a `pdb_assistant` prompt and a server `instructions` block long after
  all three were gone. Update both files in the same change that renames a tool, moves a
  parameter, or splits a module.
