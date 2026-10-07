"""RCSB Search API tools: discover PDB identifiers by keyword, structured attribute,
sequence similarity, chemistry, 3D shape, sequence motif, or residue geometry.

Self-contained like the sibling tool packages: the parameter type aliases (which the
schema turns into JSON-schema enums / numeric bounds), the AttributeFilter model, the
shared result/facet formatters, and the all_hits guard all live here. The tool
functions are module-level (so they stay directly unit-testable); a FastMCP server
attaches them with register_search_tools(mcp), the register-onto-mcp pattern. This
module imports nothing back from server.
"""

from __future__ import annotations

import difflib
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from rcsb_mcp import queries, query_doc
from rcsb_mcp.attribute_types import SearchAttribute, TextOperator
from rcsb_mcp.client import _post_search, _search_editor
from rcsb_mcp.tooling import READ_ONLY
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES
from rcsb_mcp.descriptions.search import (
    list_pdb_search_attributes,
    query_attribute,
    query_chemical,
    query_composer,
    query_fulltext,
    query_seqmotif,
    query_sequence,
    query_strucmotif,
    query_structure,
    search_request,
    shared,
)
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES


ReturnType = Literal[
    "entry", "polymer_entity", "non_polymer_entity",
    "polymer_instance", "assembly", "mol_definition",
]
# TextOperator / AttributeValueType / SearchAttribute live in rcsb_mcp.attribute_types
# so the catalog data modules can share them without an import cycle.
SequenceType = Literal["protein", "dna", "rna"]
ChemMatchType = Literal[
    "graph-exact", "graph-strict", "graph-relaxed", "graph-relaxed-stereo",
    "fingerprint-similarity", "sub-struct-graph-exact", "sub-struct-graph-strict",
    "sub-struct-graph-relaxed", "sub-struct-graph-relaxed-stereo",
]
DescriptorType = Literal["SMILES", "InChI"]
ChemQueryType = Literal["descriptor", "formula"]
SeqmotifPatternType = Literal["simple", "prosite", "regex"]
AtomPairingScheme = Literal["ALL", "BACKBONE", "SIDE_CHAIN", "PSEUDO_ATOMS"]
MotifPruningStrategy = Literal["NONE", "KRUSKAL"]
LogicalOperator = Literal["and", "or"]
SortDirection = Literal["asc", "desc"]
GroupBy = Literal["seqid_30", "seqid_50", "seqid_70", "seqid_90", "seqid_95", "uniprot"]
GroupByRanking = Literal[
    "resolution", "released_date", "entity_residue_count", "score", "coverage",
]
AttributeSchema = Literal["structure", "chemical"]


# Numeric bounds (Annotated so the parameter default stays on the signature).
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]
Tolerance = Annotated[int, Field(ge=0, le=3)]


# `extra="forbid"` below, because the tool surface has TWO things called an operator:
# this model's `operator` (the per-condition COMPARISON — exact_match, in, less) and the
# tool's `logical_operator` (the ONE boolean joining every condition, a sibling of the
# `attributes` array). Under pydantic's default an unknown key is dropped in SILENCE, so a
# caller conflating them and writing `logical_operator` in here got "and" while having
# asked for "or" — a different answer, no error, nothing to notice. It now raises.
#
# This note is a COMMENT, not part of the docstring: pydantic ships a model's docstring
# into the JSON schema as `description`, so putting it there billed every caller 134
# tokens on every call to explain an internal decision. The class docstring stays short.
class AttributeFilter(BaseModel):
    # This class owns the validation contract only. Its model-facing text -- this docstring
    # (the schema's $defs description) and every field description -- lives in
    # descriptions/search/query_attribute.py, with the rest of what the model reads about the tool.
    __doc__ = query_attribute.FILTER_DOC

    model_config = {"extra": "forbid"}

    attribute: str = Field(description=query_attribute.FILTER_ATTRIBUTE_DOC)
    operator: TextOperator = Field(description=query_attribute.FILTER_OPERATOR_DOC)
    value: str | int | float | list | dict | None = Field(
        default=None, description=query_attribute.FILTER_VALUE_DOC
    )
    negation: bool = Field(default=False, description=query_attribute.FILTER_NEGATION_DOC)
    case_sensitive: bool = Field(
        default=False, description=query_attribute.FILTER_CASE_SENSITIVE_DOC
    )


def _filter_dicts(attributes: list[AttributeFilter] | None) -> list[dict[str, Any]] | None:
    """Convert typed AttributeFilter inputs into the plain dicts the builders expect."""
    return [f.model_dump() for f in attributes] if attributes else None


