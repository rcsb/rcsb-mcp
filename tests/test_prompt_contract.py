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
    # The score caveat moved OUT of this prompt: it now lives on rcsb_query_fulltext,
    # rcsb_query_attribute and rcsb_search_request (group_by_ranking), i.e. on the
    # always-delivered channel, and is guarded by tests/test_tool_descriptions.py.
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


def test_the_prompt_is_optional_not_load_bearing():
    """No registered tool may depend on a prompt to be usable.

    A prompt is delivered only when the client asks for it, so a tool description that
    says "see the <name> prompt" is a promise the server cannot keep — the same failure
    as the `instructions` block that arrangement replaced (injected whole by some
    clients, truncated at 2048 chars by others, dropped entirely by others again).
    Guidance a tool NEEDS belongs on that tool's own description, which always arrives
    via tools/list.

    This is the invariant the removed guide-composition tests were circling: they pinned
    HOW the pointers resolved instead of whether pointing was safe at all.
    """
    import asyncio

    tools = asyncio.run(server.mcp.list_tools())
    offenders = [
        (t.name, m.group(0))
        for t in tools
        for m in [re.search(r"(?:see|in|load) the [\w.]+ prompt", t.description or "")]
        if m
    ]
    assert not offenders, "tool descriptions point at prompts that may never arrive:\n" + "\n".join(
        f"  - {name}: {phrase!r}" for name, phrase in offenders
    )


def test_no_text_cites_a_prompt_that_is_not_registered():
    """A named prompt must actually exist — the dangling-reference check, generalised."""
    import asyncio

    registered = {p.name for p in asyncio.run(server.mcp.list_prompts())}
    texts = {f"tool:{t.name}": t.description or "" for t in asyncio.run(server.mcp.list_tools())}
    texts["prompt:rcsb_search_assistant"] = server.rcsb_search_assistant()

    dangling = [
        (where, name)
        for where, text in texts.items()
        for name in re.findall(r"\b(rcsb_[a-z_]+) prompt\b", text)
        if name not in registered
    ]
    assert not dangling, "references to prompts that are not registered:\n" + "\n".join(
        f"  - {where} cites {name!r}" for where, name in dangling
    )


def test_the_unserved_guide_is_marked_as_such():
    """prompts/rcsb_mcp_guide.md is kept to rescue prose from, and is NOT served.

    Nothing loads it, so it cannot go stale in a way that reaches an agent — but a file
    sitting in prompts/ reads like a prompt. The header is what stops someone wiring it
    back in without reading why it was unwired.
    """
    from pathlib import Path

    from rcsb_mcp import server as _s

    path = Path(_s.__file__).resolve().parent / "prompts" / "rcsb_mcp_guide.md"
    assert path.exists(), "the file is kept deliberately; delete it only on purpose"
    assert path.read_text(encoding="utf-8").lstrip().startswith("<!--\nNO LONGER SERVED"), (
        "the kept guide must open with the NO LONGER SERVED header explaining where its "
        "content went and what was not relocated"
    )
