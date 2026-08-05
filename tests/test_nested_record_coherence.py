"""`group_node` must not splice a group that pins conditions to one nested-indexed record.

A Search API group is not only a boolean node — for the 41 paths the schema marks
`rcsb_nested_indexing` it is also the RECORD-COHERENCE scope. Conditions inside one group
must hold on the SAME sub-record; flattened into the parent, each need only hold SOMEWHERE
in the object. So the splice that `group_node` documented as a "semantic no-op because
AND/OR are associative" turned a restriction into a relaxation.

The tell is that the count goes UP when a restriction is added, which no correct AND can
do. Measured at return_type=entry, before the carve-out / after it:

    citation.rcsb_journal_abbrev=Nature AND citation.year=1995          137 alone
        composed with exptl.method=X-RAY DIFFRACTION      298  ->  124
    rcsb_binding_affinity.comp_id=PTR AND .type=IC50                      0 alone
        composed with exptl.method=X-RAY DIFFRACTION        5  ->    0
    rcsb_polymer_entity_annotation.type=Pfam AND .annotation_id=GO:0004672
                                                                          0 alone
        composed with exptl.method=X-RAY DIFFRACTION    3,846  ->    0

Every hit in the "before" column was checked against the Data API and carried the two
conditions on DIFFERENT records — PTR only ever has Kd; the Pfam entries have a Pfam record
and a GO record, never one record with both.

Pure tree-shape assertions, no network.
"""

import pytest

from rcsb_mcp import queries
from rcsb_mcp.search import _compose


def _f(attribute, value, operator="exact_match"):
    return {"attribute": attribute, "operator": operator, "value": value}


XRAY = queries.attribute_node([_f("exptl.method", "X-RAY DIFFRACTION")], "and")


def _is_flat(tree):
    """True when the composed tree has no group among its children."""
    return all(child.get("type") != "group" for child in tree.get("nodes", []))


# --- the defect ------------------------------------------------------------------
@pytest.mark.parametrize(
    "filters, why",
    [
        ([_f("citation.rcsb_journal_abbrev", "Nature"), _f("citation.year", 1995, "equals")],
         "one citation must be both the journal and the year"),
        ([_f("rcsb_binding_affinity.comp_id", "PTR"), _f("rcsb_binding_affinity.type", "IC50")],
         "one affinity measurement must be both the ligand and the type"),
        ([_f("rcsb_polymer_entity_annotation.type", "Pfam"),
          _f("rcsb_polymer_entity_annotation.annotation_id", "GO:0004672")],
         "one annotation record must be both"),
    ],
)
def test_a_group_pinning_a_nested_record_is_never_spliced(filters, why):
    composed = _compose([queries.attribute_node(filters, "and"), XRAY], "and")
    assert not _is_flat(composed), why


def test_the_annotation_case_goes_through_the_real_tool_path():
    """rcsb_query_attribute -> rcsb_query_composer, the shape an agent actually produces.

    This is the one that matters most: the resolver prose steers agents to resolve a
    GO/InterPro/EC term and then filter on the annotation, so this exact pair is the
    recommended workflow. Spliced it returned 3,846 entries for a query whose correct
    answer is none.
    """
    q = queries.attribute_node(
        [_f("rcsb_polymer_entity_annotation.type", "Pfam"),
         _f("rcsb_polymer_entity_annotation.annotation_id", "GO:0004672")], "and")
    composed = _compose([q, XRAY], "and")
    assert composed["type"] == "group" and composed["logical_operator"] == "and"
    inner = [c for c in composed["nodes"] if c.get("type") == "group"]
    assert len(inner) == 1, "the annotation pair must survive as its own group"
    assert len(inner[0]["nodes"]) == 2