# Hard ceiling for all_hits searches: above this many matches the tool refuses and
# steers to facets/paging, so a broad query can't dump a huge id list into context.
ALL_HITS_MAX = 10000


# Attribute catalogs by schema name (see rcsb_list_pdb_search_attributes).
ATTRIBUTE_CATALOGS = {"structure": SEARCH_ATTRIBUTES, "chemical": CHEMICAL_SEARCH_ATTRIBUTES}

# --------------------------------------------------------------------------- #
# Local attribute validation
#
# Agents routinely GUESS attribute paths from naming conventions (e.g.
# `...nonpolymer_entity_container_identifiers.comp_id` instead of the real
# `...nonpolymer_comp_id`) — the prompt tells them not to, but pattern-matching wins.
# The path they invent is usually absent from the schema entirely, yet the Search API
# reports it as a CAPABILITY limit ("aggregation is not allowed on the attribute"),
# which reads as "exists but not aggregatable" and invites a work-around instead of a
# correction — costing several round trips. So validate here, locally, against the
# authoritative catalog (the exact set rcsb_list_pdb_search_attributes serves): a path
# not in it is not searchable, so this only rejects what the API would reject too, but
# fails FAST with a "did you mean" that steers straight to the right path.
# --------------------------------------------------------------------------- #
_ATTR_INDEX: dict[str, dict[str, SearchAttribute]] = {
    schema: {a["attribute"]: a for a in catalog} for schema, catalog in ATTRIBUTE_CATALOGS.items()
}

# `score` is the API's reserved default relevance sort — a real sort_by value, not a catalog
# attribute; exempt it (and any future reserved token) from attribute-path validation. (The
# `in`-on-numeric gap the catalog once had is now corrected in the catalog DATA itself — the
# generator maps `in` onto numeric/date attributes — so no operator special-case is needed.)
_RESERVED_SORT = frozenset({"score"})


def _check_attribute(path: str, schema: str) -> SearchAttribute:
    """Return the catalog record for `path`, or raise ValueError naming close matches."""
    record = _ATTR_INDEX[schema].get(path)
    if record is not None:
        return record
    close = difflib.get_close_matches(path, _ATTR_INDEX[schema], n=3, cutoff=0.6)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    schema_arg = ', schema="chemical"' if schema == "chemical" else ""
    raise ValueError(
        f"'{path}' is not a searchable {schema} attribute. Find the exact path with "
        f'rcsb_list_pdb_search_attributes(query="<keyword>"{schema_arg}) — do not guess it.{hint}'
    )


def _check_operator(record: SearchAttribute, operator: str) -> None:
    """Raise ValueError if `operator` isn't one this attribute supports."""
    if operator not in record["operators"]:
        raise ValueError(
            f"operator '{operator}' is not valid for attribute '{record['attribute']}' "
            f"(type {record['type']}); valid operators: {', '.join(record['operators'])}."
        )


# Operators that compare a value against the attribute's own vocabulary. `contains_words`
# and `contains_phrase` are excluded on purpose — those match text WITHIN a value, so a
# fragment is a legitimate query, not a mistake. `exists` carries no value at all.
_ENUM_CHECKED_OPERATORS = frozenset({"exact_match", "in", "equals"})


def _check_value(record: SearchAttribute, operator: str, value: Any, case_sensitive: bool) -> None:
    """Reject a value the attribute does not allow, when its vocabulary is published.

    This is the only part of a filter that used to go unchecked, and the only one whose
    failure is SILENT. A bad path or operator is refused outright; a bad VALUE builds a
    perfectly legal query that the Search API answers with zero hits — and an empty result
    on an attribute filter is a legitimate answer the tools explicitly tell the agent to
    report rather than work around. So `exptl.method="cryo-EM"` does not error: it reports
    that the PDB holds no cryo-EM structures. It holds 35,660.

    Comparison is case-INSENSITIVE by default because the API is; when the caller asked for
    `case_sensitive`, the exact spelling is required, since anything else is another silent
    zero. Non-string values (numeric or boolean enums) are compared by their string form so
    one path handles every type.
    """
    allowed = record.get("enum")
    if not allowed or operator not in _ENUM_CHECKED_OPERATORS:
        return
    # `in` takes a list of alternatives; every one of them has to be real.
    values = value if (operator == "in" and isinstance(value, list)) else [value]
    by_lower = {str(a).lower(): a for a in allowed}
    for v in values:
        if v is None:
            continue
        canonical = by_lower.get(str(v).lower())
        if canonical is None:
            close = difflib.get_close_matches(str(v), [str(a) for a in allowed], n=3, cutoff=0.4)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            raise ValueError(
                f"'{v}' is not a valid value for '{record['attribute']}'. Allowed values: "
                f"{', '.join(repr(str(a)) for a in allowed)}.{hint}"
            )
        if case_sensitive and str(v) != str(canonical):
            raise ValueError(
                f"'{v}' is not spelled as '{record['attribute']}' publishes it and you asked "
                f"for a case-sensitive match, which would return nothing. Use {canonical!r}."
            )


