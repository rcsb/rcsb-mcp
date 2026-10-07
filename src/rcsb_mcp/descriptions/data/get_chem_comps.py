"""Argument descriptions for rcsb_get_chem_comps (see the package docstring for why).

`fields` uses the shared wording in shared.py; this module supplies its example.
"""

__all__ = [
    "COMP_IDS_DOC",
    "FIELDS_EXAMPLE",
]

COMP_IDS_DOC = (
    'chemical-component short codes, e.g. ["HEM", "ATP"]. Unknown IDs are returned '
    'under "not_found".'
)

FIELDS_EXAMPLE = "chem_comp.name"
