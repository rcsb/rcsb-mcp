"""Argument descriptions for rcsb_query_seqmotif (see the package docstring for why). `sequence_type` is in shared.py."""

__all__ = [
    "PATTERN_DOC",
    "PATTERN_TYPE_DOC",
]

PATTERN_DOC = "The motif, written in the grammar named by pattern_type."

PATTERN_TYPE_DOC = (
    '"prosite" (default) for PROSITE syntax like "C-x(2,4)-C-x(3)-[LIVMFYWC]"; "regex" for a '
    'regular expression like "C..H[LIVF]"; "simple" for simple wildcards where X matches any '
    'residue (e.g. "NXS").'
)
