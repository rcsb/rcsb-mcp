# Token-surface reduction: decision memo

**Baseline re-verified for this memo**: `measure.py --src /Users/joan/devel/rcsb-mcp/src` → **39 tools = 23,199 tok** (desc 11,815 / schema 9,789), instructions 3,307 tok. Every Δ below is anchored to that run.

---

## 1. The answer

**Merge: yes — but the partial merge (5 specialists → 1), not the 7→1.** The full merge is worth **1,608 tok (6.9%) more** than the partial and costs you the two highest-traffic tool names, a new `service="chemical"` / `chemical_attributes=True` naming collision, and the entire routing gamble applied to keyword and attribute search. That is the worst risk-adjusted trade on the board.

**And it is not the first thing to ship.** Roughly **-2,180 tok (-9.4%)** is available today at zero risk with a shipped implementation and a 161-case guard test, and a separate **correctness bug** is currently discarding 84.8% of the server `instructions` you wrote.

### Ranked options

| # | Option | Measured Δ (always-on) | % of 23,199 | Risk | Stacks? | Number status |
|---|---|---|---|---|---|---|
| 0 | **Fix the 2048-char `instructions` truncation** | 0 saved; **recovers 2,815 tok of authored guidance** | — | none | independent | **Measured, corroborated first-hand in this session** |
| 1 | **Lossless schema compaction** (strip auto-`title`, `default:null`, `additionalProperties:true`, inline single-use `$defs`) | **-2,180** | **-9.40%** | none | with everything | Measured; implemented + 161-case guard test |
| 2 | **`structured_output=False` on all 39 tools** | **-1,152** always-on, **plus -35% on every response** | -4.97% | low-med (breaks `structuredContent` readers) | with everything | Wire payload measured; *billing impact unverified* |
| 3 | **Compact response serialization** (kill `indent=2`) | 0 always-on; **-1,093 tok on one 100-hit search** | — | near-zero | with everything | Measured on live call |
| 4 | **Hidden deprecation aliases** (registered, unlisted) | 0 | — | low (lowlevel SDK behaviour) | enables 7/8 | Proven end-to-end over real protocol path |
| 5 | **`render_report` design-rationale docstrings → `#` comments** | -234 on that tool (-622 surface-wide) | -1.0% / -2.7% | none | yes | Measured |
| 6 | **Variant C — prose trim only** (delete Args blocks already in `instructions`, sortability rule → runtime `ValueError`) | **-2,854** | **-12.30%** | **med** — relocates 1,605 tok into the truncated channel (see §2) | **overlaps the merge 79%** | Measured, 186 tests pass |
| 7 | **Variant A/F — partial merge** (5 specialists → `rcsb_search_by_similarity`; fulltext + by_attribute keep their names) | A **-4,360** / F (+trim) **-5,603** | -18.79% / -24.15% | med-high — 5 deployed names removed | partially | Measured, 185/186 tests pass, 21/21 byte-identical request bodies |
| 8 | **Variant D/E — full 7→1 merge** | D **-6,905** / E (+trim) **-7,444** | -29.76% / -32.09% | **high** — 7 names removed, routing unmeasured | partially | Measured twice independently (-6,905 / -6,935, 30-tok drift) |
| 9 | **URL-scoped tool profiles** (`?profile=search`) | 39 tools/25,376 → 9 tools/12,709 **on that URL only** | -50% for opt-in clients | none on default path | orthogonal | Prototype verified over real streamable-HTTP |
| — | ~~Variant B — shared-options sub-model~~ | **+1,414** | **+6.10%** | — | — | **Measured. Reject.** |
| — | ~~Advertised alias shim during migration~~ | net -1,019 only | -4.4% | — | — | Measured. Only 14.7% of the win lands. |
| — | Flatten `anyOf:[X,null]` | -860 in stack | -3.7% | **semantically narrowing**; also destroys the merge's fail-fast sentinel | conflicts with 7/8 | Measured, deliberately not wired |

