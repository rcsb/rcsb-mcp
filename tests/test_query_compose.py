"""The composer layer: node joining, and the two things derived from a query tree.

`rcsb_search_request` sees only a query node, so it must DERIVE what the flat builders
each knew about themselves: which scoring strategy applies, and what return_type to use
when the caller named none. Both are silent when wrong -- a mis-derived return_type
returns the wrong KIND of identifier and the search still succeeds -- so they are pinned
here rather than left to the baseline fixture, which only covers shapes the old builders
could already express.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import queries  # noqa: E402

RESOLUTION = {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0}
METHOD = {"attribute": "exptl.method", "operator": "exact_match", "value": "X-RAY DIFFRACTION"}
SEQ = "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"


# --------------------------------------------------------------------------- #
# group_node: collapsing and splicing
# --------------------------------------------------------------------------- #
def test_a_single_node_needs_no_group():
    node = queries.fulltext_node("hemoglobin")
    assert queries.group_node([node], "and") == node


def test_same_operator_children_are_spliced_not_nested():
    """AND/OR are associative, so a same-operator child flattens into its parent."""
    inner = queries.attribute_node([RESOLUTION, METHOD], "and")
    composed = queries.group_node([queries.fulltext_node("kinase"), inner], "and")
    assert composed["type"] == "group"
    assert [n["service"] for n in composed["nodes"]] == ["full_text", "text", "text"]


def test_opposite_operator_children_stay_nested():
    """The nesting the composer exists for must survive: (A or B) and C."""
    either = queries.attribute_node([RESOLUTION, METHOD], "or")
    composed = queries.group_node([either, queries.fulltext_node("kinase")], "and")
    assert composed["logical_operator"] == "and"
    assert composed["nodes"][0]["logical_operator"] == "or"
    assert len(composed["nodes"][0]["nodes"]) == 2


def test_repeated_composition_does_not_build_a_tower():
    """An iteratively-called composer must not grow depth for same-operator joins."""
    node = queries.fulltext_node("a")
    for _ in range(20):
        node = queries.group_node([node, queries.fulltext_node("b")], "and")
    assert node["logical_operator"] == "and"
    assert all(n["type"] == "terminal" for n in node["nodes"]), "should stay one level deep"
    assert len(node["nodes"]) == 21


def test_alternating_operators_do_nest():
    node = queries.fulltext_node("a")
    for i in range(4):
        node = queries.group_node([node, queries.fulltext_node("b")], "or" if i % 2 else "and")
    depth = 0
    cur = node
    while cur.get("type") == "group":
        depth += 1
        cur = cur["nodes"][0]
    assert depth == 4


@pytest.mark.parametrize("bad_op", ["xor", "AND", "", None])
def test_group_node_rejects_a_bad_operator(bad_op):
    with pytest.raises(ValueError, match="logical_operator"):
        queries.group_node([queries.fulltext_node("a"), queries.fulltext_node("b")], bad_op)


def test_group_node_rejects_an_empty_list():
    with pytest.raises(ValueError, match="at least one query"):
        queries.group_node([], "and")


# --------------------------------------------------------------------------- #
# scoring_strategy_for
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "node, expected",
    [
        (queries.sequence_node(SEQ), "sequence"),
        (queries.chemical_node("C9H8O4", query_type="formula"), "chemical"),
        (queries.structure_node("4HHB", assembly_id="1"), "structure"),
        (queries.strucmotif_node("2MNR", [{"label_asym_id": "A", "label_seq_id": 162},
                                          {"label_asym_id": "A", "label_seq_id": 193}]),
         "strucmotif"),
        # seqmotif has never set one; the API default applies.
        (queries.seqmotif_node("CXCXXL", "simple"), None),
        (queries.fulltext_node("kinase"), None),
        (queries.attribute_node([RESOLUTION]), None),
    ],
    ids=["sequence", "chemical", "structure", "strucmotif", "seqmotif", "fulltext", "attribute"],
)
def test_scoring_strategy_is_derived_from_the_service(node, expected):
    assert queries.scoring_strategy_for(node) == expected


def test_attribute_refinement_does_not_change_the_strategy():
    """Refining a sequence search with attributes leaves it a sequence search."""
    node = queries.group_node(
        [queries.sequence_node(SEQ), queries.attribute_node([RESOLUTION])], "and")
    assert queries.scoring_strategy_for(node) == "sequence"


def test_a_mixed_service_query_falls_back_to_the_api_default():
    """Two services have no single right ranking, so neither one is imposed."""
    node = queries.group_node(
        [queries.sequence_node(SEQ), queries.structure_node("4HHB", assembly_id="1")], "and")
    assert queries.scoring_strategy_for(node) is None


# --------------------------------------------------------------------------- #
# default_return_type_for
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "node, expected",
    [
        (queries.fulltext_node("kinase"), "entry"),
        (queries.attribute_node([RESOLUTION]), "entry"),
        (queries.sequence_node(SEQ), "polymer_entity"),
        (queries.seqmotif_node("CXCXXL", "simple"), "polymer_entity"),
        (queries.chemical_node("C9H8O4", query_type="formula"), "mol_definition"),
        (queries.strucmotif_node("2MNR", [{"label_asym_id": "A", "label_seq_id": 162},
                                          {"label_asym_id": "A", "label_seq_id": 193}]),
         "assembly"),
        # The structure service depends on the reference, not the service name.
        (queries.structure_node("4HHB", assembly_id="1"), "assembly"),
        (queries.structure_node("4HHB", asym_id="A"), "polymer_instance"),
    ],
    ids=["fulltext", "attribute", "sequence", "seqmotif", "chemical", "strucmotif",
         "structure-assembly", "structure-chain"],
)
def test_default_return_type_matches_what_each_flat_tool_used(node, expected):
    assert queries.default_return_type_for(node) == expected


def test_a_mixed_service_query_defaults_to_entry():
    """entry is the one type every service can return."""
    node = queries.group_node(
        [queries.sequence_node(SEQ), queries.chemical_node("C9H8O4", query_type="formula")], "and")
    assert queries.default_return_type_for(node) == "entry"


def test_an_explicit_return_type_always_wins():
    body = queries.build_search_request(queries.sequence_node(SEQ), return_type="entry")
    assert body["return_type"] == "entry"


def test_structure_chain_reference_is_not_flattened_into_assembly():
    """The silent-wrongness case: a chain reference must not return assemblies."""
    body = queries.build_search_request(queries.structure_node("4HHB", asym_id="A"))
    assert body["return_type"] == "polymer_instance"


# --------------------------------------------------------------------------- #
# include_computed_models: honoured by every service
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "node",
    [
        queries.fulltext_node("kinase"),
        queries.attribute_node([RESOLUTION]),
        queries.sequence_node(SEQ),
        queries.seqmotif_node("CXCXXL", "simple"),
        queries.chemical_node("C9H8O4", query_type="formula"),
        queries.structure_node("4HHB", assembly_id="1"),
    ],
    ids=["fulltext", "attribute", "sequence", "seqmotif", "chemical", "structure"],
)
def test_include_computed_models_reaches_every_service(node):
    """Regression: five of the flat builders hardcoded this off while advertising it.

    `_request_options` takes include_computed as its THIRD POSITIONAL argument, and the
    specialist builders each passed a literal False there -- so computed structure models
    were silently excluded from every sequence, chemical, structure, seqmotif and
    strucmotif search that asked for them. Routing every builder through
    build_search_request is what fixed it; this keeps it fixed.
    """
    body = queries.build_search_request(node, include_computed=True)
    assert body["request_options"]["results_content_type"] == ["experimental", "computational"]

    off = queries.build_search_request(node)
    assert off["request_options"]["results_content_type"] == ["experimental"]


def test_include_computed_models_reaches_the_flat_builders_too():
    """The rcsb_search_* shims stay on these entry points, so they need the fix as well."""
    for build, kwargs in (
        (queries.build_sequence_query, {"sequence": SEQ}),
        (queries.build_chemical_query, {"value": "C9H8O4", "query_type": "formula"}),
        (queries.build_structure_query, {"entry_id": "4HHB", "assembly_id": "1"}),
        (queries.build_seqmotif_query, {"pattern": "CXCXXL", "pattern_type": "simple"}),
        (queries.build_strucmotif_query, {
            "entry_id": "2MNR",
            "residue_ids": [{"label_asym_id": "A", "label_seq_id": 162},
                            {"label_asym_id": "A", "label_seq_id": 193}]}),
    ):
        body = build(include_computed=True, **kwargs)
        assert body["request_options"]["results_content_type"] == \
            ["experimental", "computational"], build.__name__


def test_include_computed_models_reaches_a_facet_query():
    body = queries.build_search_request(
        queries.sequence_node(SEQ), include_computed=True,
        facets=[{"name": "m", "aggregation_type": "terms", "attribute": "exptl.method"}])
    assert body["request_options"]["results_content_type"] == ["experimental", "computational"]
