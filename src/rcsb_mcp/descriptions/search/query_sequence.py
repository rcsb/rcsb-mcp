"""Argument descriptions for rcsb_query_sequence (see the package docstring for why). `sequence_type` is in shared.py."""

__all__ = [
    "SEQUENCE_DOC",
    "IDENTITY_CUTOFF_DOC",
    "EVALUE_CUTOFF_DOC",
]

SEQUENCE_DOC = "One-letter sequence; whitespace is ignored. FASTA headers must be removed."

IDENTITY_CUTOFF_DOC = (
    "Minimum fractional identity 0-1 (default 0.3). Raise toward 0.9 for close homologs, "
    "lower for remote ones."
)

EVALUE_CUTOFF_DOC = "Maximum E-value (default 1.0); lower is stricter."
