"""Argument descriptions for rcsb_find_enzyme_classes (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "LIMIT_DOC",
    "WITH_PDB_COUNTS_DOC",
]

QUERY_DOC = 'Free-text enzyme / reaction, e.g. "alcohol dehydrogenase", "protein kinase".'

LIMIT_DOC = "Max EC numbers to return."

WITH_PDB_COUNTS_DOC = (
    "If true (default), annotate each with pdb_entry_count (PDB entries carrying it, via "
    "rcsb_ec_lineage.id)."
)