### The realistic combined ladder (all measured on top of each other, not summed)

| Configuration | tok | Δ | Δ% |
|---|---|---|---|
| baseline | 23,199 | — | — |
| lossless compaction only | **21,019** | -2,180 | -9.4% |
| + trim (C) | **18,161** | -5,038 | -21.7% |
| + partial merge (A) instead of trim | 17,068 | -6,131 | -26.4% |
| + partial merge **and** trim (F) | **15,821** | -7,378 | **-31.8%** |
| + full merge and trim (E) | **14,213** | -8,986 | **-38.7%** |

Two independent implementations of the lossless stack landed at 21,019 and 21,024 — agreement within 5 tok, which is the strongest validity signal in the whole exercise.

---

## 2. Two facts that change the frame — both corroborated first-hand in this session

**(a) The `instructions` block is truncated at exactly 2048 characters.** `rcsb_mcp_guide.md` is 13,455 chars; **15.2% is delivered, 84.8% is discarded**. The copy in my own system context this session ends mid-word at `"...add a free-text keyword to t"` — character 2048 exactly, verified against the file. This is not "Claude web drops instructions"; the text is delivered and then silently cut. **49 tool-description cross-references point into the discarded 85%.**

This directly downgrades option 6 (variant C), whose entire thesis is "this prose is already in the always-on `instructions` block". For most of the 7 params it is — but past character 2048, so for this client it is not delivered at all. **C must not ship before the truncation is fixed**, or it converts duplicated-but-delivered prose into deleted prose.

**(b) This client defers all 39 tool schemas.** Every `rcsb_*` tool appears in my context as a name only, materialized on demand. Resident cost is ~1,519 tok, not 25,374. Under deferral, *total surface is nearly irrelevant* and what matters is per-tool size at materialization plus name/description retrievability — which is an argument **against** collapsing 7 retrievable intent-named entry points into one.

Neither observation generalizes without testing: Claude web/desktop and the self-hosted vLLM portal are unmeasured. **The experiment: point each client at the deployed endpoint, send one trivial prompt, read turn-1 input tokens. ~25k = eager, ~1.5k = deferred.** For the portal you control the loop, so you decide.

**(c) Corrected baseline.** `measure.py` counts `name + description + inputSchema` only. The real `tools/list` payload also carries `outputSchema` (1,074 tok) and `annotations` (984 tok): **the true always-on surface is 25,374 tok**, and 2,175 of it has never been counted. Option 2 removes 1,152 of that.

---

## 3. The stacking question — answered with a measurement, not arithmetic

The merge and the prose trim target the same duplicated text. They are **not additive**:

| | Δ |
|---|---|
| full merge alone (D) | -6,905 |
| trim alone (C) | -2,854 |
| naive sum | -9,759 |
| **actually measured together (E)** | **-7,444** |
| **overlap** | **2,315 tok — 79% of the trim** |

The trim's residual value is proportional to how many search tools survive it, and this was verified at three points:

| trim applied on top of | search tools left | trim's marginal Δ | % of its standalone 2,854 |
|---|---|---|---|
| baseline | 7 | -2,854 | 100% |
| partial merge (A) | 3 | -1,243 | 44% |
| full merge (D) | 1 | -539 | 19% |

**Budget the merge and the trim as one win.** Ship the trim first and the full merge's remaining value falls from 6,905 to 5,410. Ship the merge first and the trim's falls to 539.

The lossless encoding ladder is the only lever that is genuinely orthogonal — it is still worth **-1,775** on top of variant F and **-1,542** on top of E.

---

## 4. Is merging the 7 into one tool a good idea?

**The pro-merge case, with the number that carries it.** Reducing tool count is the *only* structural lever on cross-tool duplication, and this is now proven rather than argued. MCP hands each tool a standalone `inputSchema` with no cross-tool sharing, so:

