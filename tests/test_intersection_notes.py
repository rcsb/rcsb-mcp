"""`queries.intersection_notes` — where a query was intersected more loosely than it reads.

The Search API intersects ANDed conditions at the level named by `return_type`, and within
one object it intersects across repeated records. Neither is visible in the response, so a
too-loose answer looks exactly like a correct one. These notes are the only signal.

Their SILENCE is as load-bearing as their text: on this server `return_type="entry"` is the
common default and most attributes are finer than entry, so a rule like "warn whenever a
scope differs from return_type" fires on ~35% of the baseline corpus, and is provably wrong
on most of those. A note that common gets skipped, taking the real ones with it. So the
quiet cases below are tested at least as carefully as the loud ones.

Every number quoted is measured against the live API; the tests are pure and offline.
"""

import pytest

from rcsb_mcp import queries
from rcsb_mcp.queries import MAX_INTERSECTION_NOTES, intersection_notes

ORG = "rcsb_entity_source_organism.ncbi_scientific_name"


def _f(attribute, value, operator="exact_match"):
    return {"attribute": attribute, "operator": operator, "value": value}


def _attr(filters, logical_operator="and", chemical=False):
    return queries.attribute_node(filters, logical_operator, chemical=chemical)


def _flat_and(*attribute_value_pairs):
    """A group whose terminals are direct siblings — the shape that loses coherence."""
    return {"type": "group", "logical_operator": "and", "nodes": [
        queries._text_node(a, op, v) for a, op, v in attribute_value_pairs]}


# --- 1. two comparable conditions finer than return_type (fixable) ----------------
def test_two_per_molecule_conditions_asked_for_as_entries():
    """The case the whole scope map was built for.

        AND(organism="Homo sapiens", organism="Escherichia coli")
            return_type=entry          745 entries
            return_type=polymer_entity 550 entities -> 550 parent entries, 0 outside
        => 195 entries (26%) matched only because two DIFFERENT molecules did.
    """
    notes = intersection_notes(
        _attr([_f(ORG, "Homo sapiens"), _f(ORG, "Escherichia coli")]), "entry")
    assert any("polymer_entity" in n and 'return_type="polymer_entity"' in n for n in notes), notes


def test_the_note_names_a_return_type_that_actually_exists():
    """branched_entity / non_polymer_instance / branched_instance have NO return_type, so
    a note must never recommend one — the API rejects it with a 400."""
    for note in intersection_notes(
            _attr([_f("rcsb_branched_entity_container_identifiers.rcsb_id", "1ABC_1"),
                   _f("rcsb_branched_entity_container_identifiers.rcsb_id", "1ABC_2")]), "entry"):
        for scope in ("branched_entity", "non_polymer_instance", "branched_instance"):
            assert f'return_type="{scope}"' not in note, note


def test_taking_the_advice_retires_the_note():
    """Asked at polymer_entity, the cross-molecule finding no longer applies."""
    notes = intersection_notes(
        _attr([_f(ORG, "Homo sapiens"), _f(ORG, "Escherichia coli")]), "polymer_entity")
    assert not any("DIFFERENT polymer_entity can satisfy" in n for n in notes), notes


def test_two_ligand_conditions_asked_for_as_entries():
    """Chemical-component paths in structure search are judged per non-polymer entity, so
    two of them at entry level can be met by two DIFFERENT ligands. Measured 2026-10-08,
    AND(comp_id=HEM, nonpolymer_comp_id=ATP): 5 entries, 0 non-polymer entities."""
    node = _flat_and(("rcsb_chem_comp_container_identifiers.comp_id", "exact_match", "HEM"),
                     ("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id",
                      "exact_match", "ATP"))
    notes = intersection_notes(node, "entry")
    assert any('DIFFERENT non_polymer_entity' in n and 'return_type="non_polymer_entity"' in n
               for n in notes), notes
    assert intersection_notes(node, "non_polymer_entity") == []
    # ...while the same paths in the chemical index describe one definition: nothing to split
    chem = _attr([_f("rcsb_chem_comp_container_identifiers.comp_id", "HEM"),
                  _f("chem_comp.type", "non-polymer")], chemical=True)
    assert intersection_notes(chem, "mol_definition") == []


def test_conditions_on_different_KINDS_of_object_stay_silent():
    """"A human protein and an ATP ligand" is two different objects BY DEFINITION.

    polymer_entity and non_polymer_entity are incomparable — neither contains the other —
    so nothing is being lost and a note would be pure noise. This is the single most
    important silence here: it is a completely ordinary query.
    """
    node = queries.group_node([
        _attr([_f(ORG, "Homo sapiens")]),
        _attr([_f("rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id", "ATP")]),
    ], "and")
    assert intersection_notes(node, "entry") == []


