"""Argument descriptions for rcsb_describe_seqcoord_object (see the package docstring for why)."""

__all__ = [
    "OBJECT_KEY_DOC",
    "INTO_DOC",
    "QUERY_DOC",
    "MAX_DEPTH_DOC",
]

OBJECT_KEY_DOC = (
    'The root field to describe: "alignments" for rcsb_seqcoord_alignments, "annotations" '
    "for rcsb_seqcoord_annotations."
)

INTO_DOC = (
    'Optional dot-path of nested object field(s) to scope to, e.g. "target_alignments" or '
    '"features.feature_positions".'
)

QUERY_DOC = (
    "Optional case-insensitive keyword, matched against each field's path (relative to the "
    "scope) and its description."
)

MAX_DEPTH_DOC = (
    "How many levels to walk (1-6). Omit it: the default follows what you are doing — 1 when "
    "browsing, 3 when searching. The schema bottoms out at 3."
)