- **`AttributeFilter` alone is duplicated 7×: 361 tok each = 2,166 tok (9.34% of the surface) of pure redundancy that no encoding trick can touch.**
- The natural "keep the names, share the params" fix was built and measured: variant B is **+1,414 tok (+6.1%)** — pydantic emits the whole `$defs.SearchOptions` block seven times, plus seven `$ref` wrappers. Moving prose from a docstring into `Field(description=...)` costs **+3,549 tok** for the same words. **Any shared-object design is strictly dominated.**

**The routing objection on record is weaker than it looks.** Measured: `rcsb_search_by_chemical` is named in **no tool description anywhere**; `by_sequence` in one; `by_structure`/`by_seqmotif` only inside strucmotif's contrast sentence. For the four services that most need routing help, **the only always-delivered routing signal today is the tool name itself** — the INTENT table lives in `instructions`, i.e. past character 2048. A merge relocates that table into the tool description, the channel that is always delivered. And the merge converts a class of silent errors into loud ones: `service="structure"` + `residue_ids` is rejected by name, whereas today `rcsb_search_by_structure(entry_id="4CHA")` silently runs a whole-shape search instead of a motif search.

**The honest marginal price.** One agent priced the merge's marginal value at only 1,871 tok (8.1%) against a no-merge de-dup "ceiling" of -5,064. That ceiling is **not shippable** — realising it requires either the shared-options object (measured at +1,414) or the postponed builder/executor split, which pays two round trips on every search. Against the best design you can actually ship without touching a tool name (lossless + trim = 18,161):

| merge variant | marginal Δ vs 18,161 | % of baseline |
|---|---|---|
| partial (F + lossless = 15,821) | **-2,340** | **-10.1%** |
| full (E + lossless = 14,213) | **-3,948** | **-17.0%** |

**What the merge costs, measured.** The prototype's emitted schema has `required: ["service"]`, 36 properties, and **no `oneOf` / `if`-`then` / `dependentRequired` anywhere**. So 8 requiredness constraints that were schema-enforced (and unrepresentable as malformed calls under constrained decoding) become prose plus a runtime `ValueError`, and 17 concrete defaults become `default: null`. Per service, the fraction of *visible* params that are illegal runs **44–64%** (baseline: 0%, at 12–19 params).

The counter-objection — that the extra round trips eat the win — **does not survive arithmetic**. Break-even requires a **12–75% inflation in request count** depending on caching and conversation length. The real cost is a 2–5 s stall and a visible self-correction in a user-facing chat portal: a UX cost, not a token cost. Note also that the tool-block delta of -29.9% is only **13.6% of total input token-equivalents at 16 turns with caching**.

### Recommendation

**Ship the partial merge (variant A, then F).** Fold `sequence`, `chemical`, `structure`, `seqmotif`, `strucmotif` into one `rcsb_search_by_similarity` with a `service` discriminator. Keep `rcsb_search_fulltext` and `rcsb_search_by_attribute` as first-class names.

