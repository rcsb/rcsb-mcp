"""Argument descriptions for rcsb_get_polymer_entity_groups (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "GROUP_IDS_DOC",
    "FIELDS_EXAMPLE",
]

GROUP_IDS_DOC = (
    'sequence-cluster group ids, e.g. ["85_70"]. Unknown IDs are returned under '
    '"not_found".'
)

FIELDS_EXAMPLE = "rcsb_group_info.group_name"
