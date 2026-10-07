"""Argument descriptions for rcsb_query_composer (see the package docstring for why)."""

__all__ = [
    "QUERIES_DOC",
    "LOGICAL_OPERATOR_DOC",
]

QUERIES_DOC = (
    "Two or more query documents from any rcsb_query_* tool (including this one). Pass each "
    "through exactly as returned."
)

LOGICAL_OPERATOR_DOC = '"and" (default) or "or".'
