# Evaluation suite

Two complementary suites:

- **`rcsb_pdb_eval.xml`** (below) — end-to-end *accuracy*: can an agent fully answer
  realistic PDB questions using these tools?
- **[`tool_selection/`](tool_selection/)** — a lightweight *first-tool-call* A/B harness
  for catching routing regressions when tool docstrings change (plus the deterministic
  [`tests/test_tool_descriptions.py`](../tests/test_tool_descriptions.py) that guards
  load-bearing phrases in CI). Reach for this after a docstring edit; reach for the
  accuracy suite to judge overall server quality.

[`rcsb_pdb_eval.xml`](rcsb_pdb_eval.xml) is a set of 14 read-only questions that
measure how well an LLM — given **only** this MCP server's tools and no other
context — can answer realistic Protein Data Bank questions. It follows the
`mcp-builder` skill's evaluation format (one `<qa_pair>` per question), and is
the real measure of server quality: not how many tools exist, but whether their
names, schemas, and docstrings let an agent route and chain them correctly.

Every question is **independent**, **read-only**, and has a **single, stable**
answer. Answers are anchored to deposited-structure metadata (sequences,
ligands, assemblies, citations, cross-references), which is immutable once a
structure is released — so they don't drift over time. No dynamic counts are
used. All 14 answers were verified against the live RCSB APIs on **2026-06-24**.

## What each question exercises

| # | Answer | Capability under test (expected tool path) |
|---|--------|--------------------------------------------|
| 1 | `P68871` | entry → entities → pick the *beta* subunit → UniProt mapping (`rcsb_get_entries` → `rcsb_get_polymer_entities` → `rcsb_seqcoord_alignments`/field discovery) |
| 2 | `KABFMIBPWCXCRK-RGGAHWMASA-L` | entry → identify the 4-copy heme ligand → chem-component InChIKey (`rcsb_get_entries` → `rcsb_get_nonpolymer_entities` → `rcsb_get_chem_comps`) |
| 3 | `4` | biological-assembly composition (`rcsb_get_entries` → `rcsb_get_assemblies`); must count polymer, not non-polymer, instances |
| 4 | `Physeter macrocephalus` | source-organism binomial of a polymer entity (`rcsb_get_polymer_entities`) |
| 5 | `STI` | entry → ligand discovery, disambiguating the inhibitor from the chloride ion (`rcsb_get_entries` → `rcsb_get_nonpolymer_entities`) |
| 6 | `NAD` | batch chem-component fetch + numeric comparison across four ligands (`rcsb_get_chem_comps`) |
| 7 | `10.1016/j.cell.2020.02.058` | primary-citation DOI of a cryo-EM entry (`rcsb_get_entries`) |
| 8 | `P00520` | NCBI/UniProt cross-reference via Sequence Coordinates — note the murine Abl accession, not the human one (`rcsb_seqcoord_alignments`) |
| 9 | `IPR000980` | free-text domain → InterPro id via the ontology resolver (`rcsb_find_interpro_domains`) |
| 10 | `MONDO:0009061` | free-text disease → MONDO id via the ontology resolver (`rcsb_find_disease_terms`) |
| 11 | `GO:0004096` | free-text molecular function → GO id via the ontology resolver (`rcsb_find_go_terms`) |
| 12 | `4.2.1.1` | free-text enzyme → EC number via the enzyme-classification resolver (`rcsb_find_enzyme_classes`) |
| 13 | `NP_000509` | polymer entity → NCBI RefSeq protein cross-reference via Sequence Coordinates (`rcsb_seqcoord_alignments`) |
| 14 | `40674` | free-text clade → NCBI Taxonomy id via the organism resolver, picking the class *Mammalia* over noisier top hits (`rcsb_find_organisms`) |

## Running it

