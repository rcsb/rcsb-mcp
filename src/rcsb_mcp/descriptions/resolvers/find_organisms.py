"""Argument descriptions for rcsb_find_organisms (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "LIMIT_DOC",
    "WITH_PDB_COUNTS_DOC",
]

QUERY_DOC = 'Free-text organism / clade / common name, e.g. "human", "mammals", "E. coli".'

LIMIT_DOC = "Max taxa to return."

WITH_PDB_COUNTS_DOC = (
    "If true (default), annotate each taxon with pdb_entry_count (PDB entries from it or any "
    "organism beneath it, via taxonomy_lineage.id) — this also disambiguates a species from "
    "its strains."
)
