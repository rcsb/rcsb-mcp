"""Argument descriptions for rcsb_seqcoord_alignments (see the package docstring for why). `fields` is in shared.py."""

__all__ = [
    "QUERY_ID_DOC",
    "FROM_REF_DOC",
    "TO_REF_DOC",
    "SEQ_RANGE_DOC",
]

QUERY_ID_DOC = (
    'The sequence id, in the from_ref system\'s format — UNIPROT "P69905", NCBI_PROTEIN '
    '"NP_000508", NCBI_GENOME "NC_000016", PDB_ENTITY "4HHB_1" (entry_entityNumber), '
    'PDB_INSTANCE "4HHB.A" (entry.asym_id). PDB ids must be ENTITY-level, never a bare '
    "entry: for a whole entry, first get its polymer entity ids (4HHB -> 4HHB_1, 4HHB_2) and "
    "query each one."
)

FROM_REF_DOC = "Reference system of query_id."

TO_REF_DOC = "Reference system to map onto."

SEQ_RANGE_DOC = "Optional [begin, end] (1-based) to restrict the query region."