> **Read [Known harness bugs](#known-harness-bugs) first.** As shipped, the harness does
> not fail loudly — it reports a **confidently wrong score**. Unpatched, this suite scored
> 8/14 while *every* tool call silently failed; with the two fixes applied it scores 14/14.
> And even patched, the reported number is a **lower bound**: grading is exact string match, so
> a correct answer phrased as a sentence scores ❌ (bug 3). Never read the raw score without
> checking the per-task answers.

The evaluation harness ships with the `mcp-builder` skill
(`scripts/evaluation.py` + `connections.py` + `requirements.txt`). It launches
Claude with this server's tools attached, lets it answer each question, and
scores the result. Copy those three files next to this README (or run from the
skill's `scripts/` directory), then:

```bash
# 1. Install this server + the harness deps, in the same environment
pip install -e .                 # from the repo root: provides the `rcsb-mcp` stdio entry point
pip install anthropic mcp        # harness deps (or: pip install -r requirements.txt)

# 2. Provide an Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Run the suite over stdio (the harness starts/stops the server itself)
python evaluation.py \
  -t stdio \
  -c rcsb-mcp \
  -m claude-sonnet-4-6 \
  -o report.md \
  rcsb_pdb_eval.xml
```

- `-c rcsb-mcp` is the stdio entry point created by `pip install -e .`. (Equivalent:
  `-c python -a rcsb_mcp.server` if you prefer invoking the module directly.)
- `-m` selects the judge/agent model — pass one your API key can access; the
  harness's built-in default is older than the example above.
- `-o report.md` writes a per-question report (pass/fail, tool calls, the agent's
  own feedback on the tools); omit it to print to stdout.

The report's accuracy and the agent's tool feedback are the signal: a question
that fails usually points at a tool description or schema that needs sharpening,
not just a wrong answer.

## Known harness bugs

Bugs 1-3 are in the `mcp-builder` harness (as of 2026-07-16, run with `claude-sonnet-5`)
and make the command above report a **confidently wrong** result instead of failing loudly.
None of the three is in this server. Patch your local copy before trusting a score — the
fixes are small — and ideally push them upstream to the skill rather than forking it here.
Bug 4 is different: it is in **our own** `tool_selection` runner, and it is fixable here.

All four share one failure mode worth internalising: *the suite prints a number no matter
what went wrong.* Never read a score without reading what produced it.

**1. Only the first tool call in a turn is answered** (`evaluation.py`, `agent_loop`).
It does `tool_use = next(block for block in response.content if block.type == "tool_use")`
and appends a single `tool_result`. Current models readily emit **parallel** tool calls, so
the remaining `tool_use` ids never get a result and the next request dies with
`400 ... tool_use ids were found without tool_result blocks`. *Fix:* iterate over **every**
`tool_use` block, execute each, and return all `tool_result`s in one user message.

**2. Tool results never reach the model** (`evaluation.py` + `connections.py`) — *this is the
dangerous one.* `call_tool` returns `result.content`, a **list of MCP `TextContent` objects**;
the harness then does
`json.dumps(tool_result) if isinstance(tool_result, (dict, list)) else str(tool_result)`.
The list branch raises `TypeError: Object of type TextContent is not JSON serializable`, which
the surrounding `except` swallows and feeds back to the model **as the tool's output**. Every
tool call appears to fail, the agent falls back on its own prior knowledge, and the suite still
prints a score. Unpatched it reported **8/14 while calling zero tools successfully** — the
answers were recited from memory, not retrieved. *Fix:* unwrap each content block's `.text`
before returning the result.

With both fixed, the suite runs clean: **14/14, zero serialization errors**. A useful tell that
you are hitting bug 2 rather than a real failure: the per-task feedback in the report will say
every tool call failed with an identical `TextContent` error.

**3. The reported accuracy is a LOWER bound — grading is exact string match.** Not a crash, but
it will mislead you the same way. `evaluation.py` scores with
`int(response_value == qa_pair["answer"])`: no judge, no normalization, no substring match. The
agent's answer must equal the ground truth *exactly*. A scientifically correct answer wrapped in
a sentence scores ❌. Observed on 2026-07-16 (`claude-sonnet-5`), Task 1 — ground truth `P68871`:

> *"The beta subunit corresponds to polymer entity 4HHB_2 ("Hemoglobin subunit beta"), which
> maps to UniProt accession **P68871** (HBB_HUMAN)."* → graded ❌

Reported 13/14; every one of the 14 answers actually contained its ground truth. The same
question passed on an earlier run of the same server, so this is **run-to-run variance in how
the agent phrases things**, not a behaviour change — the harness sets no temperature. Before
concluding a question regressed, check whether the answer merely *contains* the expected value:

```python
# in the report, compare "Ground Truth Answer" vs "Actual Answer" per task
expected in actual   # -> a formatting artifact, not a wrong answer
```

Consequences: don't read a 1-point drop as a regression without checking, and don't extend the
suite with answers that invite prose (keep them short, ID-shaped, single-valued).

Model ids are also stale: the harness default is `claude-3-7-sonnet-20250219`, and the `-m`
example above predates current models — always pass a current model explicitly.

**4. `tool_selection/run_probes.py` scores a transport error as a WRONG ANSWER — and the
error rate climbs with run position, so a sequential A/B penalises whichever side runs
second.** This one is ours, in this repo, not `mcp-builder`.

At [`run_probes.py`](tool_selection/run_probes.py) the rate is `passes / max(1, args.k)`: the
denominator is the *requested* sample count. A sample whose API call raises is appended to
`errors` and skipped with `continue`, so it never increments `passes` but still counts
against the rate — a dropped connection is arithmetically identical to the model picking the
wrong tool. `compare()` diffs those same `rate` values, so the A/B inherits the distortion.

That would be a tolerable constant tax if the errors were evenly spread. They are not.
Observed 2026-07-29 (`claude-haiku-4-5-20251001`, k=5 then k=8), every failure was the same
error — `[SSL: SSLV3_ALERT_BAD_RECORD_MAC]` — and its frequency rose with position in the
session:

```
run 1:   pos 1 = OLD   2 errors/60      pos 2 = NEW   12 errors/60
run 2:   pos 1 = NEW  13 errors/96      pos 2 = OLD   27 errors/96
```

So the *same* change measured `0.92 -> 0.78` with the baseline first, and `0.67 -> 0.80`
with the baseline second. Neither number was about the code under test. Pooled over only the
samples that reached the model: 119/127 (94%) vs 124/131 (95%), z = +0.33 — indistinguishable.
Read raw, the first run is a convincing 14-point regression that does not exist.

*Fix:* divide by the samples that actually reached the model, and surface the attrition —

```python
rate = passes / max(1, len(observed))          # not args.k
```

then print the error count beside the rate so a run with heavy attrition is visibly
untrustworthy. Better still, retry a couple of times on transport exceptions before
giving up on a sample.

Until that lands: **read `errors` in the `--out` JSON before believing any delta**, and run
the two sides in both orders — if the winner follows the running order rather than the
`--src`, you are looking at this bug and not at your change.

## Maintaining the suite

If you change default field selections, tool names, or routing guidance, re-run
the suite and re-verify any answer that moves. To re-confirm an answer by hand,
solve it directly against the live API, e.g.:

```python
import asyncio
from rcsb_mcp import server
print(asyncio.run(server.rcsb_get_chem_comps(["HEM", "ATP", "NAD", "STI"])))
```
