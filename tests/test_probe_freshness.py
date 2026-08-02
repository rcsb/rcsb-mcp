"""evals/tool_selection/probes.xml must name tools and arguments that actually exist.

This guards a failure that had already happened silently. After the seven flat rcsb_search_*
tools were replaced by the rcsb_query_* builders plus rcsb_search_request, every probe still
asserted on the removed names — so the suite would have failed all 15 probes IDENTICALLY in
both arms of an A/B and reported "no difference", which reads as "the change is safe". A
stale eval is worse than no eval, because it answers.

Nothing here needs a model or a key: it compares the probe file against the server's own
tool schemas. The suite itself still needs an endpoint, which is why this cheap check lives
in CI and the probes do not.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PROBES = Path(__file__).resolve().parents[1] / "evals" / "tool_selection" / "probes.xml"
RUNNER = Path(__file__).resolve().parents[1] / "evals" / "tool_selection" / "run_probes.py"


@pytest.fixture(scope="module")
def tools():
    """{tool_name: set(parameter names)} as the server actually publishes them."""
    import asyncio

    from rcsb_mcp.server import mcp

    listed = asyncio.run(mcp.list_tools())
    return {t.name: set((t.inputSchema.get("properties") or {})) for t in listed}


@pytest.fixture(scope="module")
def probes():
    return ET.parse(PROBES).getroot().findall("probe")


def _expected_tools(expect):
    names = []
    for key in ("tool", "tool-in", "tool-not"):
        if expect.get(key):
            names += [x.strip() for x in expect.get(key).split(",")]
    return names


def test_probes_file_parses(probes):
    """XML comments cannot contain a `--` run; a hyphen underline silently breaks the file."""
    assert probes, "no probes parsed"


def test_every_expected_tool_exists(probes, tools):
    missing = {
        p.get("id"): [t for t in _expected_tools(p.find("expect")) if t not in tools]
        for p in probes
    }
    missing = {k: v for k, v in missing.items() if v}
    assert not missing, f"probes assert on tools the server no longer exposes: {missing}"


def test_every_asserted_arg_exists_on_that_tool(probes, tools):
    """An <arg> naming a parameter the tool does not have can never pass.

    Only checkable when the probe pins a single tool — `tool-in` leaves the target
    ambiguous, and an args-only probe deliberately does not care which tool was called.
    """
    bad = {}
    for p in probes:
        expect = p.find("expect")
        target = expect.get("tool")
        if not target or target not in tools:
            continue
        unknown = [el.get("name") for el in expect
                   if el.tag == "arg" and el.get("name") not in tools[target]]
        if unknown:
            bad[p.get("id")] = (target, unknown)
    assert not bad, f"probes assert on parameters that do not exist: {bad}"


def test_model_visible_text_names_no_removed_tool(probes, tools):
    """The prompts and seeded turns are the only probe text the MODEL sees.

    The old runner's seed said "I searched with rcsb_search_by_attribute" — a tool that no
    longer exists — which both misleads the model and dates the suite. XML comments and the
    runner's own docstrings are exempt on purpose: they legitimately discuss removed tools
    when explaining why something changed, and a guard that forbade that would just push the
    history out of the file.

    Attribute paths (`rcsb_entry_info.resolution_combined`) are excluded by the negative
    lookahead, and `rcsb_query_*`-style globs by the trailing-underscore check.
    """
    visible = []
    for p in probes:
        visible.append(p.findtext("prompt") or "")
        visible += [t.text or "" for t in p.findall("turn")]
    strays = sorted({
        token for text in visible
        for token in re.findall(r"\brcsb_[a-z0-9_]+\b(?!\.)", text)
        if token not in tools and not token.endswith("_")
    })
    assert not strays, (
        f"probe text shown to the model names tools that are not registered: {strays}. "
        f"Leaving these stale makes an A/B report 'no difference' from a dead harness."
    )


def test_executor_probes_seed_the_builder_step(probes, tools):
    """A probe asserting on an rcsb_search_request-only argument must seed prior turns.

    Only the model's FIRST tool call is graded, and in a real search that call is always an
    rcsb_query_* builder — so return_type / group_by / sort_by / all_hits are unreachable
    unless the probe seeds the builder step as already done. Without a seed the probe cannot
    pass however good the model is, and would read as a docstring regression.
    """
    executor_only = tools["rcsb_search_request"] - set().union(
        *(v for k, v in tools.items() if k.startswith("rcsb_query_"))
    )
    for p in probes:
        asserted = {el.get("name") for el in p.find("expect") if el.tag == "arg"}
        if asserted & executor_only:
            roles = [t.get("role") for t in p.findall("turn")]
            assert "assistant" in roles, (
                f"probe {p.get('id')} asserts on {sorted(asserted & executor_only)}, which only "
                f"rcsb_search_request accepts, but seeds no prior assistant turn — it can never pass"
            )


def test_the_paired_intersection_probes_stay_paired():
    """`same-molecule` and `entry-is-fine` are only meaningful together.

    They seed the IDENTICAL query document and differ solely in what the user asked for, so
    one measures whether the return_type guidance lands and the other whether it over-fires.
    Keeping only the first would reward a change that pushes every query to polymer_entity.
    """
    by_id = {p.get("id"): p for p in ET.parse(PROBES).getroot().findall("probe")}
    assert {"same-molecule", "entry-is-fine"} <= set(by_id), "the control probe was dropped"
    seeds = {
        pid: [t.text for t in by_id[pid].findall("turn") if t.get("role") == "assistant"]
        for pid in ("same-molecule", "entry-is-fine")
    }
    assert seeds["same-molecule"] == seeds["entry-is-fine"], (
        "the pair must seed the same query document, or they measure two different things"
    )


def test_seeded_tool_call_arguments_are_json_objects(probes):
    """A tool call's `arguments` must map PARAMETER NAMES to values, not be a bare value.

    The seeds originally carried `[{"attribute": ...}, ...]` — the raw value of the
    `attributes` parameter with no key around it. api-gpt-oss-120b tolerated it, so every
    A/B run looked healthy; api-gemma-4-31b rejected it with the actual diagnosis
    ("tool_calls[].function.arguments must be a JSON object (mapping)") and glm/deepseek
    failed downstream with "'list' object has no attribute 'items'".

    A malformed seed is worse than a broken one when one lenient model hides it.
    """
    import json

    for probe in probes:
        for turn in probe.findall("turn"):
            if not turn.get("tool"):
                continue
            parsed = json.loads(turn.get("args") or "{}")
            assert isinstance(parsed, dict), (
                f"{probe.get('id')}: seeded args must be a JSON object, "
                f"got {type(parsed).__name__}"
            )


def test_seeded_tool_call_arguments_match_the_real_tool_schema(probes, tools):
    """Every key in a seed must be a real parameter of the tool it claims to call."""
    import json

    for probe in probes:
        for turn in probe.findall("turn"):
            tool = turn.get("tool")
            if not tool:
                continue
            assert tool in tools, f"{probe.get('id')} seeds unknown tool {tool}"
            unknown = set(json.loads(turn.get("args") or "{}")) - tools[tool]
            assert not unknown, f"{probe.get('id')}: {tool} has no parameter(s) {sorted(unknown)}"