def test_a_lone_finer_condition_stays_silent():
    """One condition cannot be split — "entries containing a human protein" is exact."""
    assert intersection_notes(_attr([_f(ORG, "Homo sapiens")]), "entry") == []


def test_OR_stays_silent():
    """Under OR, different objects satisfying different conditions is what was ASKED."""
    assert intersection_notes(
        _attr([_f(ORG, "Homo sapiens"), _f(ORG, "Escherichia coli")], "or"), "entry") == []


def test_a_LONE_condition_at_assembly_is_flagged():
    """No AND, no second condition, no group — the mode a count-based trigger misses.

    1DEE ("S. aureus protein A bound to a human IgM Fab") has five assemblies; three hold
    no S. aureus entity at all, and organism="Staphylococcus aureus" @assembly returns all
    five. Chain G exists only in 1DEE-2, and @assembly returns all five for that too.
    """
    notes = intersection_notes(_attr([_f(ORG, "Homo sapiens")]), "assembly")
    assert notes and "ENTRY level" in notes[0]
    assert "No return_type narrows this" in notes[0]


def test_an_entry_scoped_condition_at_assembly_is_silent():
    """Nothing finer is involved, so there is nothing to project."""
    assert intersection_notes(
        _attr([_f("exptl.method", "X-RAY DIFFRACTION")]), "assembly") == []


@pytest.mark.parametrize("return_type", ["entry", "polymer_entity", "polymer_instance"])
def test_entity_and_instance_return_types_get_no_projection_note(return_type):
    """Only assembly and mol_definition project an entry-level answer onto their objects."""
    notes = intersection_notes(_attr([_f(ORG, "Homo sapiens")]), return_type)
    assert not any("ENTRY level" in n for n in notes)


# --- 3. return_type="mol_definition" with a non-chemical condition ----------------
CHEM_COMP_ID = "rcsb_chem_comp_container_identifiers.comp_id"


def test_a_structure_condition_at_mol_definition_is_flagged():
    """Measured 2026-10-08: comp_id=HEM as a STRUCTURE attribute at mol_definition returns
    2,033 definitions -- every component of the 6,485 HEM entries, ALA and SO4 included.
    The same condition through the chemical index returns 1: HEM."""
    [note] = intersection_notes(_attr([_f(CHEM_COMP_ID, "HEM")]), "mol_definition")
    assert f"`{CHEM_COMP_ID}`" in note and "ENTRY level" in note
    assert "chemical_attributes=True" in note, "it must name the way to ask the component itself"


def test_any_non_chemical_service_is_flagged_by_name():
    """Full text, sequence and structure searches are entry-level answers too ("protoporphyrin"
    full text at mol_definition: 2,087 definitions, standard residues included)."""
    full_text = {"type": "terminal", "service": "full_text", "parameters": {"value": "heme"}}
    [note] = intersection_notes(full_text, "mol_definition")
    assert "the full-text condition" in note


def test_one_mol_definition_note_however_many_structure_conditions():
    node = _attr([_f(ORG, "Homo sapiens"), _f("exptl.method", "X-RAY DIFFRACTION")])
    assert len([n for n in intersection_notes(node, "mol_definition") if "mol_definition" in n]) == 1


def test_a_mixed_query_names_its_structure_condition():
    """Chemical condition AND structure condition: the chemical one is judged per definition,
    the structure one per entry -- the note names the latter."""
    node = {"type": "group", "logical_operator": "and", "nodes": [
        queries._text_node("chem_comp.formula_weight", "greater", 500, service="text_chem"),
        queries._text_node(ORG, "exact_match", "Thermus thermophilus HB8")]}
    [note] = [n for n in intersection_notes(node, "mol_definition") if "mol_definition" in n]
    assert f"`{ORG}`" in note and "chem_comp.formula_weight" not in note


def test_the_chemical_index_at_mol_definition_is_silent():
    """text_chem and rcsb_query_chemical judge the definition itself: nothing is projected."""
    chem = _attr([_f(CHEM_COMP_ID, "HEM"), _f("chem_comp.type", "non-polymer")], chemical=True)
    assert intersection_notes(chem, "mol_definition") == []
    smiles = queries.chemical_node("c1ccccc1", "descriptor", descriptor_type="SMILES")
    assert intersection_notes(smiles, "mol_definition") == []
    # ...and a structure condition asked for as entries is not this finding
    assert intersection_notes(_attr([_f(CHEM_COMP_ID, "HEM")]), "entry") == []


