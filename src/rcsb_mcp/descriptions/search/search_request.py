"""Argument descriptions for rcsb_search_request (see the package docstring for why)."""

__all__ = [
    "QUERY_DOC",
    "RETURN_TYPE_DOC",
    "LIMIT_DOC",
    "OFFSET_DOC",
    "ALL_HITS_DOC",
    "INCLUDE_COMPUTED_DOC",
    "FACETS_DOC",
    "SORT_BY_DOC",
    "SORT_DIRECTION_DOC",
    "GROUP_BY_DOC",
    "GROUP_BY_RANKING_DOC",
]

QUERY_DOC = "The query document returned by an rcsb_query_* tool, passed through unchanged."

RETURN_TYPE_DOC = """\
What kind of identifier to return:
  Type               Description          Example    Data API tool
  entry              whole structure      "4HHB"     -> rcsb_get_entries
  polymer_entity     one molecule         "4HHB_1"   -> rcsb_get_polymer_entities
  non_polymer_entity ligand entity        "4HHB_3"   -> rcsb_get_nonpolymer_entities
  polymer_instance   one chain            "4HHB.A"   -> rcsb_get_polymer_entity_instances
  assembly           biological assembly  "4HHB-1"   -> rcsb_get_assemblies
  mol_definition     chemical component   "HEM"      -> rcsb_get_chem_comps
If conditions granularity is finer than entry (e.g. entity, instance, ...), an entry \
matches when EACH condition holds on SOME subunit — not necessarily the same one.
Omit it to use the default implied by the query:
  Query                 Return type
  rcsb_query_fulltext   -> entry
  rcsb_query_attribute  -> entry
  rcsb_query_sequence   -> polymer_entity
  rcsb_query_seqmotif   -> polymer_entity
  rcsb_query_structure  -> assembly (assembly_id in query) / polymer_instance (asym_id in query)
  rcsb_query_strucmotif -> assembly
  rcsb_query_chemical   -> mol_definition
Setting it CONVERTS the result — e.g. a ligand attribute filter with \
return_type="entry" gives the structures containing that ligand."""

LIMIT_DOC = "Max hits to return, 1-100 (default 10)."

OFFSET_DOC = (
    "Hits to skip, for paging; pass the response's next_offset back with the same query "
    "to fetch the next page."
)

ALL_HITS_DOC = (
    'Return the COMPLETE result set in one call, for an explicit "ALL ..." request. '
    "Ignores limit, cannot be combined with offset (the Search API rejects pagination "
    "here), and is refused above 10000 hits — narrow the query, aggregate with `facets`, "
    "or page instead. Ignored when `facets` is set."
)

INCLUDE_COMPUTED_DOC = (
    "Also search computed structure models (AlphaFold and similar), not just experimental "
    "structures."
)

FACETS_DOC = """\
Aggregation specs returning a BREAKDOWN instead of hits — use for "how many by X \
(e.g., experimental method)", "distribution of Y (e.g., EC numbers)", "which Z (e.g., \
organisms)" queries or to discover what your hits SHARE so you can re-search on it and \
explore other potential candidates. A terms facet on an attribute returns the values \
common to the result set, at any hit count. Those counts are within your hits only — a \
value's archive-wide count is a separate query, and it is what says whether the value is \
distinctive or generic.
Each is {name, aggregation_type, attribute} plus: `interval` for \
histogram/date_histogram, `ranges` for range/date_range, and an optional nested `facets` \
list. aggregation_type is one of terms, histogram, date_histogram, range, date_range, \
cardinality."""

SORT_BY_DOC = (
    "Attribute path to order hits by, replacing the default relevance order (each hit's "
    "score is still returned). A pure attribute filter is a boolean match whose hits "
    'otherwise come back in near-arbitrary order, so set this for "best resolution first", '
    '"newest first", and similar. Only SORTABLE attributes work: those listing exact_match '
    "(strings) or equals (numbers/dates) in rcsb_list_pdb_search_attributes; "
    'full-text-only attributes (e.g. struct.title) and return_type="mol_definition" are '
    "rejected."
)

SORT_DIRECTION_DOC = '"asc" (default) or "desc"; applies only when sort_by is set.'

GROUP_BY_DOC = (
    "Collapse redundant polymer_entity hits into clusters and return one representative "
    'each — requires return_type="polymer_entity". Sequence-identity clustering at '
    '30/50/70/90/95 percent ("seqid_30" ... "seqid_95"), or "uniprot" to group by '
    "matching UniProt accession."
)

GROUP_BY_RANKING_DOC = (
    'Which member represents each cluster: "resolution" (best first), "released_date" '
    '(newest first), "entity_residue_count" (longest deposited sequence first — expression '
    'tags and fusion partners count toward it), "coverage" (most of the UniProt sequence '
    'covered — "uniprot" grouping only, and preferred there, since it distinguishes '
    'distinct proteins from redundant entries), or "score". Note "score" is search '
    "relevance: it measures neither biological importance nor structure quality, so don't "
    "pick a cluster representative by it unless relevance is genuinely what you want ranked."
)
