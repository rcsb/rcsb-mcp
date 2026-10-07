"""Argument descriptions for rcsb_find_disease_terms (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "LIMIT_DOC",
    "WITH_PDB_COUNTS_DOC",
]

QUERY_DOC = 'Free-text disease / condition, e.g. "cystic fibrosis", "breast cancer".'

LIMIT_DOC = "Max MONDO terms to return."

WITH_PDB_COUNTS_DOC = (
    "If true (default), annotate each with pdb_entry_count (PDB entries carrying it, via "
    "annotation_lineage.id)."
)
