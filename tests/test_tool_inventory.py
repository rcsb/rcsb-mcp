"""The complete, exact set of MCP tools the server registers.

A frozen inventory. Its job is to make a *disappearance* loud: the biggest risk
in moving tool definitions between modules (the server.py -> packages refactor) is
a tool silently failing to register because its module was never imported or its
`register_*` was never called. `list_tools()` would just come back one short, and
nothing else in the suite asserts the full roster.

So: if you ADD a tool, add its name here (deliberate). If a move DROPS one, this
fails immediately, naming exactly which. It intentionally does not check
descriptions/schemas — test_tool_descriptions.py owns that.
"""

import asyncio

from rcsb_mcp import server

EXPECTED_TOOLS = {
    # search (RCSB Search API) — layered: build a query, optionally compose, then run it
    "rcsb_query_fulltext",
    "rcsb_query_attribute",
    "rcsb_query_sequence",
    "rcsb_query_seqmotif",
    "rcsb_query_structure",
    "rcsb_query_strucmotif",
    "rcsb_query_chemical",
    "rcsb_query_composer",
    "rcsb_search_request",
    # data (RCSB Data API — reads)
    "rcsb_get_entries",
    "rcsb_get_polymer_entities",
    "rcsb_get_branched_entities",
    "rcsb_get_nonpolymer_entities",
    "rcsb_get_polymer_entity_instances",
    "rcsb_get_branched_entity_instances",
    "rcsb_get_nonpolymer_entity_instances",
    "rcsb_get_assemblies",
    "rcsb_get_interfaces",
    "rcsb_get_chem_comps",
    "rcsb_get_pubmed",
    "rcsb_get_uniprot",
    "rcsb_get_entry_groups",
    "rcsb_get_polymer_entity_groups",
    "rcsb_get_nonpolymer_entity_groups",
    "rcsb_get_group_provenance",
    # data — schema introspection
    "rcsb_list_pdb_search_attributes",
    "rcsb_describe_data_object",
    # resolvers (external EBI/ontology services)
    "rcsb_find_go_terms",
    "rcsb_find_interpro_domains",
    "rcsb_find_enzyme_classes",
    "rcsb_find_disease_terms",
    "rcsb_find_organisms",
    # sequence-coordinates (RCSB 1D-Coordinates API)
    "rcsb_seqcoord_alignments",
    "rcsb_seqcoord_annotations",
    "rcsb_seqcoord_group_alignments",
    "rcsb_seqcoord_group_annotations",
    "rcsb_describe_seqcoord_object",
    # report
    "rcsb_render_report",
}


def test_registered_tools_are_exactly_the_expected_set():
    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    missing = EXPECTED_TOOLS - registered
    unexpected = registered - EXPECTED_TOOLS
    assert not missing, f"tools expected but NOT registered (a move dropped them?): {sorted(missing)}"
    assert not unexpected, f"tools registered but not in the inventory (add them here): {sorted(unexpected)}"


def test_inventory_count_is_stable():
    """A blunt second signal: the count itself, so a swap (drop one, add one) still trips."""
    assert len(EXPECTED_TOOLS) == 38
    assert len(asyncio.run(server.mcp.list_tools())) == 38


# --- the markdown docs cite tool names too, and nothing used to check them ----------
#
# README.md and AGENTS.md both drifted badly across the builder/executor refactor: they
# documented seven `rcsb_search_by_*` tools that had been replaced by `rcsb_query_*` +
# `rcsb_search_request`, a `group_by_identity` parameter that had become `group_by`, a
# `pdb_assistant` prompt renamed to `rcsb_search_assistant`, and a server `instructions`
# block that no longer exists. None of it failed anything; it was found by a human reading
# the README months later.
#
# This is the cheap half of that problem — a name that no longer exists is mechanically
# detectable, so it should never again be found by eye.

# Backticked `rcsb_...` tokens that are deliberately NOT tools. Keep this short: each entry
# is a promise that the name is discussed on purpose.
ALLOWED_NON_TOOLS = {
    "rcsb_search_assistant",  # the served MCP prompt
    "rcsb_mcp_guide",         # the retired prompt, named where the docs explain the retirement
}

DOCS = ("README.md", "AGENTS.md")


def _cited_names(text: str) -> set[str]:
    """Backticked rcsb_* tokens that look like a TOOL name.

    Dotted tokens are attribute or module paths (`rcsb_entity_source_organism.ncbi_...`,
    `rcsb_mcp.server`), not tools, so they are excluded by the absence of a dot rather than
    by an allowlist — there are hundreds of them and they change constantly.
    """
    import re
    return {m for m in re.findall(r"`(rcsb_[a-z0-9_]+)`", text) if "." not in m}


def test_the_markdown_docs_only_cite_tools_that_exist():
    import pathlib

    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    root = pathlib.Path(__file__).resolve().parents[1]
    stale = {}
    for name in DOCS:
        cited = _cited_names((root / name).read_text())
        bad = sorted(cited - registered - ALLOWED_NON_TOOLS)
        if bad:
            stale[name] = bad
    assert not stale, (
        "these docs name tools that are not registered — renamed, removed, or a typo:\n  "
        + "\n  ".join(f"{f}: {', '.join(n)}" for f, n in stale.items())
    )


def test_every_tool_is_documented_in_the_readme():
    """The reverse: a tool nobody can find is nearly as bad as one that doesn't exist.

    README.md is the user-facing inventory, so every registered tool has to appear in it.
    AGENTS.md is deliberately exempt — it describes modules and conventions, not a roster.
    """
    import pathlib

    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text()
    cited = _cited_names(readme)
    missing = sorted(EXPECTED_TOOLS - cited)
    assert not missing, f"registered but absent from README.md: {missing}"
