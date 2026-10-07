"""Argument descriptions for rcsb_get_interfaces (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "INTERFACE_IDS_DOC",
    "FIELDS_EXAMPLE",
]

INTERFACE_IDS_DOC = (
    'entry-assembly.interface, e.g. ["1BMV-1.1"]. Unknown IDs are returned under '
    '"not_found".'
)

FIELDS_EXAMPLE = "rcsb_interface_info.interface_area"