Justifying numbers:
- Those five tools are **91% redundant prose** (by_sequence's unique content is five one-line Args entries). Fulltext and by_attribute carry the routing triangle, "an empty result is a valid answer", "score is text-relevance NOT biological importance", the `attributes` shape example, and the AND/OR/NOT gotcha — **1,572 tok of genuinely unique routing signal lives in the 7 descriptions and most of it is in those two**.
- F + lossless = **15,821 tok (-31.8%)** vs E + lossless = 14,213 (-38.7%). The full merge's extra 1,608 tok buys the loss of the two names with the highest reference counts (30 and 24), plus the `chemical` → `chemical_attributes` rename which **variant A does not need at all** (that flag only ever applied to fulltext/by_attribute).
- The four services with no name-based routing guidance are exactly the ones A merges. Agent evidence that undercuts the routing objection undercuts it **precisely for the specialists**, not for fulltext/attribute.

### What would change the answer to "full 7→1"

1. A rewritten `evals/tool_selection` A/B at k≥20 on the target model showing **no per-service confusion-matrix regression** for fulltext and by_attribute.
2. Confirmation that the portal (and Claude web) load tools **eagerly**, making the extra 1,608 tok a real recurring cost rather than a number in a spreadsheet.
3. A decision that the token budget must go below ~16k. Variant E is built, 186-green, byte-identical request bodies, diff ready.

### What would change the answer to "don't merge at all"

1. Confirmation that the portal's own agent loop defers or retrieves tools (its BM25 `ToolRetriever` already does) — in which case total surface barely matters and per-call payload (options 2–4) is the whole game.
2. An A/B showing the small self-hosted model picks `service` measurably worse than it picks a tool name. This is the one grounded anti-merge signal on record: memory notes that small models get *query construction* wrong while the plumbing is right, and the merge moves a decision from name space into argument space.

---

## 5. Contradictions resolved

| Claim | Disagreement | Resolution |
|---|---|---|
| Auto-`title` strip | -2,257 (record) vs -1,633 vs **-1,614** | **-1,614.** The -2,257 reproduces only when measuring at `indent=2` — a serialization mismatch against the 23,199 baseline. The -1,633 came from blind-popping `title`, which also deletes the schema of `ReportRequest`'s field literally *named* `title`. Trust the implementation that only strips a title it can prove was generated. |
| Full lossless stack | -2,175 vs **-2,180** | Both correct, different mixes (dedent+title+null vs title+null+additionalProperties+`$defs` inline). Agreement within 5 tok. Ship the -2,180 version — it has the guard test. |
| Dedent | -730 vs **-296** | **-296.** That number came from actually applying the transform; -730 came from normalizing text in a spreadsheet sense. Treat -730 as an upper bound requiring real re-wrapping. |
| Merge delta | -6,935 vs **-6,905** | Both real; 30-tok drift from cross-reference wording. Use ≈-6,900 (-29.8%). |
| "F + lossless ≈ full merge + trim" | Reported as indistinguishable (15,821 vs 15,755) | **Apples to oranges.** That compares F *with* the lossless ladder against E *without* it. Like for like: F+lossless 15,821 vs **E+lossless 14,213**. The full merge is genuinely 1,608 tok better. Corrected. |
| Merge's marginal value | 1,871 tok (8.1%) vs -6,935 (29.9%) | **Neither.** 1,871 measures against an unshippable ceiling (proven unshippable by variant B's +1,414). The honest figure is **-2,340 (partial) / -3,948 (full)** vs the best no-name-change stack. |
| "Instructions already covers this prose" | Asserted as the basis for the trim | **Only for the first 2048 chars.** Verified. The trim's premise is 15% true for this client. |
| `AttributeFilter` 7× redundancy | Unquantified until now | **2,166 tok (9.34%)**, recoverable only by tool-count reduction. The strongest measured pro-merge fact. |
| `rcsb_get_*` collapse | 4,133 tok (record) | **3,694 tok**, and confirmed a dead end regardless. |

---

## 6. Sequenced plan

### Now — free, no name changes, no eval needed

1. **Fix the `instructions` truncation.** Rewrite the first 2,048 characters to be self-contained and load-bearing: return types, the search-tool routing table, the paging/facet/grouping essentials. Treat everything after as bonus. The `rcsb_mcp_guide` loadable prompt is unaffected by the cap and is the right fallback — keep it. **This is a prerequisite for step 4.**
2. **Ship the lossless schema-compaction pass.** `-2,180 (-9.40%)`, `src/rcsb_mcp/schema_compact.py` + 8 lines in `server.py`, guard test asserts description multiset and constraint multiset are byte-identical before/after and 15,600 fuzzed instances agree. Diff at `/tmp/rcsb-mcp-schema-compact-2026-07-28.diff`. This alone beats the postponed builder/executor refactor's estimated 2,177 at a fraction of the risk.
3. **Move `rcsb_render_report`'s class-docstring second paragraphs into `#` comments.** They are maintainer-facing design rationale shipped to the model every turn — `Evidence` spends ~100 tok explaining a schema-boundary design choice. **-234 tok on that tool**, zero behaviour change. After the merge, `render_report` becomes the second-largest item on the surface (1,903 tok, 54% of its schema is prose).

