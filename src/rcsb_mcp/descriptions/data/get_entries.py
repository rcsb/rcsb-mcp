"""Argument descriptions for rcsb_get_entries (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "ENTRY_IDS_DOC",
    "FIELDS_EXAMPLE",
]

ENTRY_IDS_DOC = (
    '4-character PDB entry codes, e.g. ["4HHB", "1MBN"]; pass a one-element list for a '
    'single entry. Unknown IDs are returned under "not_found".'
)

FIELDS_EXAMPLE = "struct.title"
