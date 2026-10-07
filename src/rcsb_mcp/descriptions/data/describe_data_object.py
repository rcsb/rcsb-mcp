"""Argument descriptions for rcsb_describe_data_object (see the package docstring for why)."""

__all__ = [
    "OBJECT_KEY_DOC",
    "INTO_DOC",
    "QUERY_DOC",
    "MAX_DEPTH_DOC",
]

OBJECT_KEY_DOC = (
    "Which object to describe — the key matching the rcsb_get_* tool. OMIT it to "
    "search every object at once and be told which tool owns each match; that needs a "
    "`query` and cannot be combined with `into`. An empty result from a NAMED object "
    "means that object has no matching field — not that the field does not exist; "
    "re-run without object_key to search them all."
)

INTO_DOC = (
    'Optional dot-path of nested object field(s) to scope to, e.g. "rcsb_entry_info" '
    'or "polymer_entities.rcsb_polymer_entity". Scoping a search to a sub-tree is '
    'cheaper and more focused than flattening from the root, and needs an object_key. '
    'Browsing workflow: rcsb_describe_data_object("entries") -> spot a nested object '
    'such as "rcsb_entry_info" -> rcsb_describe_data_object("entries", '
    'into="rcsb_entry_info") to list its leaves.'
)

QUERY_DOC = (
    "Optional case-insensitive keyword, matched against each field's path (relative to "
    "the scope) and its description, e.g. \"resolution\", \"abstract\", \"organism\". A "
    "SEARCH ATTRIBUTE PATH works as the query too: every attribute from "
    "rcsb_list_pdb_search_attributes is also a Data API field, so pasting one in tells "
    "you which tool fetches the value you can filter on. Matches are ordered exact "
    "field name, then partial, then description-only."
)

MAX_DEPTH_DOC = (
    'How many levels to walk (1-6). Omit it: the default follows what you are doing — '
    '1 when browsing, 3 when searching, which is what it takes to reach '
    '"polymer_entities.rcsb_polymer_entity.pdbx_description". Set it only to go deeper '
    'still, or to cap a broad walk. Deeper is slower on a cold cache; prefer narrowing '
    'with `query` and `into`.'
)
