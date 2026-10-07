"""Descriptions shared by several data tools (see the package docstring)."""

__all__ = [
    "FIELDS_DOC",
]

# Every rcsb_get_* tool takes the same `fields` argument. The wording is written once here
# with two blanks -- an example path and the Data API object -- which data.py fills per tool.
# The 16 hand-copied versions it replaces had drifted apart in form (rcsb_get_pubmed's example
# unquoted, no final period), and one example failed against the live API (rcsb_get_uniprot's
# `rcsb_uniprot_protein.name` is an object, so it needs a sub-field).
FIELDS_DOC = (
    'Optional GraphQL selection replacing the curated default (e.g. "{example}"); '
    'discover/verify paths with rcsb_describe_data_object("{object_key}").'
)