def _check_facet(facet: Any, schema: str) -> None:
    """Validate a facet's aggregation attribute, recursing into nested sub-facets."""
    if not isinstance(facet, dict):
        return
    attr = facet.get("attribute")
    if isinstance(attr, str) and attr:
        _check_attribute(attr, schema)
    for sub in facet.get("facets") or []:
        _check_facet(sub, schema)


def _validate_query_attributes(
    *,
    chemical: bool = False,
    attributes: list[AttributeFilter] | None = None,
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
) -> None:
    """Validate every agent-supplied attribute path (and each condition's operator) before
    building the query, so a guessed path/operator raises a clear ValueError here rather
    than a misleading Search-API error several calls later."""
    schema = "chemical" if chemical else "structure"
    for f in attributes or []:
        record = _check_attribute(f.attribute, schema)
        _check_operator(record, f.operator)
        _check_value(record, f.operator, f.value, f.case_sensitive)
    for facet in facets or []:
        _check_facet(facet, schema)
    if sort_by and sort_by not in _RESERVED_SORT:
        _check_attribute(sort_by, schema)


# return_type -> the Data API tool that takes those identifiers.
#
# Choosing return_type is the one search decision with no local failure signal: a wrong
# choice still succeeds and still returns plausible identifiers, just of the wrong KIND,
# and the mistake only surfaces later when a rcsb_get_* tool rejects them. The always-on
# surface can only describe the choice in advance (rcsb_search_request's `return_type`
# arg does); this states what actually came back, at the moment the agent is holding the
# ids and picking the next call. It costs nothing until a search runs.
RETURN_TYPE_FETCH_TOOL: dict[str, str] = {
    "entry": "rcsb_get_entries",
    "polymer_entity": "rcsb_get_polymer_entities",
    "non_polymer_entity": "rcsb_get_nonpolymer_entities",
    "polymer_instance": "rcsb_get_polymer_entity_instances",
    "assembly": "rcsb_get_assemblies",
    "mol_definition": "rcsb_get_chem_comps",
}


