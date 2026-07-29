"""Guard: agent-facing text must not describe how the report is *presented*.

Colour is a presentation concern owned entirely by the render/template layer
(report/render.py + report/templates/report.html.j2). The agent decides only what
goes in each field — `grounds` is the tool value, `interpretation` is its own reading;
whether those render in one colour or another is not its business and not stable enough
to name. When the instructions said "rendered in the assistant colour" / "provenance
colouring", they re-coupled the agent to the CSS and would rot the moment the styling
changed.

So the whole agent-facing surface — the prompt, the server instructions block, every
tool description, and every tool inputSchema (which carries the nested field
descriptions like Evidence.grounds / Evidence.interpretation) — must contain no colour
vocabulary. The distinction those fields draw is semantic; its rendering is not
described here. If a report ever genuinely needs to explain its own colour key, that
belongs in the template, next to the CSS.

No network, no API key, no model.
"""

import asyncio
import json

from rcsb_mcp import server

# Substring match (not word-boundary): this must also catch "coloured", "colouring",
# "colors", "colorful", etc. Both spellings, since the codebase uses British English.
FORBIDDEN = ("color", "colour")


def _agent_facing_texts() -> dict[str, str]:
    """Every block of text the model actually reads: prompt, instructions, and — for each
    registered tool — its description plus its full serialized inputSchema (nested field
    descriptions included)."""
    tools = asyncio.run(server.mcp.list_tools())
    # The guide is scanned via its PROMPT, not via `server.mcp.instructions` — the server no
    # longer ships that block, and reading it here would silently degrade to "" and stop
    # covering the guide at all while the test kept passing.
    texts = {
        "prompt:rcsb_search_assistant": server.rcsb_search_assistant() or "",
        "prompt:rcsb_mcp_guide": server.rcsb_mcp_guide() or "",
    }
    for t in tools:
        texts[f"{t.name}.description"] = t.description or ""
        texts[f"{t.name}.inputSchema"] = json.dumps(t.inputSchema, ensure_ascii=False)
    return texts


def test_no_colour_vocabulary_in_any_agent_facing_text():
    offenders = []
    for where, text in _agent_facing_texts().items():
        low = text.lower()
        for word in FORBIDDEN:
            if word in low:
                offenders.append(f"{where}: contains {word!r}")
    assert not offenders, (
        "agent-facing text names a presentation detail (colour). Colour is owned by "
        "report/render.py + the Jinja template; the agent chooses field CONTENT, not how "
        "it is rendered. Describe the semantic distinction (tool value vs your own reading) "
        "instead:\n  " + "\n  ".join(offenders)
    )
