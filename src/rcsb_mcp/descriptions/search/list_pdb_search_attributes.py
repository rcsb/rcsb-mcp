"""Argument descriptions for rcsb_list_pdb_search_attributes (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "SCHEMA_DOC",
]

QUERY_DOC = (
    "Optional case-insensitive keyword to filter the catalog. Matched as a LITERAL SUBSTRING "
    'against the attribute path and description, so pass ONE keyword ("resolution", '
    '"comp_id"), not a phrase — a multi-word query only matches where those exact words are '
    "adjacent in a description. Omit to return everything."
)

SCHEMA_DOC = (
    'Which catalog — "structure" (~683 attrs: entry/entity/assembly/instance) or "chemical" '
    "(~61 attrs: chemical-component). Paths from the chemical catalog need "
    "chemical_attributes=True on rcsb_query_attribute."
)