# --- shape ---------------------------------------------------------------------
def test_notes_are_capped():
    """A wall of notes reads as boilerplate and gets skipped whole."""
    node = _flat_and(
        (ORG, "exact_match", "Homo sapiens"), (ORG, "exact_match", "Escherichia coli"),
        ("citation.rcsb_journal_abbrev", "exact_match", "Nature"),
        ("citation.year", "equals", 1995),
        ("software.name", "contains_phrase", "PHENIX"),
        ("software.classification", "contains_phrase", "data reduction"),
        ("rcsb_polymer_instance_annotation.type", "exact_match", "CATH"),
        ("rcsb_polymer_instance_annotation.annotation_id", "exact_match", "1.10.10.10"),
    )
    assert 0 < len(intersection_notes(node, "assembly")) <= MAX_INTERSECTION_NOTES


def test_notes_are_deduplicated():
    node = _flat_and((ORG, "exact_match", "Homo sapiens"),
                     (ORG, "exact_match", "Escherichia coli"),
                     (ORG, "exact_match", "Mus musculus"))
    assert len(intersection_notes(node, "entry")) == len(set(intersection_notes(node, "entry")))


def test_an_unplaceable_attribute_is_ignored_rather_than_guessed():
    """scope_of returns None for an unknown root; a note built on None would be a
    confident claim about a path the API is going to reject anyway."""
    node = _flat_and(("not_a_real_root.field", "exact_match", "x"),
                     ("not_a_real_root.other", "exact_match", "y"))
    assert intersection_notes(node, "entry") == []


def test_a_non_attribute_service_is_ignored():
    """Sequence/structure terminals carry no attribute path to scope."""
    node = queries.group_node(
        [queries.sequence_node("MVLSPADKTNVKAAW", "protein"), _attr([_f(ORG, "Homo sapiens")])],
        "and")
    assert intersection_notes(node, "entry") == []


# --- same field twice: nothing to bind, so nothing to say -------------------------
def _annot(value, operator="exact_match"):
    return {"attribute": "rcsb_polymer_entity_annotation.annotation_id",
            "operator": operator, "value": value}


# --- nested records get NO note, deliberately -------------------------------------
def test_nothing_is_said_about_nested_records_however_the_query_is_shaped():
    """Removed 2026-08-05 after the Search API team explained the design. Do not re-add.

    The branch existed on the premise that these queries were "intersected more loosely than
    they read". They are not. Grouping SELECTS the semantics, on purpose:

        "In our search system and(A, B, C) is not equivalent to and(and(A, B), C) only when
         A and B are fields stored in nested documents ... we overload the boolean syntax
         with special semantics for such fields ... users can explicitly control the search
         semantics. Attributes that don't need to be evaluated against the same nested
         document don't need to be part of the same group even if they have a nested
         context available."

    So both shapes are valid and mean different things, and only INTENT separates them —
    which a query document does not carry:

        type=Kd + value<1        grouped 303, split 481   -- grouped is almost certainly meant
        IPR001128 + type=GO      grouped   0, split 1549  -- SPLIT is the only sensible one,
                                                             since no annotation record is
                                                             both an InterPro id and type GO

    A note firing on the split shape would have called that second query suspect. Detection
    was never the hard part — a prototype scored 9/9 on every shape measured — but nothing in
    the tree distinguishes the two rows above, so any trigger is wrong half the time.

    The rule now lives where the choice is actually made: `nested_group` on each catalog
    record, plus the prose in rcsb_query_attribute and rcsb_list_pdb_search_attributes.
    queries._pins_a_nested_record still stops rcsb_query_composer SPLICING a group the caller
    built deliberately — preserving an expressed choice, a different job from guessing an
    unexpressed one.
    """
    KD = _f("rcsb_binding_affinity.type", "Kd")
    LT = _f("rcsb_binding_affinity.value", 1, "less")
    shapes = [
        ("together and alone (303)", _attr([KD, LT]), "entry"),
        ("sharing their group (456)", _flat_and(
            ("rcsb_binding_affinity.type", "exact_match", "Kd"),
            ("rcsb_binding_affinity.value", "less", 1),
            ("exptl.method", "exact_match", "X-RAY DIFFRACTION")), "entry"),
        ("split across groups (481)",
         queries.group_node([_attr([KD]), _attr([LT])], "and"), "entry"),
        # Asked at polymer_entity so finding 1 has nothing to say either: these are
        # entity-scoped, and at return_type="entry" it correctly reports that two
        # different entities could satisfy them. That note is unrelated and stays.
        ("an intended split (1549)", _attr(
            [_f("rcsb_polymer_entity_annotation.annotation_id", "IPR001128"),
             _f("rcsb_polymer_entity_annotation.type", "GO"),
             _f("exptl.method", "X-RAY DIFFRACTION")]), "polymer_entity"),
        ("a deep nested record (rcsb_ec_lineage)", _attr(
            [_f("rcsb_polymer_entity.rcsb_ec_lineage.depth", 1, "equals"),
             _f("rcsb_polymer_entity.rcsb_ec_lineage.id", "2.7.11.1"),
             _f("exptl.method", "X-RAY DIFFRACTION")]), "polymer_entity"),
    ]
    for why, node, return_type in shapes:
        assert intersection_notes(node, return_type) == [], why

    # And an entity-scoped pair keeps its finding-1 note at entry level, which is about
    # DIFFERENT ENTITIES, not different annotation records — removing finding 2 must not
    # have taken it with it. Matched INDEPENDENTLY (beside an unrelated condition) is the
    # shape where that is true. Bound in a group of their own the pair is held to one
    # annotation record, so to one entity, and the note would be false: measured 2026-10-09
    # (annotation type=Pfam + name~kinase, released Q1 2024), bound 165 entries = 165 behind
    # matching entities; independent 574 vs 556, 18 reached only via different entities.
    # (Until then this asserted the note on the bound shape — see _binds_one_record.)
    entity_scoped = _attr([_f("rcsb_polymer_entity_annotation.annotation_id", "IPR001128"),
                           _f("rcsb_polymer_entity_annotation.type", "GO"),
                           _f("exptl.method", "X-RAY DIFFRACTION")])
    notes = intersection_notes(entity_scoped, "entry")
    assert any('return_type="polymer_entity"' in n for n in notes), notes
    assert not any("record" in n for n in notes), (
        f"nothing may mention nested records any more: {notes}"
    )