def test_a_nested_path_nested_inside_another_keys_to_the_outer_record():
    """`.type` and `.annotation_lineage.id` describe ONE annotation.

    Both `rcsb_polymer_entity_annotation` and its `.annotation_lineage` are nested-indexed.
    Keying each condition to the DEEPEST path it matches would put these two under
    different records, find no shared record, and splice them apart — reintroducing the
    defect for exactly the lineage queries the resolvers recommend. The shallowest match
    is the coherent record.
    """
    assert queries._nested_record_of(
        "rcsb_polymer_entity_annotation.annotation_lineage.id", "text"
    ) == "rcsb_polymer_entity_annotation"
    q = queries.attribute_node(
        [_f("rcsb_polymer_entity_annotation.type", "GO"),
         _f("rcsb_polymer_entity_annotation.annotation_lineage.id", "GO:0004672")], "and")
    assert not _is_flat(_compose([q, XRAY], "and"))


# --- the splice still happens where it is safe -----------------------------------
def test_a_non_nested_group_is_still_spliced_flat():
    """The carve-out must stay narrow: 107 of 148 roots are not nested-indexed, and
    nesting them all would deepen every composed tree against the MAX_DEPTH cap for
    nothing."""
    q = queries.attribute_node(
        [_f("exptl.method", "X-RAY DIFFRACTION"),
         _f("rcsb_entry_info.polymer_entity_count", 2, "equals")], "and")
    composed = _compose([q, XRAY], "and")
    assert _is_flat(composed)
    assert len(composed["nodes"]) == 3


def test_a_single_condition_on_a_nested_path_is_still_spliced():
    """One condition pins nothing — there is no second condition to be coherent WITH,
    so keeping it nested would cost depth and buy no correctness."""
    q = queries.attribute_node([_f("citation.year", 1995, "equals")], "and")
    assert _is_flat(_compose([q, XRAY], "and"))


def test_two_conditions_on_DIFFERENT_nested_records_are_spliced():
    """Coherence is per record. A citation condition and an affinity condition have no
    shared record to preserve, so flattening them changes nothing."""
    q = queries.attribute_node(
        [_f("citation.year", 1995, "equals"),
         _f("rcsb_binding_affinity.type", "IC50")], "and")
    assert _is_flat(_compose([q, XRAY], "and"))


def test_the_opposite_operator_is_still_never_spliced():
    """Pre-existing behaviour, retested here because this change touches the same branch."""
    q = queries.attribute_node(
        [_f("exptl.method", "X-RAY DIFFRACTION"), _f("exptl.method", "NEUTRON DIFFRACTION")], "or")
    assert not _is_flat(_compose([q, XRAY], "and"))


# --- the two catalogs have different nested paths ---------------------------------
def test_the_chemical_catalog_uses_its_own_nested_paths():
    """`_nested_record_of` is per service, like `scope_of`."""
    assert queries._nested_record_of("rcsb_chem_comp_annotation.type", "text_chem") \
        == "rcsb_chem_comp_annotation"
    assert queries._nested_record_of("exptl.method", "text") is None
    # A structure-only root is not a chemical nested path.
    assert queries._nested_record_of("citation.year", "text_chem") is None


def test_a_chemical_nested_group_is_protected_too():
    q = queries.attribute_node(
        [_f("rcsb_chem_comp_annotation.type", "PDBX_MOLECULE_FEATURES"),
         _f("rcsb_chem_comp_annotation.annotation_id", "ATP")], "and", chemical=True)
    assert not _is_flat(_compose([q, XRAY], "and"))


# --- shape invariants -------------------------------------------------------------
def test_a_lone_group_is_still_returned_as_is():
    """The single-node collapse is untouched by the carve-out."""
    q = queries.attribute_node(
        [_f("citation.rcsb_journal_abbrev", "Nature"), _f("citation.year", 1995, "equals")], "and")
    assert queries.group_node([q], "and") is q


def test_repeated_composition_does_not_stack_wrappers():
    """An iterative composer must not grow a tower of same-operator groups on safe input,
    which is what the splice exists for."""
    node = queries.attribute_node([_f("exptl.method", "X-RAY DIFFRACTION")], "and")
    for _ in range(6):
        node = _compose([node, queries.attribute_node(
            [_f("rcsb_entry_info.polymer_entity_count", 2, "equals")], "and")], "and")
    assert _is_flat(node), "safe conditions must stay flat however many times they compose"


