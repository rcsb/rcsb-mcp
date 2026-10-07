"""Argument descriptions for rcsb_find_interpro_domains (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "ENTRY_TYPE_DOC",
    "LIMIT_DOC",
    "WITH_PDB_COUNTS_DOC",
]

QUERY_DOC = 'Free-text domain/family name, e.g. "SH2 domain", "immunoglobulin".'

ENTRY_TYPE_DOC = "Optional type filter. Omit to return all types."

LIMIT_DOC = "Max entries to return."

WITH_PDB_COUNTS_DOC = (
    "If true (default), annotate each entry with pdb_entry_count (PDB entries carrying it)."
)