### Next — per-call, matters most for the hosted portal

4. **`structured_output=False`.** -1,152 always-on and every response stops being serialized twice: a live 100-hit search goes 3,749 → 2,421 tok; `rcsb_get_entries` with 5 ids goes 3,407 → 1,415 (-58%). Update `tests/test_report_output.py:217`. **Verify first** that no client in your stack reads `structuredContent` instead of `content`.
5. **Return pre-serialized compact JSON** (a `str` passes through `_convert_to_content` untouched). Whitespace alone is 1,093 tok of that 100-hit search. With #4: **3,749 → 1,328, a 65% cut on the dominant per-call payload.**
6. **Drop `score` from hit lists and the `editor` echo** — another 876 tok per 100-hit call. `score` is constant 1.0 for every attribute search; hits already arrive sorted, so position encodes ranking. Needs a coordinated edit to 7 tool descriptions and `test_tool_descriptions.py`.

### Then — needs the eval instrument fixed first

7. **Rebuild `evals/tool_selection` (§7).** Nothing structural should ship before this. It is the only thing that turns the merge from an argument into a measurement.
8. **Variant C (trim) — only after step 1.** -2,854 standalone, but remember 79% of it evaporates if the merge follows. If you are going to merge, **skip C and go straight to F**; C is a down-payment, not an addition.
9. **Variant A → F (partial merge).** Ship with hidden aliases (§8) and the `rcsb-ai` `core_tools` config change in the same window.

### Hold

- **Variant E (full 7→1).** Built, green, diff ready. Ship only if §4's conditions are met.
- **`anyOf:[X,null]` flattening** (-860). Narrows the schema and destroys the merge's `None`-sentinel fail-fast validation. Keep the exported-but-unwired function and its "nobody wires this in by accident" test.
- **URL tool profiles** (`?profile=search`, 39→9 tools, -50%). Zero blast radius, per-client opt-in, no tool renamed. Best fit for the hosted portal if it turns out to load eagerly. Prototype has no auth, no profile registry, and does not filter `CallToolRequest`.

### Leave alone

- **Variant B (shared-options sub-model)** — the only variant that makes things *worse* (+1,414).
- **Advertised alias shims** — only -1,019 net (14.7% of the win), and removal day carries the identical blast radius, just later.
- **`tools/list` pagination** — unimplemented server-side in this SDK, and saves zero context anyway (a paginating client fetches all pages).
- **`listChanged` + dynamic registration** — blocked by `stateless_http=True` across 2–6 replicas with no session affinity.
- **Collapsing the `rcsb_get_*` family** — 3,694 tok, confirmed dead end.
- **`exclusiveMinimum`, `type: object`, `required` arrays** — already the cheapest encoding, all load-bearing.

---

## 7. Making a merge measurable — required changes to `evals/tool_selection`

**Today the suite cannot A/B this change at all.** 8 of 12 probes assert on a merged tool name; two of those cannot be mechanically rewritten. This is the blocker.

### `run_probes.py`

