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
    # search (RCSB Search API)
    "rcsb_search_fulltext",
    "rcsb_search_by_attribute",
    "rcsb_search_advanced",
    "rcsb_search_by_sequence",
    "rcsb_search_by_seqmotif",
    "rcsb_search_by_structure",
    "rcsb_search_strucmotif",
    "rcsb_search_by_chemical",
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
    "rcsb_data_graphql",
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
    "rcsb_seqcoord_graphql",
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
    assert len(EXPECTED_TOOLS) == 39
    assert len(asyncio.run(server.mcp.list_tools())) == 39
