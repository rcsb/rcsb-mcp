"""The attribute scope map — which object each searchable attribute hangs off.

This map exists to make one silent wrongness detectable. The Search API intersects
multiple conditions at the level named by `return_type`, NOT at the level the attributes
live at, so ANDing two polymer-entity conditions and asking for entries matches a
structure when one molecule carries the annotation and a *different* one supplies the
organism. Measured on AND(source_organism="Homo sapiens", source_organism="Escherichia
coli"):

    return_type=entry            745 entries
    return_type=polymer_entity   550 entities -> 550 distinct parent entries (0 outside)

195 entries — 26% of the entry-level answer — are cross-molecule, and nothing in the
response says so. Detecting that needs the scope of every attribute, which is why these
tests care most about the attributes whose PATH does not reveal their scope.

Pure data, no network: the map is vendored by scripts/generate_attribute_scopes.py.
"""

from typing import get_args

import pytest

from rcsb_mcp.attribute_scopes import (
    CHEMICAL_ATTRIBUTE_ENTRY_CONSTANT,
    CHEMICAL_ATTRIBUTE_SCOPES,
    SEARCH_ATTRIBUTE_AMBIGUOUS_ROOTS,
    SEARCH_ATTRIBUTE_ENTRY_CONSTANT,
    SEARCH_ATTRIBUTE_NESTED_ROOTS,
    SEARCH_ATTRIBUTE_REPEATING_ROOTS,
    SEARCH_ATTRIBUTE_SCOPES,
)
from rcsb_mcp.attribute_types import AttributeScope
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES
from rcsb_mcp.queries import RETURN_TYPES, scope_of
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES

SCOPES = set(get_args(AttributeScope))


# --- completeness -------------------------------------------------------------
@pytest.mark.parametrize(
    "catalog, service",
    [(SEARCH_ATTRIBUTES, "text"), (CHEMICAL_SEARCH_ATTRIBUTES, "text_chem")],
)
def test_every_searchable_attribute_has_a_scope(catalog, service):
    """A missing scope is invisible: the detector would just skip that attribute.

    So the generator treats an unplaceable root as fatal, and this pins the result —
    a catalog refresh that adds an attribute the Data API object graph cannot place
    fails here rather than quietly shrinking the detector's coverage.
    """
    missing = [a["attribute"] for a in catalog if scope_of(a["attribute"], service) is None]
    assert not missing, f"{len(missing)} attribute(s) without a scope: {missing[:10]}"


@pytest.mark.parametrize(
    "catalog, service",
    [(SEARCH_ATTRIBUTES, "text"), (CHEMICAL_SEARCH_ATTRIBUTES, "text_chem")],
)
def test_every_scope_is_a_declared_value(catalog, service):
    assert {scope_of(a["attribute"], service) for a in catalog} <= SCOPES


def test_attribute_scopes_cover_more_levels_than_return_types():
    """Attributes live at nine granularities; a search can be returned at six.

    branched_entity, non_polymer_instance and branched_instance have no return_type, so
    conditions at those levels can be intersected too loosely with NO level available to
    tighten them. Anything built on this map has to say that rather than recommend a
    return_type the API would reject.
    """
    assert RETURN_TYPES < SCOPES
    assert SCOPES - RETURN_TYPES == {
        "branched_entity", "non_polymer_instance", "branched_instance",
    }


# --- the paths that do not reveal their own scope ------------------------------
@pytest.mark.parametrize(
    "attribute, expected, why",
    [
        # The motivating case. Reads entry-level; is per-molecule. This one attribute
        # produced the 26% measured above.
        ("rcsb_entity_source_organism.ncbi_scientific_name", "polymer_entity",
         "no 'entity' prefix on the path, but the organism is a property of the molecule"),
        ("rcsb_entity_host_organism.ncbi_scientific_name", "polymer_entity",
         "same shape as source_organism"),
        ("entity_src_gen.pdbx_host_org_scientific_name", "polymer_entity",
         "'entity_src_gen' names no level a caller would recognise"),
        ("entity_poly.rcsb_entity_polymer_type", "polymer_entity", "likewise"),
        # ~15 em_* roots / ~100 attributes are entry-scoped and not one says so.
        ("em_imaging.microscope_model", "entry", "experimental metadata is per structure"),
        ("em_3d_reconstruction.resolution", "entry", "likewise"),
        ("exptl.method", "entry", "likewise"),
        ("citation.title", "entry", "likewise"),
        ("refine.ls_d_res_high", "entry", "likewise"),
        # Reached only at depth 2, through the object that owns them.
        ("rcsb_uniprot_protein.name.value", "polymer_entity", "via polymer_entity.uniprots"),
        ("rcsb_pubmed_abstract_text", "entry", "via entry.pubmed"),
        ("drugbank_info.brand_names", "mol_definition", "via chem_comp.drugbank"),
        # Self-describing, included so a regression that flattens everything is caught.
        ("rcsb_polymer_instance_annotation.type", "polymer_instance", ""),
        ("rcsb_ligand_neighbors.ligand_comp_id", "polymer_instance",
         "rank tie: polymer_instance is askable, branched_instance is not"),
        ("rcsb_assembly_info.polymer_entity_count", "assembly", ""),
        ("rcsb_entry_info.resolution_combined", "entry", ""),
    ],
)
def test_scope_is_derived_not_guessed_from_the_path(attribute, expected, why):
    assert scope_of(attribute) == expected, why


