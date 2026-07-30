"""``SearchConfiguration`` — how a search runs, and the vocabulary it is built from.

Every ``rcsb_search_*`` tool takes only its own payload (query / sequence / value /
entry_id ...) plus one of these objects, on a single rule: the payload says WHAT to match,
this says everything else about how the search runs. That boundary is the RCSB Search API's
own — a request is a primary service terminal, plus optional attribute refinements, plus
``request_options``.

Everything the class is built from lives here with it, and that grouping is not arbitrary:
after the consolidation, ReturnType / Limit / Offset / LogicalOperator / SortDirection /
GroupBy / GroupByRanking are referenced by NOTHING in search.py except this model. The
per-modality vocabulary (SequenceType, ChemMatchType, Tolerance, ...) stays in search.py
with the tools that take it.

A LEAF as far as the package goes: imports only ``attribute_types``, so search.py can import
this without the two referring back to each other.

WRITING THE DOCSTRINGS IN THIS FILE. A pydantic model's docstring is AGENT-FACING: pydantic
emits it as the ``$def``'s ``description``, so it ships inside every tool schema that
references the model — 7x for SearchConfiguration, 7x for AttributeFilter. It is not a place
for notes to maintainers; those go in ``#`` comments or in this module docstring, neither of
which is emitted. Keep a class docstring to what an agent needs in order to fill the object:
what it is, and the CROSS-FIELD rules no single ``Field(description=...)`` can state.

Per-field descriptions are the primary documentation — they reach the model attached to the
parameter it is filling, and every rcsb_search_* tool inherits them by taking this object. So
a rule that belongs to one field goes ON that field rather than in a tool's docstring, where
it would apply to the one tool whose prose happens to mention it instead of all seven. The
trade is that field text is duplicated per tool: 783 tokens of descriptions cost 5,481 across
seven schemas, because MCP gives each tool an independent inputSchema with no cross-tool
``$defs`` sharing. Prefer precision over completeness here, and do not restate what an
adjacent field already says.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rcsb_mcp.attribute_types import TextOperator


ReturnType = Literal[
    "entry", "polymer_entity", "non_polymer_entity",
    "polymer_instance", "assembly", "mol_definition",
]
LogicalOperator = Literal["and", "or"]
SortDirection = Literal["asc", "desc"]
GroupBy = Literal["seqid_30", "seqid_50", "seqid_70", "seqid_90", "seqid_95", "uniprot"]
GroupByRanking = Literal[
    "resolution", "released_date", "entity_residue_count", "score", "coverage",
]

# Numeric bounds (Annotated so the parameter default stays on the signature).
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]


class AttributeFilter(BaseModel):
    # Deliberately one line: this ships x7, and the rest of what a caller needs — where to
    # find paths, how the conditions combine — is already on SearchConfiguration.attributes
    # and .logical_operator, which arrive in the same schema.
    """One structured attribute condition — a single `text`/`text_chem` terminal."""

    attribute: str = Field(
        description="Dotted RCSB attribute path, e.g. 'rcsb_entry_info.resolution_combined'."
    )
    operator: TextOperator = Field(
        description="Type-specific operator (see rcsb_list_pdb_search_attributes): strings use "
        "exact_match/in or contains_words/contains_phrase; numbers/dates use greater/"
        "greater_or_equal/less/less_or_equal/equals/range; any type supports exists."
    )
    value: str | int | float | list | dict | None = Field(
        default=None,
        description="Comparison value; omit for 'exists'. A list for 'in'; a "
        "{from,to,include_lower,include_upper} object for 'range'. A numeric string is "
        "coerced to a number for numeric operators; dates take an ISO-8601 string.",
    )
    negation: bool = Field(default=False, description="Invert the match (NOT).")
    case_sensitive: bool = Field(
        default=False, description="Match the value case-sensitively (default insensitive)."
    )


class SearchConfiguration(BaseModel):
    """How a search runs and what comes back — everything except WHAT you are matching on.

    Three rules span fields, so no one field can state them:
      * group_by requires return_type="polymer_entity".
      * group_by_ranking="coverage" is valid only with group_by="uniprot" (preferred there).
      * all_hits cannot be combined with offset, and ignores limit.
    """

    model_config = ConfigDict(extra="forbid")

    # --- refinement: narrows WHAT matches, alongside the tool's own payload -------
    attributes: list[AttributeFilter] | None = Field(
        default=None,
        description=(
            "Structured conditions combined with the tool's own query — AttributeFilter "
            "{attribute, operator, value, negation?, case_sensitive?}. REQUIRED by "
            "rcsb_search_by_attribute, where these conditions ARE the query; optional "
            "refinement everywhere else. NEVER invent, guess, or infer an attribute path: if "
            "you don't know one or its operators, call rcsb_list_pdb_search_attributes first. "
            "Operators are TYPE-SPECIFIC; a range value is {from, to, include_lower, "
            "include_upper}, bounds EXCLUSIVE unless the include flags are true. For a "
            "biological CONCEPT (disease, function, domain, enzyme, organism) resolve it to an "
            "ontology id with the matching rcsb_find_* tool and filter on that annotation "
            "instead of guessing a path. For ordinary constraints (resolution, organism, "
            "dates) an empty result is a valid answer: report it, don't switch to a "
            'keyword search. Example: [{"attribute": "exptl.method", "operator": '
            '"exact_match", "value": "X-RAY DIFFRACTION"}, {"attribute": '
            '"rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0}].'
        ),
    )
    logical_operator: LogicalOperator = Field(
        default="and",
        description=(
            "Combine the tool's own query with the attribute conditions. ALL conditions share "
            "this ONE operator — NESTED boolean groups are not supported."
        ),
    )
    chemical_attributes: bool = Field(
        default=False,
        description=(
            "Set True when `attributes` target chemical-component attributes (the text_chem "
            'service) rather than structure attributes; usually pair with '
            'return_type="mol_definition".'
        ),
    )

    # --- what comes back ----------------------------------------------------------
    return_type: ReturnType | None = Field(
        default=None,
        description=(
            "What to return — this fixes the SHAPE of every id in the response and which tool "
            'fetches its details: entry "4HHB" (rcsb_get_entries); polymer_entity "4HHB_1" '
            '(rcsb_get_polymer_entities); non_polymer_entity "4HHB_3" '
            '(rcsb_get_nonpolymer_entities); polymer_instance "4HHB.A", one chain '
            '(rcsb_get_polymer_entity_instances); assembly "4HHB-1" (rcsb_get_assemblies); '
            'mol_definition "HEM", a chemical component (rcsb_get_chem_comps). OMIT to get '
            "each search's natural unit — entry for keyword and attribute, polymer_entity for "
            "sequence and sequence-motif, mol_definition for chemical, assembly for structural "
            "motif, and for 3D-shape the unit matching the reference."
        ),
    )
    include_computed_models: bool = Field(
        default=False,
        description=(
            "Also search computed structure models (AlphaFold etc.). Honoured by keyword and "
            "attribute searches; the sequence, motif, structure and chemical services ignore "
            "it for now."
        ),
    )

    # --- paging -------------------------------------------------------------------
    limit: Limit = Field(default=10, description="Max number of hits to return (1-100).")
    offset: Offset = Field(
        default=0,
        description=(
            "Number of hits to skip, for paging; pass the response's next_offset back with "
            "the same query to fetch the next page."
        ),
    )
    all_hits: bool = Field(
        default=False,
        description=(
            'Return the COMPLETE result set in one call, for an explicit "ALL ..." request. '
            "Ignores limit and omits paging; can't be combined with offset (the Search API "
            "rejects pagination here); refused above 10000 hits — narrow, aggregate with "
            "`facets`, or page."
        ),
    )

    # --- ordering -----------------------------------------------------------------
    sort_by: str | None = Field(
        default=None,
        description=(
            "Attribute path to order the hits by; omit to sort by relevance score. Only "
            "SORTABLE attributes work: those listing exact_match (strings) or equals "
            "(numbers/dates) in rcsb_list_pdb_search_attributes; full-text-only attributes "
            '(e.g. struct.title) and return_type="mol_definition" are rejected.'
        ),
    )
    sort_direction: SortDirection = Field(
        default="asc", description="Applies only when sort_by is set."
    )

    # --- aggregation and clustering -------------------------------------------------
    facets: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Aggregation specs to return a breakdown / distribution instead of hits (see the "
            "faceting note in the rcsb_mcp_guide prompt for the spec)."
        ),
    )
    group_by: GroupBy | None = Field(
        default=None,
        description=(
            "Collapse redundant polymer hits into clusters, one representative each; requires "
            'return_type="polymer_entity" — see the grouping note in the rcsb_mcp_guide prompt.'
        ),
    )
    group_by_ranking: GroupByRanking | None = Field(
        default=None,
        description=(
            "Which member represents each group. `coverage` is valid only with "
            'group_by="uniprot", and is preferred there.'
        ),
    )


def _cfg(config: "SearchConfiguration | None", default_return_type: str | None) -> tuple:
    """Unpack a caller's configuration, applying THIS tool's return_type default.

    `return_type` is the one field whose default differs per tool (entry / polymer_entity /
    mol_definition / assembly), so SearchConfiguration deliberately defaults it to None and
    each tool supplies its own here. Giving the model a concrete default instead would make
    an omitted return_type indistinguishable from an explicit "entry", silently returning the
    wrong entity type from four of the seven searches.

    Returns (config, resolved_return_type); the config is a default instance when the caller
    passed none, so every call site can read `.limit` etc. unconditionally.
    """
    cfg = config or SearchConfiguration()
    return cfg, (cfg.return_type or default_return_type)
