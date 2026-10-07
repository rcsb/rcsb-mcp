"""Argument descriptions for rcsb_get_branched_entity_instances (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "INSTANCE_IDS_DOC",
    "FIELDS_EXAMPLE",
]

INSTANCE_IDS_DOC = (
    'entry.asym_id (glycan chain), e.g. ["5FMB.C"]. Unknown IDs are returned under '
    '"not_found".'
)

FIELDS_EXAMPLE = "rcsb_branched_entity_instance_container_identifiers.asym_id"