# --- the two catalogs genuinely disagree ---------------------------------------
def test_rcsb_id_means_something_different_in_each_catalog():
    """The reason the map is per catalog rather than one shared table.

    The structure schema documents rcsb_id as "...concatenation of entry and entity
    identifiers"; the chemical schema as "a unique identifier for the chemical definition
    in this container". A single owner map built over every Data API root resolved the
    chemical one to "entry" — visibly wrong next to 15 sibling roots that are all
    mol_definition, and a false fact if the scope is ever surfaced to a caller.
    """
    assert scope_of("rcsb_id", "text_chem") == "mol_definition"
    assert scope_of("rcsb_id", "text") != "mol_definition"


def test_every_chemical_attribute_is_a_chemical_definition():
    """The chemical index has exactly one granularity, so nothing in it can split."""
    assert set(CHEMICAL_ATTRIBUTE_SCOPES.values()) == {"mol_definition"}
    assert CHEMICAL_ATTRIBUTE_ENTRY_CONSTANT == []


# --- the overrides and the collapse --------------------------------------------
@pytest.mark.parametrize("attribute", SEARCH_ATTRIBUTE_ENTRY_CONSTANT)
def test_an_entry_id_is_entry_scoped_wherever_it_is_filed(attribute):
    """`rcsb_polymer_entity_container_identifiers.entry_id` sits under an entity root, but
    its VALUE is the parent entry's id — identical across every entity of that entry.

    Two conditions on it therefore cannot be met by different siblings, so treating it as
    entity-scoped would make a detector fire on a query that cannot actually split.
    """
    assert scope_of(attribute) == "entry"


def test_the_entry_constant_list_is_mostly_load_bearing():
    """6 of the 8 overrides genuinely change the answer; 2 are no-ops kept for uniformity.

        assembly           -> entry   rcsb_assembly_container_identifiers.entry_id
        branched_entity    -> entry   rcsb_branched_entity_container_identifiers.entry_id
        branched_instance  -> entry   rcsb_branched_entity_instance_container_identifiers
        non_polymer_instance -> entry rcsb_nonpolymer_entity_instance_container_identifiers
        polymer_entity     -> entry   rcsb_polymer_entity_container_identifiers.entry_id
        polymer_instance   -> entry   rcsb_polymer_entity_instance_container_identifiers

    The two no-ops sit under roots that are entry-scoped already
    (rcsb_entry_container_identifiers, rcsb_comp_model_provenance). They stay in the list
    because it is generated by an exact leaf-name rule, not curated — carving them out
    would turn a mechanical rule into a judgement call for no gain.
    """
    changed = [a for a in SEARCH_ATTRIBUTE_ENTRY_CONSTANT
               if SEARCH_ATTRIBUTE_SCOPES[a.split(".")[0]] != "entry"]
    assert len(changed) == 6, changed
    assert len(SEARCH_ATTRIBUTE_ENTRY_CONSTANT) == 8


def test_ambiguous_roots_collapse_to_the_coarsest_scope():
    """Silence is the safe failure. A root the Data API exposes at several levels is
    recorded as the COARSEST, which can only make a split detector quieter — never make
    it fire on a query that is fine.

    rcsb_id is the extreme case: it exists at all nine granularities, so it collapses to
    "entry" and can never trigger anything.
    """
    for root, found in SEARCH_ATTRIBUTE_AMBIGUOUS_ROOTS.items():
        assert len(found) > 1
        assert SEARCH_ATTRIBUTE_SCOPES[root] in found
    assert SEARCH_ATTRIBUTE_SCOPES["rcsb_id"] == "entry"