1. **Surface-agnostic tool tokens.** Add `_SERVICE_TOOL = {"attribute": "rcsb_search_by_attribute", ...}`, detect the surface with `merged = "rcsb_search" in {t["name"] for t in tools}` in `load_server`. A probe token `service:X` in `tool` / `tool-in` / `tool-not` resolves to `("rcsb_search", args["service"]==X)` on the merged arm and to `(_SERVICE_TOOL[X], True)` on the split arm. **This is the whole trick** — one resolver, `probes.xml` becomes surface-independent.
2. **`check()` must take the surface flag** — on the merged arm a `service:` token is a conjunction over tool AND args.
3. **`tool-not` must be a negated conjunction.** `tool-not="service:fulltext"` means `not (tool=="rcsb_search" and args.get("service")=="fulltext")`. Expanding it naively to `tool-not="rcsb_search"` fails 100% of merged runs and manufactures a catastrophic fake regression on the `empty-valid` probe. Current code (`run_probes.py:68-70`) is a flat name comparison.
4. **Arg-level negation** (`<arg name="X" absent="true"/>`) — required to express `empty-valid` at all, and the instrument for measuring param over-supply on a wide schema (`rmsd_cutoff`, `identity_cutoff`, `match_type` on prompts that never mention them).
5. **Conditional arg assertions.** The grader ANDs all children unconditionally, so the `strucmotif` probe's legitimate `rcsb_get_polymer_entity_instances` branch fails the moment you add `<arg name="service" .../>`.
6. **Argument alias map** `{"chemical_attributes": "chemical"}` applied on the split arm. Without it every chemical-attribute probe reads 0% on the OLD arm and the diff reports a fake *improvement*. (Not needed for the partial merge, which avoids the rename.)
7. **`<clean-args/>`** — import `_SERVICE_PARAMS`/`_PARAM_OWNERS` from the loaded `rcsb_mcp.search` and assert no supplied argument is owned by another service. Vacuously true on the split arm, so it stays A/B-valid, and it measures the merge's one genuinely new failure mode.
8. **A 7×7 service confusion matrix** in the `--out` JSON, printed by `--compare`. **This, not per-probe pass rate, is the instrument that answers the question** — it shows whether the enum confuses the *same* pairs the names confused, or new ones.
9. **2-turn mode.** The grader scores the first call only, so the merge's fail-fast error + successful retry is scored as a plain fail. The merge is currently scored strictly worse than it behaves.

### `probes.xml`

- **No seqmotif probe exists.** The structure / seqmotif / strucmotif triangle the merge is accused of endangering has one leg entirely unprobed. `README.md:204` has a ready-made prompt.
- **No chemical-attributes probe** — exactly where the full merge invents a new collision. Need one that must choose `service="attribute"` + `chemical_attributes=True` + `return_type="mol_definition"` and one that must not.
- Target ~24 probes: 3 per service (canonical / near-miss against its confusable sibling / discriminating-param-ambiguous) plus the 5 existing mechanic probes. `README.md:199-205` already contains 7 unexecuted prompt→tool mappings; promote them.

### Statistics

`--k 5` gives an SE up to 0.22 per probe; with ~24 probes and "any drop = REGRESSION", spurious flags are near-certain. **Use k≥20 and judge on the pooled per-service confusion matrix.** Run against the **target self-hosted model**, not only Haiku — Haiku showed 0 regressions for a 28% docstring trim and will show nothing either way. Do not bundle any other guide edit into the treatment arm.

### Guard-rail repairs the merge requires

- `tests/test_tool_descriptions.py` currently checks *presence* once all 21 phrases live in one blob; it was written to check **attachment**. Scope each phrase to its own SERVICES bullet, or strucmotif's label-vs-author-numbering warning can drift into the seqmotif paragraph and still pass green.
- `tests/test_search_validation.py`'s AST guard went from 8 tool names to 2. Re-point it at the `_SERVICE_PARAMS` keys, or an eighth service added tomorrow lands inside the `if/elif` chain where the guard is permanently blind.
- `tests/test_tool_descriptions.py` reads `t.description` only and never `inputSchema` — a latent hole discovered via variant B, worth closing regardless of which variant ships.

---

## 8. Irreversible / live-deployment items

`https://rcsb-mcp.west.k8s.rcsb.org/mcp` is live and `stateless_http=True` across 2–6 replicas with no session affinity.