# --- a group the API binds to ONE nested record: one object, nothing to split ---------
SYM = "rcsb_struct_symmetry"
XRAY = _f("exptl.method", "X-RAY DIFFRACTION")


def _sym(field, value):
    return _f(f"{SYM}.{field}", value)


def _with_xray(group):
    """Compose like rcsb_query_composer: a group binding a record is kept, not spliced."""
    return queries.group_node([group, _attr([XRAY])], "and")


def _split_notes(node):
    return [n for n in intersection_notes(node, "entry") if "DIFFERENT assembly" in n]


def test_bound_annotation_conditions_cannot_split_across_entities():
    """One level down, the same: Pfam + name~kinase bound in their own group reach 165
    entries, all 165 behind an entity carrying one such record."""
    bound = _attr([_f("rcsb_polymer_entity_annotation.type", "Pfam"),
                   _f("rcsb_polymer_entity_annotation.name", "kinase", "contains_words")])
    notes = intersection_notes(_with_xray(bound), "entry")
    assert not any("DIFFERENT polymer_entity" in n for n in notes), notes


def test_conditions_bound_to_one_record_cannot_split_across_objects():
    """The 2026-10-09 session's step 8: oligomeric_state + kind built in ONE call. The API
    holds both to the same symmetry record, a record belongs to one assembly, so "a
    DIFFERENT assembly can satisfy each one" cannot happen. Measured with symbol=C4 in place
    of kind: 0 entries bound, 26 matched independently."""
    assert _split_notes(_with_xray(_attr([_sym("oligomeric_state", "Homo 2-mer"),
                                          _sym("kind", "Global Symmetry")]))) == []


def test_the_same_conditions_matched_independently_keep_the_note():
    """Beside an unrelated condition in ONE group they are matched independently -- Homo
    2-mer + C4: 26 entries but 1 assembly. That is exactly the split the note exists for."""
    loose = _flat_and((f"{SYM}.oligomeric_state", "exact_match", "Homo 2-mer"),
                      (f"{SYM}.symbol", "exact_match", "C4"),
                      ("exptl.method", "exact_match", "X-RAY DIFFRACTION"))
    assert _split_notes(loose)


def test_a_same_field_pair_on_its_own_is_not_bound():
    """Homo 2-mer AND Homo 4-mer in their own group: 2,153 entries bound or not -- one field
    never binds a record, so different assemblies can still supply each value."""
    assert _split_notes(_with_xray(_attr([_sym("oligomeric_state", "Homo 2-mer"),
                                          _sym("oligomeric_state", "Homo 4-mer")])))


def test_a_second_field_binds_the_same_field_pair_too():
    """The same pair plus kind=Global Symmetry in one group: 0 entries -- the whole group is
    bound to one record, which cannot be both a dimer and a tetramer."""
    assert _split_notes(_with_xray(_attr([_sym("oligomeric_state", "Homo 2-mer"),
                                          _sym("oligomeric_state", "Homo 4-mer"),
                                          _sym("kind", "Global Symmetry")]))) == []


def test_an_unmeasured_shape_keeps_the_note():
    """A negated condition in the group has not been measured, so the note stays on."""
    negated = {**_sym("kind", "Global Symmetry"), "negation": True}
    assert _split_notes(_with_xray(_attr([_sym("oligomeric_state", "Homo 2-mer"), negated])))