@pytest.mark.parametrize(
    "root", ["rcsb_ligand_neighbors", "pdbx_vrpt_summary_entity_fit_to_map"]
)
def test_a_rank_tie_prefers_a_scope_that_HAS_a_return_type(root):
    """Ties are NOT broken alphabetically, and this is the bug that taught us why.

    Both roots resolve to two rank-2 instance scopes. The alphabetical winner was
    `branched_instance`, which has no return_type — so the map reported a granularity a
    caller cannot ask for, and anything built on it would have said "this cannot be
    narrowed" when it can:

        AND(rcsb_ligand_neighbors.ligand_comp_id=ATP, =HEM)
            return_type=entry             -> 5   (all cross-chain false positives)
            return_type=polymer_instance  -> 0

    The previous version of this test asserted the alphabetical tie-break "costs nothing"
    because both candidates were instance-level. That pinned the assumption rather than
    checking it: the two candidates were NOT interchangeable, because only one of them
    is a level the API will accept.
    """
    assert SEARCH_ATTRIBUTE_SCOPES[root] in RETURN_TYPES
    assert len(SEARCH_ATTRIBUTE_AMBIGUOUS_ROOTS[root]) > 1


# --- the second splitting axis: repeated records inside one object ---------------
def test_repeating_roots_are_recorded_because_scope_alone_is_not_enough():
    """Equal scope does NOT mean two conditions describe the same thing.

    `software.name` and `software.classification` are both entry-scoped, so a
    scope-equality check stays silent — but an entry holds a LIST of software records:

        AND(software.name ~ "PHENIX", software.classification ~ "data reduction")
        -> 80,050 entries; of 25 sampled, 18 (72%) have NO single software record with both

    That is the same failure as the cross-molecule case, one level down, and it reaches
    roots at every scope. A detector using only `scope_of` would miss all of it.
    """
    assert scope_of("software.name") == scope_of("software.classification") == "entry"
    assert "software" in SEARCH_ATTRIBUTE_REPEATING_ROOTS
    # It is a large minority of the catalog, not a curiosity.
    assert 90 <= len(SEARCH_ATTRIBUTE_REPEATING_ROOTS) <= 115


def test_nested_indexing_is_recorded_as_paths_not_roots():
    """The flag marks the coherent RECORD, which is often a sub-object.

    `rcsb_uniprot_container_identifiers` is not itself nested-indexed but its
    `.reference_sequence_identifiers` is; 6 roots have that shape. Recording the root as
    nested would claim record coherence for its other fields too, which the API does not
    offer — so an attribute is coherent-able only when it sits UNDER one of these paths.
    """
    assert "rcsb_uniprot_container_identifiers.reference_sequence_identifiers" in SEARCH_ATTRIBUTE_NESTED_ROOTS
    assert "rcsb_uniprot_container_identifiers" not in SEARCH_ATTRIBUTE_NESTED_ROOTS
    assert "citation" in SEARCH_ATTRIBUTE_NESTED_ROOTS  # flagged at the root itself


def test_nested_indexing_separates_the_fixable_from_the_unfixable():
    """The whole point of splitting the two lists.

    A nested-indexed record can be pinned by keeping the conditions in their own group,
    so the looseness is a query-shape problem. A repeating root WITHOUT the flag offers
    no such guarantee — no arrangement of the query forces the conditions onto one
    record — so the honest answer there is to say so, not to suggest a fix.
    """
    nested_roots = {p.split(".")[0] for p in SEARCH_ATTRIBUTE_NESTED_ROOTS}
    unfixable = set(SEARCH_ATTRIBUTE_REPEATING_ROOTS) - nested_roots
    assert "citation" in nested_roots, "the API tracks citation records"
    assert "software" in unfixable, "nothing in a query can pin software.name to one record"
    assert len(unfixable) > len(nested_roots), (
        "most repeating roots are NOT nested-indexed, so 'keep it nested' cannot be the "
        "general advice"
    )


# --- unknown stays unknown ------------------------------------------------------
@pytest.mark.parametrize("attribute", ["not_a_real_root.field", "not_a_real_root", ""])
def test_an_unrecognised_ROOT_has_no_scope(attribute):
    """None means "not in this catalog", and callers must not turn it into a scope.

    Inventing a scope for an unrecognised root would put a confident claim behind a path
    the Search API will reject anyway.
    """
    assert scope_of(attribute) is None


@pytest.mark.parametrize(
    "attribute", ["exptl.methd", "exptl", "em_imaging.no_such_field.nested"]
)
def test_a_known_root_with_an_unknown_LEAF_still_has_that_root_s_scope(attribute):
    """Scope is a property of the ROOT, so the leaf does not have to be recognised.

    That is the actual contract, and it is the right one: everything under `exptl` is
    entry-scoped whether or not `methd` exists, and a mistyped leaf is rejected by the
    attribute-path validation that runs before a query is built — scope never has to
    double as a spell checker.

    The one place a root does NOT determine the scope is the enumerated entry-constant
    list above, which is why that list is data rather than a rule applied here.
    """
    assert scope_of(attribute) == "entry"


def test_a_structure_attribute_is_unknown_to_the_chemical_catalog():
    """The catalogs are separate indexes; crossing them silently would be a wrong scope."""
    assert scope_of("em_imaging.microscope_model", "text_chem") is None
