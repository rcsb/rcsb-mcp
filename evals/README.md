# Evaluation suite

[`rcsb_pdb_eval.xml`](rcsb_pdb_eval.xml) is a set of 13 read-only questions that
measure how well an LLM — given **only** this MCP server's tools and no other
context — can answer realistic Protein Data Bank questions. It follows the
`mcp-builder` skill's evaluation format (one `<qa_pair>` per question), and is
the real measure of server quality: not how many tools exist, but whether their
names, schemas, and docstrings let an agent route and chain them correctly.

Every question is **independent**, **read-only**, and has a **single, stable**
answer. Answers are anchored to deposited-structure metadata (sequences,
ligands, assemblies, citations, cross-references), which is immutable once a
structure is released — so they don't drift over time. No dynamic counts are
used. All 13 answers were verified against the live RCSB APIs on **2026-06-24**.

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

## Running it

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

## Maintaining the suite

If you change default field selections, tool names, or routing guidance, re-run
the suite and re-verify any answer that moves. To re-confirm an answer by hand,
solve it directly against the live API, e.g.:

```python
import asyncio
from rcsb_mcp import server
print(asyncio.run(server.rcsb_get_chem_comps(["HEM", "ATP", "NAD", "STI"])))
```
