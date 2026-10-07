"""Argument descriptions for rcsb_find_go_terms (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "NAMESPACE_DOC",
    "LIMIT_DOC",
    "WITH_PDB_COUNTS_DOC",
]

QUERY_DOC = 'Free-text function / process / location, e.g. "kinase activity", "DNA repair".'

NAMESPACE_DOC = "Optional GO aspect to restrict to. Omit to search all three."

LIMIT_DOC = "Max GO terms to return."

WITH_PDB_COUNTS_DOC = (
    "If true (default), annotate each term with pdb_entry_count (PDB entries carrying it, via "
    "annotation_lineage.id)."
)
