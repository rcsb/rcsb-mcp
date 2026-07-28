"""Deterministic guard for load-bearing content in the rcsb_search_assistant prompt.

The prompt is the agent's only instruction on what to put in a report and how to
deliver it, and it has no other coverage: the tool-selection eval
(``evals/tool_selection/``) loads the ``instructions=`` block and tool schemas, NOT
this prompt, so nothing else notices if a rule is trimmed away.

These assertions lock in the rules the JSON schema cannot encode — what to do with
an id the report can't show, how to deliver the link, and the provenance flag — plus
one negative invariant: the prompt must contain no presentation vocabulary, because
how results are displayed is owned entirely by the server.

No network, no API key, no model. The behavioral check lives in evals/.
"""

import re

from rcsb_mcp import server


def _norm(s: str) -> str:
    """Collapse whitespace so line-wrapping never hides a phrase."""
    return re.sub(r"\s+", " ", s or "")


def _prompt() -> str:
    """The prompt as the MCP client actually receives it (via the registered resource)."""
    return _norm(server.rcsb_search_assistant())


# Rules that are not derivable from the tool schema, so only the prompt carries them.
# Each entry is (substring, why it is load-bearing).
REQUIRED = [
    # --- what the agent supplies -------------------------------------------
    ("`result_type`", "the agent must know the field exists; nothing else tells it"),
    ('"entry"', "which value means PDB entry ids"),
    ('"ligand"', "which value means chemical component ids"),
    ("`evidence`", "the agent's one creative output"),
    # --- ids the report cannot show ----------------------------------------
    # Only entry + ligand ids resolve. Entity/assembly ids come back empty, and the
    # schema cannot express "map this up to its parent" — so the prompt must.
    ("4HHB_1", "the entity-id shape the agent must NOT report"),
    ("parent entry", "what to do instead: report the parent"),
    # --- delivery ----------------------------------------------------------
    ("Never write HTML yourself", "the agent must not hand-build the page"),
    ("clickable link", "the url IS the deliverable"),
    ("`.html`", "the html fallback is written to a file — client-agnostic, no tool named"),
    # --- provenance --------------------------------------------------------
    # Provenance is now a schema split, not a per-fragment flag: the agent's own reading
    # goes in evidence.interpretation, the tool value in grounds. Both names must survive.
    ("`grounds`", "the tool-sourced half of evidence — provenance colouring keys off the split"),
    ("`interpretation`", "the agent's-own-reading half; folding it into grounds is the bug this prevents"),
    # --- search quality: the agent's actual job ----------------------------
    ("FAMILY / ONTOLOGY ANCHOR", "rare-term recall strategy"),
    ("false positives", "full-text hits must be verified"),
    ("don't rank structures by it", "search score is not biological importance"),
]

# The server owns presentation entirely: it picks the columns, their order, labels and
# every derivable value. Naming any of that in the prompt re-couples the agent to the
# rendering — and, historically, silently drifted out of sync with the code (a ligand
# report once rendered four empty columns because the prompt described a layout the
# renderer refused to fill). Guarded as an absence so a future edit is a deliberate one.
FORBIDDEN_VOCABULARY = ["table", "column", "row"]

# Claims that were true once and silently rotted when a feature was removed. Each is a
# substring an adversarial review caught surviving a refactor; guarded so the same class
# of stale promise can't creep back. (case-insensitive)
FORBIDDEN_STALE = [
    ("advanced search link", "the collection/search link was removed (commit 235dcf4); the page has none"),
    ("into the html", "the agent never inserts into HTML — the server autoescapes; telling it to would double-escape"),
    ("present_files", "a Claude.ai-only, undocumented tool; the prompt must not name any client's file tool"),
]


def test_load_bearing_rules_are_present():
    text = _prompt()
    missing = [(s, why) for s, why in REQUIRED if s not in text]
    assert not missing, "rcsb_search_assistant.md lost load-bearing rules:\n" + "\n".join(
        f"  - {s!r}  ({why})" for s, why in missing
    )


def test_prompt_contains_no_presentation_vocabulary():
    """How results are displayed is the server's business, not the agent's."""
    text = _prompt().lower()
    found = [w for w in FORBIDDEN_VOCABULARY if re.search(rf"\b{w}s?\b", text)]
    assert not found, (
        f"rcsb_search_assistant.md mentions presentation vocabulary {found}. The agent supplies "
        "identifiers and reasoning; the server owns how they are displayed. If a layout "
        "genuinely must be described, describe it in report/tables.py instead."
    )


def test_prompt_has_no_stale_claims():
    """Promises about features that no longer exist mislead the agent worse than silence."""
    text = _prompt().lower()
    found = [(s, why) for s, why in FORBIDDEN_STALE if s in text]
    assert not found, "rcsb_search_assistant.md makes stale claims:\n" + "\n".join(
        f"  - {s!r}  ({why})" for s, why in found
    )


def test_prompt_is_reachable_as_an_mcp_prompt():
    """It ships as package data behind a registered prompt — not an unused file."""
    assert "## Search Requirements" in server.rcsb_search_assistant()


