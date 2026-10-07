"""Argument descriptions for rcsb_get_polymer_entity_instances (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "INSTANCE_IDS_DOC",
    "FIELDS_EXAMPLE",
]

INSTANCE_IDS_DOC = (
    "entry.asym_id (chain), e.g. [\"4HHB.A\"] — exactly what rcsb_search_request returns "
    "with return_type=\"polymer_instance\". Unknown IDs are returned under \"not_found\". "
    "Do not guess \".A\". It is the LABEL asym_id, not the author chain — the instance "
    "an author calls chain A is often lettered differently — and any entry with more "
    "than one chain has several instances, so a guessed \".A\" silently returns a chain "
    "that is not the one that matched. Take it from a polymer_instance search hit, or "
    "from rcsb_get_entries with fields= "
    "\"polymer_entities{rcsb_polymer_entity_container_identifiers{asym_ids}}\" — the "
    "entry's own container identifiers stop at entity and assembly ids, so chains need "
    "that traversal."
)

FIELDS_EXAMPLE = "rcsb_polymer_instance_info.modeled_residue_count"
