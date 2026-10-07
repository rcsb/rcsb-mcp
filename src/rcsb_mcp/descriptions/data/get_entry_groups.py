"""Argument descriptions for rcsb_get_entry_groups (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "GROUP_IDS_DOC",
    "FIELDS_EXAMPLE",
]

GROUP_IDS_DOC = (
    'entry-group ids, e.g. ["G_1002266"]. Unknown IDs are returned under "not_found".'
)

FIELDS_EXAMPLE = "rcsb_group_info.group_name"