def test_mcp_guide_prompt_is_the_instructions_verbatim():
    """The guide prompt must BE the `instructions` text, not a copy of it.

    27 of the 39 tool descriptions defer to "the server instructions" (~45 references).
    `instructions` is returned on `initialize`, but the spec leaves injecting it to the
    CLIENT and several do not — so those cross-references can point at text the agent
    never received. The prompt is the fallback channel, which only helps if it carries
    the SAME text; a copy would drift and the fallback would quietly go stale.
    """
    guide = server.rcsb_mcp_guide()
    assert guide == server.mcp.instructions, (
        "rcsb_mcp_guide drifted from the instructions block; both must read the same "
        "package-data file (prompts/rcsb_mcp_guide.md)."
    )
    assert guide.strip(), "the guide prompt is empty"


def test_assistant_prompt_carries_the_guide_verbatim():
    """The persona prompt must also deliver the tool-routing guide.

    Its own rules depend on it: "resolve the concept with the matching rcsb_find_*
    resolver ... and search that annotation" names no attribute path, because the paths
    live in the guide. Invoked alone against a client that drops `instructions`, that
    rule is unactionable and the ~45 "see the server instructions" cross-references in
    the tool descriptions dangle. Verbatim (not paraphrased) so there is one source.
    """
    assistant = _prompt()
    assert _norm(server.rcsb_mcp_guide()) in assistant, (
        "rcsb_search_assistant no longer contains the guide verbatim. It must join "
        "_MCP_GUIDE, not a copy or a summary of it."
    )


def test_guide_is_labelled_with_the_phrase_the_tools_cite():
    """~45 tool descriptions say "see the server instructions". The guide's own heading is
    the only thing that phrase resolves against — and, because the guide IS the
    `instructions` block, the label reaches that channel too. Nothing added at the
    composition seam could do that, so the heading has to live in the file.
    """
    assert server.rcsb_mcp_guide().lstrip().lower().startswith("## server instructions"), (
        "the guide must OPEN with a heading naming it 'Server Instructions'; without it "
        "the tool descriptions' cross-references point at unlabelled prose"
    )


def test_assistant_prompt_leads_with_the_guide():
    """Order is load-bearing, and so is the ABSENCE of a second persona.

    The guide already opens with the identity and capability summary, so the policy half
    starts at its first section. A persona preamble re-added to the .md file would sit
    after the guide's opening line and contradict it — two answers to "what am I".
    """
    assistant = _prompt()
    assert assistant.startswith("## Server Instructions"), (
        "the guide must LEAD the composed prompt"
    )
    assert "You are a structural biology assistant" not in assistant, (
        "the policy half re-grew a persona preamble; the guide's opening line is the "
        "single statement of identity"
    )
    assert assistant.index("## Search Requirements") > assistant.index(
        "Return types and fetching details"
    ), "the policy half must FOLLOW the guide, never be interleaved with it"


# Every phrase a tool description uses to point INTO the guide, with the header that
# phrase has to land on. Counts are the references in src/rcsb_mcp/*.py at the time of
# writing — 28 named pointers across 51 "server instructions" mentions. Renaming a header
# without updating its citations sends the agent looking for a section that isn't there,
# and nothing else would notice: the pointer is prose on one side and prose on the other.
GUIDE_ANCHORS = [
    ("Return types and fetching details", "Return types and fetching details", 7),
    ("faceting", "Faceting", 7),
    ("grouping", "grouping", 7),
    ("resolver", "resolvers", 6),
    ("assembly/multimer", "Assembly / multimer", 1),
]


def test_guide_headers_match_the_phrases_the_tools_cite():
    """Each "see the <X> note in the server instructions" must have an <X> header."""
    headers = [ln for ln in server.rcsb_mcp_guide().splitlines() if ln.startswith("#")]
    blob = _norm(" ".join(headers)).lower()
    missing = [
        f"{cited!r} (cited ~{n}x) has no header containing {expected!r}"
        for cited, expected, n in GUIDE_ANCHORS
        if expected.lower() not in blob
    ]
    assert not missing, (
        "a guide header no longer matches the phrase its citations use:\n  "
        + "\n  ".join(missing)
        + "\nHeaders present:\n  "
        + "\n  ".join(headers)
    )


def test_guide_headers_nest_under_the_top_heading():
    """One `##` naming the block, `###` for its sections — so the composed prompt's
    `## Search Requirements` reads as a sibling of the guide, not a subsection of it."""
    levels = [
        len(ln) - len(ln.lstrip("#"))
        for ln in server.rcsb_mcp_guide().splitlines()
        if ln.startswith("#")
    ]
    assert levels and levels[0] == 2, "the guide must open with a single `##` heading"
    assert all(lv == 3 for lv in levels[1:]), (
        f"guide sections must all be `###` under that heading; found levels {levels}"
    )


def test_both_prompts_are_registered_and_distinct():
    """Two prompts with different jobs: the persona, and the tool-routing guidance."""
    import asyncio

    names = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    assert {"rcsb_search_assistant", "rcsb_mcp_guide"} <= names, f"registered prompts: {names}"
    assert server.rcsb_search_assistant() != server.rcsb_mcp_guide()
