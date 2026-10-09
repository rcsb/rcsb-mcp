"""Argument descriptions for rcsb_list_pdb_search_attributes (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "SCHEMA_DOC",
]

QUERY_DOC = (
    "Optional keyword(s) to filter the catalog, matched as words of the attribute path "
    "and description, best match first. Omit to return everything."
)

SCHEMA_DOC = (
    'Which catalog — "structure" (~636 attrs: entry/entity/assembly/instance) or "chemical" '
    "(~58 attrs: chemical-component). Paths from the chemical catalog need "
    "chemical_attributes=True on rcsb_query_attribute."
)