| Item | Blast radius |
|---|---|
| **Removing tool names** (5 for partial, 7 for full) | Cached tool lists → "Unknown tool". Saved user prompts. Downstream agents calling by name. `server.json` contains no tool names, so the registry entry is safe. |
| **`rcsb-ai` portal breaks silently** | `core_tools` defaults to `"rcsb_search_fulltext,rcsb_search_by_attribute,rcsb_get_entries,rcsb_get_polymer_entities"` (`config.py:56`); `ToolRetriever` filters core to names that exist (`tools.py:79`). Under the **full** merge core silently shrinks 4→2 and — measured — the search tool drops out of the top-8 on 2 of 8 probe prompts. No error, no log. **One config line, must ship in lockstep.** The partial merge does not touch either name and is unaffected. |
| **`chemical` → `chemical_attributes` rename** (full merge only) | An unrelated API break riding along. Avoided entirely by the partial merge. |
| **`structured_output=False`** | Any client reading `structuredContent` rather than `content[0].text` breaks. Audit before shipping. |
| **Dropping `score`** | Documented return contract; appears in 7 descriptions. |

**Mitigation that actually works: hidden aliases, at 0 tok.** Register the old names in the tool manager but omit them from `tools/list`. Proven end-to-end on the installed SDK — `mcp/server/lowlevel/server.py:487-536` logs `Tool 'X' not listed, no validation will be performed` and dispatches anyway; `fastmcp/server.py:343-346` resolves `call_tool` purely through `self._tool_manager`. This gives the **full token win on day one** while every cached and hard-coded caller keeps working. Ship it with: a pinned `mcp` version, a test that invokes a hidden alias through `request_handlers`, and **logging on every hidden-alias call** so the removal date comes from measured usage rather than a guess.

**Stale references**: README.md (28 for the full merge), `probes.xml` (8), `run_probes.py` (1) — the prototypes leave all 37. Note also `resolvers.py:87,90` emit tool names **at runtime inside a response `note`** — a routing instruction injected mid-conversation, easy to miss during a rename, and one of them sits inside a double-quoted Python string where the mechanical rename produces a `SyntaxError`.

---

## 9. Open questions that would change the recommendation

1. **Does the portal load tools eagerly or lazily?** This session's client defers all 39 (resident cost ~1,519 tok, not 25,374). If the portal's own loop retrieves via BM25 — which it already does — the merge's total-surface win is largely notional and options 4–6 (per-call payload, -65% on a 100-hit search) are the whole game. One trivial prompt per client, read turn-1 input tokens.
2. **Does the target self-hosted model pick `service` as reliably as it picks a tool name?** Zero in-repo evidence exists either way; the only recorded routing weak spot (strucmotif vs structure on a small model) is a *name-space* failure, which cuts against the objection. Settled only by the rewritten A/B at k≥20 with a per-service confusion matrix.
3. **Do any clients read `structuredContent`?** Gates a -1,152 always-on and -35%-per-response win with a two-line change.
4. **Are the wire-payload response measurements what the client actually bills?** All per-call numbers here are wire payload — an upper bound. The `indent=2` waste in `content` is real regardless.
5. **Does the full merge's `service="chemical"` vs `chemical_attributes=True` collision confuse the model?** No probe exists, and the prototype's guide rewrite does not disambiguate it. If it does, the partial merge's advantage grows; if not, variant E becomes more attractive.
6. **Is losing 8 schema-enforced requiredness constraints and 17 visible defaults acceptable under constrained decoding?** The merged schema emits no `oneOf` / `dependentRequired`. `return_type` is the one field where a wrong value produces no error at all — it silently returns the wrong entity type, surfacing one tool call later. Its schema now shows `default: null` where it used to show `"polymer_entity"`, which reads as *unspecified*.
7. **What is the tolerable UX cost of a fail-fast round trip?** Token arithmetic says the error surface is free (break-even needs a 12–75% request-count inflation). A 2–5 s stall and a visible self-correction in a user-facing chat portal is not free, and nothing here measures it.