def _format(
    raw: dict[str, Any],
    body: dict[str, Any] | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    hits = [
        {"id": r["identifier"], "score": round(r.get("score", 0.0), 3)}
        for r in raw.get("result_set", [])
    ]
    total = raw.get("total_count", 0)
    result: dict[str, Any] = {"total_count": total, "returned": len(hits)}
    # With group_by the API keeps total_count as the UNGROUPED hit count and reports the
    # number of groups separately -- 2,092 SH2-domain entities collapse to 159 UniProt
    # groups. Surfacing it matters twice over: the caller cannot otherwise see what the
    # grouping achieved, and paging against 2,092 never terminates. At offset 200 the old
    # code returned 0 hits with has_more=True and next_offset=200, i.e. an agent following
    # the documented paging protocol loops on the same offset forever.
    group_count = raw.get("group_by_count")
    if group_count is not None:
        result["group_count"] = group_count
        total = group_count
    rt = (body or {}).get("return_type")
    if rt:
        result["result_type"] = rt
        if rt in RETURN_TYPE_FETCH_TOOL:
            result["fetch_with"] = RETURN_TYPE_FETCH_TOOL[rt]
    if offset is not None:
        # Paging metadata: a single typed-search page is capped at 100 hits, so
        # callers step `offset` forward by `next_offset` to fetch the next page.
        has_more = offset + len(hits) < total
        result["offset"] = offset
        result["has_more"] = has_more
        result["next_offset"] = offset + len(hits) if has_more else None
    result["hits"] = hits
    if body is not None:
        result["editor"] = _search_editor(body)
    return result


async def _guard_all_hits(body: dict[str, Any], offset: int = 0) -> None:
    """Validate an all_hits search before issuing it.

    all_hits returns the COMPLETE set via return_all_hits, which the Search API
    forbids combining with pagination — so reject a non-zero offset up front. Then
    pre-count the query (cheap; return_counts only) so a broad keyword/attribute query
    can't return a massive id list that would swamp the agent's context. Raises
    ValueError with an actionable next step.
    """
    if offset:
        raise ValueError(
            "all_hits returns the complete result set and can't be combined with offset "
            "paging (the Search API rejects it). Drop offset, or page with all_hits=False."
        )
    count_body = {
        "query": body["query"],
        "return_type": body["return_type"],
        "request_options": {
            "return_counts": True,
            "results_content_type": body["request_options"].get(
                "results_content_type", ["experimental"]
            ),
        },
    }
    total = (await _post_search(count_body)).get("total_count", 0)
    if total > ALL_HITS_MAX:
        raise ValueError(
            f"all_hits would return {total} hits, above the {ALL_HITS_MAX} cap. "
            "Narrow the query (add filters), aggregate by passing `facets`, or "
            "page through results with limit + offset."
        )


def _format_facet(facet: dict[str, Any]) -> dict[str, Any]:
    """Normalize one facet from a search response (bucket list or single metric)."""
    if "buckets" in facet:
        buckets = []
        for b in facet.get("buckets") or []:
            bucket = {"label": b.get("label"), "population": b.get("population")}
            if b.get("facets"):  # nested sub-facets
                bucket["facets"] = [_format_facet(f) for f in b["facets"]]
            buckets.append(bucket)
        return {"name": facet.get("name"), "buckets": buckets}
    # cardinality / single-value metric facet
    return {"name": facet.get("name"), "value": facet.get("value")}


def _format_facets(raw: dict[str, Any], body: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "total_count": raw.get("total_count", 0),
        "facets": [_format_facet(f) for f in raw.get("facets", [])],
    }
    if body is not None:
        result["editor"] = _search_editor(body)
    return result


# --------------------------------------------------------------------------- #
# Layered search: rcsb_query_* build, rcsb_query_composer joins, rcsb_search_request runs
#
# Each rcsb_query_* tool owns ONE service's payload and returns a query document. The
# result-shaping envelope (return_type, paging, sorting, grouping, faceting) lives once,
# on rcsb_search_request, instead of being repeated on every search tool -- which is
# where most of this layer's token saving comes from.
#
# The envelope stays FLAT rather than nested in a config object: MCP gives every tool an
# independent inputSchema with no cross-tool $defs sharing, so a nested sub-model costs
# more than the parameters it wraps once there is only one tool carrying them.
# --------------------------------------------------------------------------- #


class QueryDocument(BaseModel):
    """A query from an rcsb_query_* tool. Pass it through exactly as returned; to change
    the query, call that tool again rather than editing this."""

    # No per-field descriptions: this $defs block is emitted into both rcsb_query_composer
    # and rcsb_search_request, so anything written here costs twice, and the tool docstrings
    # already say what the pair is and how to handle it.
    query: dict[str, Any]
    digest: str = Field(description="A digest of the query used for validation")


def _doc(node: dict[str, Any]) -> dict[str, Any]:
    """Sign a freshly built node — the shared tail of every rcsb_query_* tool."""
    return query_doc.sign(node)


def _node(doc: QueryDocument | dict[str, Any]) -> dict[str, Any]:
    """Verify an incoming query document and return its node."""
    return query_doc.verify(doc if isinstance(doc, dict) else doc.model_dump())


def _compose(nodes: list[dict[str, Any]], logical_operator: str) -> dict[str, Any]:
    """Join nodes. Exists so rcsb_query_composer's parameter can be called `queries`
    (the name the agent should see) without shadowing the `queries` module."""
    return queries.group_node(nodes, logical_operator)


async def rcsb_query_fulltext(
    query: Annotated[str, Field(description=query_fulltext.QUERY_DOC)],
) -> dict[str, Any]:
    """Build a FREE-TEXT keyword query (e.g. "CRISPR Cas9", "hemoglobin").

    Best for broad or exploratory lookups. When a request resolves to a clear attribute
    and value, prefer rcsb_query_attribute — more precise, and it avoids spurious keyword
    matches. BEFORE keyword-searching a biological CONCEPT (disease/function/domain/
    enzyme/organism), resolve it to an ontology id with the matching rcsb_find_* tool and
    filter on the annotation instead; fall back to keywords only if that yields nothing.

    Matching spans many text attributes beyond the title — abstracts, keywords, synonyms,
    author names — so judge each hit yourself: a high `score` is text-relevance, NOT
    biological importance; never tell the user one hit is better than another because its
    score is higher. For evidence on a hit, rcsb_get_entries returns its title and, for
    many entries, a PubMed abstract (pubmed.rcsb_pubmed_abstract_text). Broader, synonym,
    or differently-worded terms for the same concept may produce different results.

    Returns:
        A query document — pass it to rcsb_search_request to run it, or to
        rcsb_query_composer to combine it with other queries first.
    """
    return _doc(queries.fulltext_node(query))


async def rcsb_query_attribute(
    attributes: Annotated[list[AttributeFilter], Field(description=query_attribute.ATTRIBUTES_DOC)],
    logical_operator: Annotated[
        LogicalOperator, Field(description=query_attribute.LOGICAL_OPERATOR_DOC)
    ] = "and",
    chemical_attributes: Annotated[
        bool, Field(description=query_attribute.CHEMICAL_ATTRIBUTES_DOC)
    ] = False,
) -> dict[str, Any]:
    """Build a STRUCTURED query from attribute conditions — the precise alternative to
    keyword search, and preferred whenever a request resolves to clear attribute(s) and
    value(s). NEVER invent, guess, or infer an attribute path: call
    rcsb_list_pdb_search_attributes first if you don't know it or its operators.

    For a biological concept, resolve it to an ontology id with the matching rcsb_find_*
    tool and filter on that annotation. If a resolver returns no usable id, or a concept
    filter yields no hits, fall back to rcsb_query_fulltext for the concept. For ordinary
    constraints — resolution, organism, dates — an empty result is a valid answer: report
    it, don't keyword-search instead.

    An attribute path also works as the `query` for rcsb_describe_data_object: every attribute
    here is also a Data API field, so pasting one in tells you which rcsb_get_* tool fetches
    the value.

    Example ("human X-ray structures better than 2 A"):
        attributes=[
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "exptl.method", "operator": "exact_match", "value": "X-RAY DIFFRACTION"},
            {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0},
        ]

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
        Note the per-hit `score` of a pure attribute filter is near-uniform and carries
        NO biological meaning; don't rank hits by it.
    """
    _validate_query_attributes(chemical=chemical_attributes, attributes=attributes)
    return _doc(
        queries.attribute_node(_filter_dicts(attributes), logical_operator, chemical_attributes)
    )


async def rcsb_query_sequence(
    sequence: Annotated[str, Field(description=query_sequence.SEQUENCE_DOC)],
    sequence_type: Annotated[SequenceType, Field(description=shared.SEQUENCE_TYPE_DOC)] = "protein",
    identity_cutoff: Annotated[
        float, Field(ge=0.0, le=1.0, description=query_sequence.IDENTITY_CUTOFF_DOC)
    ] = 0.3,
    evalue_cutoff: Annotated[
        float, Field(ge=0.0, description=query_sequence.EVALUE_CUTOFF_DOC)
    ] = 1.0,
) -> dict[str, Any]:
    """Build a SEQUENCE-SIMILARITY query (MMseqs2, BLAST-like) from a raw sequence.

    Use when you have actual residues to match. For a short motif or pattern use
    rcsb_query_seqmotif; for a named protein use rcsb_query_fulltext or a resolver.

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
    """
    return _doc(queries.sequence_node(sequence, sequence_type, identity_cutoff, evalue_cutoff))


async def rcsb_query_chemical(
    value: Annotated[str, Field(description=query_chemical.VALUE_DOC)],
    query_type: Annotated[
        ChemQueryType, Field(description=query_chemical.QUERY_TYPE_DOC)
    ] = "descriptor",
    descriptor_type: Annotated[
        DescriptorType, Field(description=query_chemical.DESCRIPTOR_TYPE_DOC)
    ] = "SMILES",
    match_type: Annotated[
        ChemMatchType, Field(description=query_chemical.MATCH_TYPE_DOC)
    ] = "graph-relaxed",
    match_subset: Annotated[bool, Field(description=query_chemical.MATCH_SUBSET_DOC)] = False,
) -> dict[str, Any]:
    """Build a CHEMICAL query from a SMILES/InChI descriptor or a molecular formula.

    Use for ligand and small-molecule questions where you have the chemistry itself. To
    find a ligand by NAME, use rcsb_query_fulltext or filter on a chemical attribute.

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
    """
    return _doc(queries.chemical_node(value, query_type, descriptor_type, match_type, match_subset))


async def rcsb_query_structure(
    entry_id: Annotated[str, Field(description=query_structure.ENTRY_ID_DOC)],
    assembly_id: Annotated[str | None, Field(description=query_structure.ASSEMBLY_ID_DOC)] = None,
    asym_id: Annotated[str | None, Field(description=query_structure.ASYM_ID_DOC)] = None,
) -> dict[str, Any]:
    """Build a 3D SHAPE-SIMILARITY query against an existing PDB structure.

    Whole-shape similarity — use it for "structures shaped like X" / "same fold as X".
    For a geometric arrangement of specific residues use rcsb_query_strucmotif; for
    sequence similarity use rcsb_query_sequence.

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
    """
    return _doc(queries.structure_node(entry_id, assembly_id, asym_id))


async def rcsb_query_seqmotif(
    pattern: Annotated[str, Field(description=query_seqmotif.PATTERN_DOC)],
    pattern_type: Annotated[
        SeqmotifPatternType, Field(description=query_seqmotif.PATTERN_TYPE_DOC)
    ] = "prosite",
    sequence_type: Annotated[SequenceType, Field(description=shared.SEQUENCE_TYPE_DOC)] = "protein",
) -> dict[str, Any]:
    """Build a SHORT SEQUENCE-MOTIF query — a pattern, not a full sequence.

    Use for active-site signatures, N-glycosylation sequons, zinc fingers, and similar
    short patterns. For a whole sequence use rcsb_query_sequence; for a 3D arrangement of
    residues use rcsb_query_strucmotif.

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
    """
    return _doc(queries.seqmotif_node(pattern, pattern_type, sequence_type))


async def rcsb_query_strucmotif(
    entry_id: Annotated[str, Field(description=query_strucmotif.ENTRY_ID_DOC)],
    residue_ids: Annotated[
        list[dict[str, Any]], Field(description=query_strucmotif.RESIDUE_IDS_DOC)
    ],
    backbone_distance_tolerance: Annotated[
        Tolerance, Field(description=query_strucmotif.BACKBONE_DISTANCE_TOLERANCE_DOC)
    ] = 1,
    side_chain_distance_tolerance: Annotated[
        Tolerance, Field(description=query_strucmotif.SIDE_CHAIN_DISTANCE_TOLERANCE_DOC)
    ] = 1,
    angle_tolerance: Annotated[
        Tolerance, Field(description=query_strucmotif.ANGLE_TOLERANCE_DOC)
    ] = 1,
    rmsd_cutoff: Annotated[
        float, Field(ge=0.0, description=query_strucmotif.RMSD_CUTOFF_DOC)
    ] = 2.0,
    atom_pairing_scheme: Annotated[
        AtomPairingScheme, Field(description=query_strucmotif.ATOM_PAIRING_SCHEME_DOC)
    ] = "SIDE_CHAIN",
    motif_pruning_strategy: Annotated[
        MotifPruningStrategy, Field(description=query_strucmotif.MOTIF_PRUNING_STRATEGY_DOC)
    ] = "KRUSKAL",
    exchanges: Annotated[
        list[dict[str, Any]] | None, Field(description=query_strucmotif.EXCHANGES_DOC)
    ] = None,
) -> dict[str, Any]:
    """Build a 3D STRUCTURAL-MOTIF query — a geometric arrangement of specific residues.

    Geometry-based, and different from rcsb_query_structure (whole-shape similarity) and
    rcsb_query_seqmotif (sequence pattern). Use it for catalytic triads, binding sites,
    metal-coordination geometries, and similar.

    Returns:
        A query document — pass it to rcsb_search_request, or to rcsb_query_composer.
    """
    return _doc(
        queries.strucmotif_node(
            entry_id, residue_ids, backbone_distance_tolerance,
            side_chain_distance_tolerance, angle_tolerance, rmsd_cutoff,
            atom_pairing_scheme, motif_pruning_strategy, exchanges,
        )
    )


async def rcsb_query_composer(
    queries: Annotated[
        list[QueryDocument], Field(min_length=2, description=query_composer.QUERIES_DOC)
    ],
    logical_operator: Annotated[
        LogicalOperator, Field(description=query_composer.LOGICAL_OPERATOR_DOC)
    ] = "and",
) -> dict[str, Any]:
    """Combine query documents with one AND/OR — call repeatedly to nest.

    You do NOT need this for conditions that share a single operator: several attribute
    conditions ANDed together are one rcsb_query_attribute call, and a list of
    alternatives for one attribute is better expressed with the `in` operator than with
    OR. Reach for the composer when a query needs BOTH operators, or mixes services:

      * (human OR mouse) AND resolution < 2 A -> build the OR group with
        rcsb_query_attribute(logical_operator="or"), build the resolution condition, then
        compose the two with "and".
      * sequence-similar to X AND containing ligand Y -> compose rcsb_query_sequence with
        rcsb_query_attribute.

    Nest by feeding a composed document straight back in as one of `queries`. Groups that
    share this call's operator are folded in rather than nested, so repeated composition
    stays flat and readable.

    Returns:
        A query document — pass it to rcsb_search_request, or back into this tool.
        A query mixing two services has no single meaningful relevance ranking, so hits
        come back in the API's default order; set `sort_by` on rcsb_search_request if the
        order matters.
    """
    return _doc(_compose([_node(q) for q in queries], logical_operator))


async def rcsb_search_request(
    query: Annotated[QueryDocument, Field(description=search_request.QUERY_DOC)],
    return_type: Annotated[ReturnType | None, Field(description=search_request.RETURN_TYPE_DOC)] = None,
    limit: Annotated[Limit, Field(description=search_request.LIMIT_DOC)] = 10,
    offset: Annotated[Offset, Field(description=search_request.OFFSET_DOC)] = 0,
    all_hits: Annotated[bool, Field(description=search_request.ALL_HITS_DOC)] = False,
    include_computed_models: Annotated[bool, Field(description=search_request.INCLUDE_COMPUTED_DOC)] = False,
    facets: Annotated[list[dict[str, Any]] | None, Field(description=search_request.FACETS_DOC)] = None,
    sort_by: Annotated[str | None, Field(description=search_request.SORT_BY_DOC)] = None,
    sort_direction: Annotated[SortDirection, Field(description=search_request.SORT_DIRECTION_DOC)] = "asc",
    group_by: Annotated[GroupBy | None, Field(description=search_request.GROUP_BY_DOC)] = None,
    group_by_ranking: Annotated[
        GroupByRanking | None, Field(description=search_request.GROUP_BY_RANKING_DOC)
    ] = None,
) -> dict[str, Any]:
    """RUN a query built by the rcsb_query_* tools and return matching PDB identifiers.

    Every search ends here: build with rcsb_query_fulltext / rcsb_query_attribute /
    rcsb_query_sequence / rcsb_query_chemical / rcsb_query_structure /
    rcsb_query_seqmotif / rcsb_query_strucmotif, optionally join with
    rcsb_query_composer, then execute with this tool. Nothing is searched until you
    call it — a query document on its own is not a result.

    Results are IDENTIFIERS only. Batch them into rcsb_get_entries, or the rcsb_get_*
    tool matching `return_type`, to get metadata.

    Returns:
        {total_count, returned, result_type, fetch_with, offset, has_more, next_offset,
        hits:[{id, score}], editor} — `result_type` is the kind of identifier that came
        back and `fetch_with` names the rcsb_get_* tool that takes it, so check those
        before batching the ids onward. `editor` opens the query in the RCSB search UI.
        With `all_hits` the paging fields are omitted; with `facets` returns
        {total_count, facets, editor} instead of hits.

        A `notes` list appears only when the results need a caveat; read it before
        describing the hits or treating them as complete.
    """
    node = _node(query)
    _validate_query_attributes(
        chemical=queries.uses_chemical_attributes(node), facets=facets, sort_by=sort_by
    )
    body = queries.build_search_request(
        node,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        include_computed=include_computed_models,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
        facets=facets,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    result = (_format_facets(raw, body) if facets
              else _format(raw, body, None if all_hits else offset))
    # Where this query was intersected more loosely than it reads. Absent on the queries
    # that are fine, which is most of them -- see queries.intersection_notes.
    notes = queries.intersection_notes(node, body["return_type"])
    # Thin answers from a wording-dependent query. Separate concern from the above: that one
    # is about a query being looser than it reads, this one about it being narrower.
    if not facets:
        thin = queries.small_result_note(node, result.get("total_count", 0))
        if thin:
            notes = [*notes, thin]
    if notes:
        result["notes"] = notes
    return result




class _AttributeListResult(BaseModel):
    """Envelope for rcsb_list_pdb_search_attributes.

    Built through pydantic so a malformed result cannot be emitted, then returned as a plain
    dict: the tool annotates `-> dict[str, Any]`, which keeps the generated outputSchema at
    ~18 tokens instead of ~110 for a typed one. The value is in `match_mode` + `note`, which
    cost tokens only on the calls that need them.
    """

    count: int
    match_mode: Literal["exact", "none", "all"]
    attributes: list[SearchAttribute]
    note: str | None = None


async def rcsb_list_pdb_search_attributes(
    query: Annotated[str | None, Field(description=list_pdb_search_attributes.QUERY_DOC)] = None,
    schema: Annotated[
        AttributeSchema, Field(description=list_pdb_search_attributes.SCHEMA_DOC)
    ] = "structure",
) -> dict[str, Any]:
    """Discover the RCSB PDB Search schema: attribute paths, value types, and operators.

    Call this FIRST when a request resolves to a clear attribute and value but you don't know
    the exact path; pick the attribute here, build the condition with `rcsb_query_attribute`,
    then execute with `rcsb_search_request`.

    Returns:
        {count, match_mode, attributes, note?}. `attributes` holds {attribute, type, operators,
        description, enum?, nested_group?} records — the RCSB/PDB attribute path (e.g.
        "rcsb_entry_info.resolution_combined"), its value type (string/number/integer/date), the
        operators it supports (exact_match, greater, range, exists, ...), and a human-readable
        description. `enum` appears on the ~15% of attributes that accept only a FIXED SET of
        values (e.g. exptl.method); when it does, use one of those values verbatim — anything
        else is rejected by rcsb_query_attribute. `nested_group` appears on the ~22% stored in NESTED DOCUMENTS —
        an entry has many citations, an entity many binding affinities — and its value is the
        container path. For these, grouping selects the semantics: conditions sharing a
        nested_group built in ONE rcsb_query_attribute call with nothing else in it must hold
        on the SAME record; in separate calls each is matched independently. Group the ones
        that describe one record, leave the rest apart. The value is NOT the attribute's first
        path segment for all of them, so read it rather than deriving it.
        `match_mode` is "exact" (the query matched), "none" (nothing matched — read
        `note`, the query shape is the usual cause), or "all" (query omitted, whole catalog).
    """
    try:
        catalog = ATTRIBUTE_CATALOGS[schema]
    except KeyError:
        raise ValueError(f'schema must be one of {sorted(ATTRIBUTE_CATALOGS)}') from None

    if not query or not query.strip():
        return _AttributeListResult(
            count=len(catalog), match_mode="all", attributes=catalog,
            note=(f"Full {schema} catalog ({len(catalog)} attributes) — large. Pass a `query` "
                  "keyword to filter it down."),
        ).model_dump(exclude_none=True)

    raw = query.strip()
    q = raw.lower()
    hits = [
        a for a in catalog
        if q in a["attribute"].lower() or q in (a.get("description") or "").lower()
    ]
    if hits:
        return _AttributeListResult(
            count=len(hits), match_mode="exact", attributes=hits,
        ).model_dump(exclude_none=True)

    # Nothing matched. Say WHY rather than asserting the attribute doesn't exist — a multi-word
    # query is the common cause and is recoverable, but a bare empty result reads as "the PDB
    # has no such attribute" and sends the model off to guess a path or fall back to full text.
    if len(raw.split()) > 1:
        note = (f'No attribute path or description contains the exact phrase "{raw}". This '
                "filter is a literal substring match, so retry with a single keyword from it "
                '(e.g. "comp_id" rather than "nonpolymer comp_id").')
    else:
        note = (f'No attribute path or description contains "{raw}". Retry with a shorter or '
                "more general keyword, or omit `query` to browse the catalog.")
    if schema == "structure":
        note += ' If the property describes a chemical component itself, try schema="chemical".'
    return _AttributeListResult(
        count=0, match_mode="none", attributes=[], note=note,
    ).model_dump(exclude_none=True)


# rcsb_search_* are the discovery tools; register_search_tools wires each onto the
# passed FastMCP instance (equivalent to the @mcp.tool decorator, but the functions
# stay importable/testable on their own). Original tool order is preserved.
_SEARCH_TOOLS = (
    # Layer 1: build one query node each.
    rcsb_query_fulltext,
    rcsb_list_pdb_search_attributes,
    rcsb_query_attribute,
    rcsb_query_sequence,
    rcsb_query_chemical,
    rcsb_query_structure,
    rcsb_query_seqmotif,
    rcsb_query_strucmotif,
    # Layer 2: join nodes (only needed for nesting or mixed services).
    rcsb_query_composer,
    # Layer 3: apply the envelope and execute.
    rcsb_search_request,
)


def register_search_tools(mcp) -> None:
    """Attach the RCSB Search API tools (rcsb_query_* / rcsb_search_request) to a server.

    The superseded flat rcsb_search_* names are gone: they were kept registered-but-unlisted
    for a deprecation window, and that window is closed. A client still holding one of those
    names now gets "Unknown tool" rather than an answer.
    """
    for fn in _SEARCH_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
