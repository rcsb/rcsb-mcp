"""Argument descriptions for rcsb_get_nonpolymer_entity_instances (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "INSTANCE_IDS_DOC",
    "FIELDS_EXAMPLE",
]

INSTANCE_IDS_DOC = (
    'entry.asym_id, e.g. ["4HHB.E"]. Unknown IDs are returned under "not_found".'
)

FIELDS_EXAMPLE = "rcsb_nonpolymer_entity_instance_container_identifiers.comp_id"