# --- grouping and isolation are SEPARATE requirements ------------------------------
def test_splitting_a_nested_pair_across_groups_breaks_it_even_with_nothing_foreign():
    """Isolation is not sufficient — grouping is its own requirement.

    Measured with only rcsb_binding_affinity conditions in the entire tree, so no foreign
    terminal exists anywhere and isolation holds in every row:

        and[Kd, v<1]                 303   together
        and[ and[Kd], and[v<1] ]     481   split
        and[ and[Kd], v<1 ]          481   HALF-split: one condition alone in a single-node
                                           group is enough, and that is exactly what
                                           rcsb_query_composer builds from two separate
                                           rcsb_query_attribute calls
        and[ and[Kd, v<1] ]          303   extra depth around the intact pair is harmless

    So the splice guard is not the whole story: group_node must also never SEPARATE a pair
    that arrived together, which is what _pins_a_nested_record already ensures by refusing
    to splice. This test pins the requirement the guard exists to satisfy.
    """
    pair = queries.attribute_node(
        [_f("rcsb_binding_affinity.type", "Kd"),
         _f("rcsb_binding_affinity.value", 1, "less")], "and")
    # Composed with an unrelated condition, the pair must survive as ONE group: spliced flat
    # it loses isolation (456), and split apart it would lose grouping (481).
    composed = _compose([pair, XRAY], "and")
    assert not _is_flat(composed)
    inner = [c for c in composed["nodes"] if c.get("type") == "group"]
    assert len(inner) == 1 and len(inner[0]["nodes"]) == 2, (
        "both affinity conditions must stay together in one group"
    )


def test_a_single_condition_is_not_wrapped_into_a_group_of_its_own():
    """The half-split shape is 481, so a lone nested condition must NOT be given a private
    group — it has to stay a bare sibling, free to be grouped with a partner later."""
    lone = queries.attribute_node([_f("rcsb_binding_affinity.type", "Kd")], "and")
    assert lone["type"] == "terminal", (
        "a one-condition build must stay a terminal; wrapping it in a group is the shape "
        "measured at 481 instead of 303"
    )


def test_the_splice_guard_counts_conditions_not_distinct_fields():
    """A pair on the SAME field must keep its group too, even though the two conditions
    cannot bind to one record on their own.

    Splicing them flat can hand them a second field they did not have, which switches the
    semantics under them:

        and[ and[annot_id in IPR..., annot_id in GO...], type=Pfam ]   555
        and[     annot_id in IPR..., annot_id in GO... , type=Pfam ]     0

    The caller grouped those two conditions in one rcsb_query_attribute call; the composer's
    job is to preserve that, not to re-decide it.
    """
    pair = queries.attribute_node(
        [_f("rcsb_polymer_entity_annotation.annotation_id", ["IPR001128"], "in"),
         _f("rcsb_polymer_entity_annotation.annotation_id", ["GO:0004497"], "in")], "and")
    assert queries._pins_a_nested_record(pair)
    composed = _compose([pair, queries.attribute_node(
        [_f("rcsb_polymer_entity_annotation.type", "Pfam")], "and")], "and")
    assert any(c.get("type") == "group" for c in composed["nodes"]), (
        "splicing this pair flat would take the query from 555 hits to 0"
    )


def test_every_nested_record_is_reachable_by_the_splice_guard():
    """_nested_record_of must place every container the schema marks, or the guard silently
    stops protecting one. Six of the 41 sit below their first path segment.

    Reachable means it RESOLVES to a nested record, not that it equals the path it came
    from: the shallowest ancestor is returned deliberately, so
    `rcsb_polymer_entity_annotation.annotation_lineage` resolves to the annotation — the
    record coherence actually keys on.
    """
    from rcsb_mcp.attribute_scopes import SEARCH_ATTRIBUTE_NESTED_ROOTS

    unreachable = [r for r in SEARCH_ATTRIBUTE_NESTED_ROOTS
                   if queries._nested_record_of(f"{r}.a", "text") is None]
    assert unreachable == [], unreachable
