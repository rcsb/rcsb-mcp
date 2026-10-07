"""Argument descriptions for rcsb_query_structure (see the package docstring for why)."""

__all__ = [
    "ENTRY_ID_DOC",
    "ASSEMBLY_ID_DOC",
    "ASYM_ID_DOC",
]

ENTRY_ID_DOC = 'Reference PDB entry, e.g. "4HHB".'

ASSEMBLY_ID_DOC = (
    'Reference a whole assembly, e.g. "1". Defaults to assembly "1" when neither this nor '
    "asym_id is given; mutually exclusive with asym_id."
)

ASYM_ID_DOC = 'Reference a single chain instead, e.g. "A" (the mmCIF label id).'
