"""Argument descriptions for rcsb_get_branched_entities (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "ENTITY_IDS_DOC",
    "FIELDS_EXAMPLE",
]

ENTITY_IDS_DOC = (
    'entry + entity number, e.g. ["5FMB_2"]. Unknown IDs are returned under '
    '"not_found".'
)

FIELDS_EXAMPLE = "rcsb_branched_entity.pdbx_description"
