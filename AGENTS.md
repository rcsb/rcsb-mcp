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
  descriptions/              the model-facing ARGUMENT text, one module per tool, mirroring the
                             source modules (search/, data/, seqcoord/, resolvers/) — see below
  queries.py                 PURE request-body builders (no network) + the DATA_OBJECTS registry
  query_doc.py               the query document passed between builders and rcsb_search_request
  client.py                  endpoint URLs + HTTP (search POST, GraphQL POST)
  graphql.py                 GraphQL execution, schema introspection/flatten, error enrichment
  tooling.py                 shared tool-registration helpers
  attribute_types.py         SearchAttribute / operator / scope types shared by the catalogs
  search_attributes.py       SEARCH_ATTRIBUTES catalog (+ UNPOPULATED_/SPARSE_ lists)
                                                              — auto-generated (see scripts/)
  chemical_search_attributes.py  CHEMICAL_SEARCH_ATTRIBUTES   — auto-generated (see scripts/)
  attribute_scopes.py        which object each attribute hangs off, + nested/repeating roots
                                                              — auto-generated (see scripts/)
  prompts/rcsb_search_assistant.md   served as the `rcsb_search_assistant` MCP prompt (package data)
  prompts/rcsb_mcp_guide.md          NOT served; kept as a source to rescue prose from
tests/                       33 network-free test modules; see "Dev workflow"
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
  metadata schemas, plus one live `exists` count per attribute (~30 s): attributes no object
  holds a value for go to `UNPOPULATED_*` instead of the catalog, and depositor-reported
  numbers many entries leave empty go to `SPARSE_SEARCH_ATTRIBUTES`. Change the generator and
  re-run it; both generators have a `--check` mode for CI-style verification.

## Guidance channels (there is only one guaranteed one)

- **Tool descriptions** are the only channel the protocol always delivers, so every routing
  rule, gotcha and cross-reference lives on the tool that needs it. That is why some
  docstrings are long: they are load-bearing, and
  [`tests/test_tool_descriptions.py`](tests/test_tool_descriptions.py) pins the phrases a
  trim must not silently delete.
- **Argument docs go in the input schema, never in an `Args:` section.** Claude Code cuts every
  tool description at 2,048 characters of whitespace-collapsed text, and `Args:` sections had
  pushed five descriptions past it — in `rcsb_search_request`, 9 of its 14 guarded phrases never
  reached the model there. Schema descriptions are not cut. So each argument is
  `Annotated[..., Field(description=...)]`, its wording in `descriptions/<module>/<name>.py`
  (tool `rcsb_<name>` in `<module>.py`), with text shared by several tools of a module in that
  folder's `shared.py`. The docstring keeps what the tool is for, when to use it, and Returns.
  `tests/test_tool_descriptions.py` checks what is *delivered* (the description up to the cut,
  plus the schema), not merely what is present: every description fits, no `Args:` section
  exists, every argument is described, and each `rcsb_get_*` `fields` text names the object its
  tool queries.
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
hatch test                       # on the Docker image's Python — run this before shipping
hatch test --all                 # every Python CI tests: the image's and the requires-python floor
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

**Test on the image's Python before shipping.** A dev interpreter newer than the Docker
image lets code that only a newer Python accepts pass locally and CrashLoopBackOff the pod.
The `hatch-test` matrix in `pyproject.toml` lists the image's Python first and the
`requires-python` floor second, so plain `hatch test` runs the image's (the comment there
covers the one exception), and `tests/test_python_support.py` keeps that list in step with
the Dockerfile. A release cannot skip this: CI runs the suite on the same versions before it
builds the image.

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
- **Nested attributes: query shape selects the semantics, deliberately.** For the ~19% of
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
  returns 0 hits, reading as "no such structures"). The catalogs carry `enum` for the ~16%
  of attributes with closed vocabularies and `rcsb_query_attribute` rejects a value outside
  it. Keep that validation local — the API's own error is less legible.
- **So did an EMPTY attribute, and a sparse one still costs recall.** ~50 schema attributes
  hold no value in the search index (`rcsb_ligand_neighbors.ligand_is_bound` among them);
  the generator drops them and `rcsb_query_attribute` rejects them by name. A value filter on
  a `SPARSE_SEARCH_ATTRIBUTES` one (crystal pH: empty on 27% of X-ray entries) drops those
  entries untested, so when it ANDs with other conditions `rcsb_search_request` counts the
  ones that report the category's anchor but lack the value — at most two extra count
  requests, run alongside the search, only for those queries. The anchor is what keeps a
  cryo-EM entry from counting as "missing" a crystal pH it could never have.
- **Chemical-component paths exist in BOTH catalogs and mean different things.** As
  structure attributes they match a component only as a non-polymer ligand; with
  `chemical_attributes=True`, also inside polymers and glycans. Phosphoserine: 38 entries
  vs 2,328. `rcsb_search_request` reports it when it happens: it re-counts the query with that
  condition in the chemical index and adds a note with both counts if that finds more. Stating
  the rule in the `chemical_attributes` description was A/B-tested instead and moved nothing
  (Haiku 4.5, 0/8 -> 0/8 on the two `chem-attributes-*` probes), so don't add it back without a
  new measurement. (The one exception is the bare rcsb_id path: in the structure catalog it is
  the entry id.)
- **Claude Desktop caches MCP processes.** After code changes, fully quit & relaunch
  (⌘Q) — it does not hot-reload, and stale/duplicate processes have caused confusion.
- **The markdown docs drift, and only the cheap half is guarded.**
  `tests/test_tool_inventory.py` checks that every tool name `README.md` and this file cite
  is registered, and that the README mentions every registered tool — so a rename or removal
  fails CI. Nothing checks whether the *prose* is still true: this file once described a
  two-module layout, a `pdb_assistant` prompt and a server `instructions` block long after
  all three were gone. Update both files in the same change that renames a tool, moves a
  parameter, or splits a module.
