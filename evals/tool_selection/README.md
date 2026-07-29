# Tool-selection probes (A/B)

A lightweight, **A/B** check for *which tool the model picks and how it fills the key
arguments*, given only this server's tool schemas + the `instructions=` block.

It complements the end-to-end accuracy suite in [`../rcsb_pdb_eval.xml`](../rcsb_pdb_eval.xml),
and the two are **disjoint by design**. That suite grades final *answers*, so its answers must
be stable — which is why it is anchored to immutable deposited metadata and uses **no dynamic
counts**. Search results drift as the PDB grows, so a stable-answer suite can never cover the
`rcsb_search_*` tools; a verified run of it calls **zero** search tools. Grading the *decision*
instead of the answer is the only practical way to cover search routing — that's this suite.

- **[`probes.xml`](probes.xml)** — the probes: a natural-language prompt plus an `<expect>`
  assertion over the model's FIRST tool call. This is the durable content; it targets the
  gotchas most at risk when docstrings are shortened (ontology routing, `group_by` needs
  `return_type="polymer_entity"`, `sort_by` sortability, the "empty result is valid" rule,
  strucmotif-vs-structure routing, …). The `<expect>` vocabulary is documented in the file.
- **[`run_probes.py`](run_probes.py)** — the runner: loads tools + instructions from any
  `--src` checkout, asks a model to act on each prompt, grades the first tool call against
  `<expect>`, `--k` samples per probe. Backends: `anthropic` (needs `ANTHROPIC_API_KEY`) or
  `openai` (any OpenAI-compatible endpoint, e.g. a local vLLM — usually no key). It also does
  the A/B diff via `--compare`. The RCSB API is never called; only the tool *decision* is graded.

## Running an A/B (before vs. after a change)

```bash
# from repo root; OLD = the committed state, NEW = your working tree
git worktree add /tmp/rcsb-old HEAD

python evals/tool_selection/run_probes.py --backend anthropic --model claude-haiku-4-5-20251001 \
    --k 5 --src /tmp/rcsb-old/src --out /tmp/old.json
python evals/tool_selection/run_probes.py --backend anthropic --model claude-haiku-4-5-20251001 \
    --k 5 --src src              --out /tmp/new.json
python evals/tool_selection/run_probes.py --compare /tmp/old.json /tmp/new.json

git worktree remove /tmp/rcsb-old
```

Point `--backend openai --base-url http://<host>:<port> --model <id>` at your target
(e.g. self-hosted) model — that's the run that matters for deployment, since small models are
the most sensitive to guidance thinned out of a docstring. Use `--only <id>,<id>` to re-run
just a probe or two while iterating.

## How to read it

> **First:** a transport error is scored as a wrong answer, and errors cluster in whichever
> side runs SECOND — so a sequential A/B can invent a regression that isn't there. See
> [bug 4](../README.md#known-harness-bugs) before believing any delta, and check `errors` in
> the `--out` JSON.

- It's a **regression** check: look for a probe whose rate DROPS old→new. A probe already
  <100% on both sides is a pre-existing model/assertion limitation, not caused by the change.
- Pick **Haiku** (or your target small model) — strong models are too forgiving to surface a
  subtle over-trim.
- Interpret **rates over K samples**, not single runs: tool selection is stochastic, so small
  single-sample flips (3/5↔4/5) are noise. Bump `--k` before believing a delta.
- It grades the **first tool call only**. That makes multi-step tasks unscorable here — if a
  prompt legitimately requires a resolver or a lookup *first*, the probe must either
  pre-supply that input or accept the prerequisite call (see the `strucmotif` probe). Genuine
  multi-step behaviour belongs in `../rcsb_pdb_eval.xml`.
- Each run records the **actual tool + args** chosen per sample in the `--out` JSON. Read it
  before concluding anything: a 0% can mean "the model did the right thing and the first-call
  grader can't credit it", not "the docs are wrong".
- Grow `probes.xml` as you dedup: every load-bearing "keep" line you preserve should get a
  probe asserting the behaviour it protects.

## The cheap deterministic gate

This suite needs a model + a key/endpoint, so it's a *deliberate* check, not a CI gate.
The CI gate is [`../../tests/test_tool_descriptions.py`](../../tests/test_tool_descriptions.py):
a free, deterministic `pytest` that asserts the load-bearing phrases still exist in each tool
description (or in the instructions block). Run that on every change; run these probes at
milestones.
