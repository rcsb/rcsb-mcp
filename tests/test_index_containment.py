"""The containment relation the SEARCH INDEX implements, and the assembly rule.

Separate from tests/test_attribute_scopes.py on purpose: that file pins DERIVED data (which
object each attribute hangs off, generated from the Data API). This one pins a hand-authored
claim about how the Search API BEHAVES, which no schema states and which contradicts the
structural hierarchy — so it is carried by measurement, recorded here.

The PDB nests entry > assembly > entity > instance structurally: an assembly holds a subset
of the entry's instances. The index does not follow that. Every measurement below is against
the live Search + Data APIs; the tests themselves are offline.

Ground truth used throughout, 1DEE ("S. aureus protein A bound to a human IgM Fab"), chosen
because its five assemblies genuinely differ in composition:

    1DEE-1  chains A,B    entities 1,2    Homo sapiens only
    1DEE-2  chains C,D,G  entities 1,2,3  + Staphylococcus aureus
    1DEE-3  chains E,F,H  entities 1,2,3  + Staphylococcus aureus
    1DEE-4  chains E,F    entities 1,2    Homo sapiens only
    1DEE-5  chains C,D    entities 1,2    Homo sapiens only
"""

import pytest

from rcsb_mcp.attribute_types import AttributeScope
from rcsb_mcp.queries import (
    RETURN_TYPES,
    answers_at_entry_level,
    scope_contains,
    scope_of,
    scopes_are_comparable,
)

from typing import get_args

SCOPES = set(get_args(AttributeScope))


# --- the relation ---------------------------------------------------------------
def test_entry_contains_every_other_scope():
    for scope in SCOPES - {"entry"}:
        assert scope_contains("entry", scope), scope
    assert not scope_contains("entry", "entry"), "containment is strict"


@pytest.mark.parametrize(
    "entity, instance",
    [
        ("polymer_entity", "polymer_instance"),
        ("non_polymer_entity", "non_polymer_instance"),
        ("branched_entity", "branched_instance"),
    ],
)
def test_an_entity_contains_its_own_instances_only(entity, instance):
    """entity > instance is respected by the index, unlike assembly > entity.

    Measured: organism="Escherichia coli" at return_type=polymer_instance returned 200
    instances, 0 of which belonged to an entity without that organism.
    """
    assert scope_contains(entity, instance)
    assert not scope_contains(instance, entity)
    for other in SCOPES - {instance, "entry"}:
        if other != entity:
            assert not scope_contains(entity, other), f"{entity} must not contain {other}"


def test_assembly_contains_nothing():
    """The finding this whole relation exists for.

    Structurally an assembly holds a subset of the entry's instances, so the obvious model
    says assembly contains entities and instances. The index disagrees: nothing is indexed
    as being INSIDE an assembly, so a match anywhere in the entry lights up every assembly.

        auth_asym_id=G, present ONLY in 1DEE-2
            @assembly         -> 1DEE-1, 1DEE-2, 1DEE-3, 1DEE-4, 1DEE-5   (all five)
            @polymer_instance -> 1DEE.G                                    (correct)
    """
    for scope in SCOPES:
        assert not scope_contains("assembly", scope), (
            f"assembly must contain nothing, but claims to contain {scope}"
        )
    assert scope_contains("entry", "assembly"), "an assembly does belong to one entry"


def test_the_relation_has_no_cycles():
    """A cycle would make scope_contains loop or answer arbitrarily."""
    for scope in SCOPES:
        assert not scope_contains(scope, scope)


# --- comparability, which is what a lone condition turns on ----------------------
@pytest.mark.parametrize(
    "a, b, expected, why",
    [
        ("entry", "polymer_entity", True, "every entity belongs to exactly one entry"),
        ("polymer_entity", "polymer_instance", True, "and every instance to one entity"),
        ("entry", "assembly", True, "an assembly belongs to one entry"),
        ("polymer_entity", "polymer_entity", True, "same scope"),
        # The pairs that make the assembly rule necessary.
        ("assembly", "polymer_entity", False, "an entity is in SOME assemblies, not all"),
        ("assembly", "polymer_instance", False, "1DEE.G is in 1DEE-2 alone"),
        ("assembly", "mol_definition", False, "same shape"),
        # Sibling entity types are unrelated in either direction.
        ("polymer_entity", "non_polymer_entity", False, "siblings, neither contains the other"),
        ("polymer_instance", "non_polymer_instance", False, "likewise"),
    ],
)
def test_comparability(a, b, expected, why):
    assert scopes_are_comparable(a, b) is expected, why
    assert scopes_are_comparable(b, a) is expected, "the relation is symmetric"


# --- the assembly rule -----------------------------------------------------------
@pytest.mark.parametrize(
    "scope", ["polymer_entity", "non_polymer_entity", "branched_entity",
              "polymer_instance", "non_polymer_instance", "branched_instance",
              "mol_definition"]
)
def test_asking_for_assemblies_answers_finer_conditions_at_entry_level(scope):
    """One condition is enough — no AND required, which is what sets this apart.

    Measured: organism="Staphylococcus aureus" @assembly returned 2,449 assemblies; of 150
    checked from multi-assembly entries, 3 contained no such entity. For 1DEE specifically
    it is 3 of 5, because that entry's assemblies actually differ.
    """
    assert answers_at_entry_level("assembly", scope)


@pytest.mark.parametrize("scope", ["entry", "assembly"])
def test_an_entry_or_assembly_condition_is_not_projected(scope):
    """Nothing finer is involved, so there is nothing to project."""
    assert not answers_at_entry_level("assembly", scope)


@pytest.mark.parametrize("return_type", sorted(RETURN_TYPES - {"assembly"}))
def test_only_assemblies_are_affected(return_type):
    """Every other return_type sits on the containment chain, where the index behaves.

    This is the half that keeps the rule cheap: it is one special case, not a general
    incomparability check across all six return types.
    """
    for scope in SCOPES:
        assert not answers_at_entry_level(return_type, scope)


def test_the_rule_reaches_the_attribute_that_motivated_it():
    """End to end from a real attribute path, not a bare scope string."""
    scope = scope_of("rcsb_entity_source_organism.ncbi_scientific_name")
    assert scope == "polymer_entity"
    assert answers_at_entry_level("assembly", scope)
    assert not answers_at_entry_level("entry", scope), (
        "entry > entity is honoured by the index; only assembly is not"
    )


def test_an_unknown_scope_does_not_trigger_the_rule():
    """scope_of returns None for an unrecognised root, and None is not a scope.

    Silence is the safe failure: a note fired on an attribute nothing could place would be
    a confident claim about a path the API is going to reject anyway.
    """
    assert not answers_at_entry_level("assembly", None)
    assert not answers_at_entry_level("assembly", "not_a_scope")
