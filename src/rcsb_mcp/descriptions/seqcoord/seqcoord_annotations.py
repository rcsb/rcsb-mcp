"""Argument descriptions for rcsb_seqcoord_annotations (see the package docstring for why). `fields` is in shared.py."""

__all__ = [
    "QUERY_ID_DOC",
    "FEATURE_TYPES_DOC",
]

QUERY_ID_DOC = (
    'A PDB polymer entity ("4HHB_1") or instance ("4HHB.A", RCSB chain id), computed models '
    "included. For a UniProt or NCBI id, find its PDB entities with rcsb_seqcoord_alignments first."
)

FEATURE_TYPES_DOC = (
    'Optional feature types to return, any of them (e.g. ["ACTIVE_SITE", "BINDING_SITE"]), named '
    "as in the `type` of returned features. Omit for every annotation; an answer too large to "
    "return is refused with the types the sequence has."
)
