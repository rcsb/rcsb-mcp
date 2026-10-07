"""Argument descriptions for rcsb_query_fulltext (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
]

QUERY_DOC = (
    "Terms matched case-insensitively against all text annotations. Quote a phrase to "
    "require adjacency (e.g. '\"DNA polymerase\"'); separate words narrow the results; a "
    "trailing '*' is a prefix wildcard. AND/OR/NOT are NOT boolean operators here — combine "
    "conditions with rcsb_query_composer instead."
)
