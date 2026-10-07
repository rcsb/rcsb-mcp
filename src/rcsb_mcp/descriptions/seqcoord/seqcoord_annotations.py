"""Argument descriptions for rcsb_seqcoord_annotations (see the package docstring for why). `fields` is in shared.py."""

__all__ = [
    "QUERY_ID_DOC",
    "REFERENCE_DOC",
    "SOURCES_DOC",
    "SEQ_RANGE_DOC",
    "FILTERS_DOC",
]

QUERY_ID_DOC = 'The sequence id, e.g. "4HHB_1" (PDB_ENTITY) or "P69905" (UNIPROT).'

REFERENCE_DOC = "Reference system query_id is given in."

SOURCES_DOC = "Annotation provenance — which source(s) to pull features from."

SEQ_RANGE_DOC = "Optional [begin, end] (1-based) to restrict the region."

FILTERS_DOC = (
    "Optional list of {field, operation, source?, values} filter dicts, where field is "
    "TARGET_ID or TYPE and operation is CONTAINS or EQUALS."
)
