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

from rcsb_mcp import queries
from rcsb_mcp.attribute_types import SearchAttribute, TextOperator
from rcsb_mcp.client import _post_search, _search_editor
from rcsb_mcp.tooling import READ_ONLY
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES
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


class AttributeFilter(BaseModel):
    """One structured attribute condition — a single `text`/`text_chem` terminal.

    A list of these expresses a flat multi-attribute query (combined with one
    AND/OR). Find a path/operators with rcsb_list_pdb_search_attributes.
    """

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
        _check_operator(_check_attribute(f.attribute, schema), f.operator)
    for facet in facets or []:
        _check_facet(facet, schema)
    if sort_by and sort_by not in _RESERVED_SORT:
        _check_attribute(sort_by, schema)


def _validate_advanced_body(query_body: Any) -> None:
    """Best-effort validation of the attribute paths in a raw advanced query body.

    Walks `text` / `text_chem` terminals and checks their parameters.attribute (+ operator)
    against the matching catalog; leaves everything else (services, group shape) to the API,
    and never raises on a malformed body — only on a clearly-invalid attribute path.
    """
    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "group":
            for child in node.get("nodes") or []:
                walk(child)
        elif node.get("type") == "terminal" and node.get("service") in ("text", "text_chem"):
            params = node.get("parameters")
            attr = params.get("attribute") if isinstance(params, dict) else None
            if isinstance(attr, str) and attr:
                record = _check_attribute(attr, "chemical" if node["service"] == "text_chem" else "structure")
                operator = params.get("operator")
                if isinstance(operator, str) and operator:
                    _check_operator(record, operator)

    if isinstance(query_body, dict):
        walk(query_body.get("query"))


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


async def rcsb_search_fulltext(
    query: str,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    return_type: ReturnType = "entry",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    include_computed_models: bool = False,
    chemical: bool = False,
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Search the PDB by free-text keywords (e.g. "CRISPR Cas9", "hemoglobin"), optionally
    refined with structured attribute filters.

    Best for broad or exploratory keyword lookups. Pass `attributes` to AND/OR the keyword
    with structured conditions (organism, resolution, method, dates, ...) in one query. When a
    request has NO keyword (only attributes), use rcsb_search_by_attribute; when it resolves to
    a clear attribute/value, prefer structured search (call rcsb_list_pdb_search_attributes for
    the exact path — more precise, avoids spurious keyword matches). For NESTED boolean logic or
    other services (sequence/structure/chemical/motif), use rcsb_search_advanced.

    BEFORE keyword-searching a biological CONCEPT (disease/function/domain/enzyme/organism),
    resolve it to an ontology id and filter on the annotation instead — see the resolver and
    assembly/multimer guidance in the server instructions. Matching spans ALL text annotations,
    so judge each hit yourself; a high `score` is text-relevance, NOT biological importance —
    never tell the user one hit is better than another because its score is higher.

    Args:
        query: Free-text terms matched (case-insensitively) against all text annotations. Quote
            a phrase to require adjacency (e.g. '"DNA polymerase"'); separate words narrow the
            results; trailing '*' is a prefix wildcard. AND/OR/NOT are NOT boolean operators here.
        attributes: Optional structured conditions combined with the keyword — AttributeFilter
            {attribute, operator, value, negation?, case_sensitive?} (see
            rcsb_search_by_attribute / rcsb_list_pdb_search_attributes for paths and operators).
        logical_operator: Combine the keyword with the attribute conditions (default "and").
        return_type: What to return (default "entry"); see the "Return types and fetching
            details" note in the server instructions.
        limit: Max number of hits to return (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call, for an explicit "ALL ..." request.
            Ignores limit and omits paging; can't be combined with offset (the Search API rejects
            pagination here); refused above 10000 hits — narrow, aggregate with `facets`, or page.
        include_computed_models: Also search computed structure models (AlphaFold etc.).
        chemical: Set True when `attributes` target chemical-component attributes (the text_chem
            service; usually pair with return_type="mol_definition").
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        sort_by: Attribute path to order the hits by; omit to sort by relevance score. Only
            SORTABLE attributes work: those listing exact_match (strings) or equals (numbers/
            dates) in rcsb_list_pdb_search_attributes; full-text-only attributes (e.g.
            struct.title) and return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; hits are ids only — batch them into rcsb_get_entries (or the
        rcsb_get_* tool matching return_type). all_hits/facets response variants: see the
        server instructions.
    """
    _validate_query_attributes(chemical=chemical, attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_combined_query(
        full_text=query,
        filters=_filter_dicts(attributes),
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        include_computed=include_computed_models,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
        chemical=chemical,
        facets=facets,
    )
    if all_hits:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


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
    query: str | None = None, schema: AttributeSchema = "structure"
) -> dict[str, Any]:
    """Discover the RCSB PDB Search schema: attribute paths, value types, and operators.

    Call this FIRST when a request resolves to a clear attribute and value but you don't know
    the exact path; pick the attribute here, then use it in `rcsb_search_by_attribute` (or as an
    `attributes` entry on any `rcsb_search_*`).

    Args:
        query: Optional case-insensitive keyword to filter the catalog. Matched as a LITERAL
            SUBSTRING against the attribute path and description, so pass ONE keyword
            ("resolution", "comp_id"), not a phrase — a multi-word query only matches where
            those exact words are adjacent in a description. Omit to return everything.
        schema: Which catalog — "structure" (~675 attrs: entry/entity/assembly/instance) or
            "chemical" (~57 attrs: chemical-component). See the server instructions for how to
            search chemical attributes.

    Returns:
        {count, match_mode, attributes, note?}. `attributes` holds {attribute, type, operators,
        description} records — the RCSB/PDB attribute path (e.g.
        "rcsb_entry_info.resolution_combined"), its value type (string/number/integer/date), the
        operators it supports (exact_match, greater, range, exists, ...), and a human-readable
        description. `match_mode` is "exact" (the query matched), "none" (nothing matched — read
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


async def rcsb_search_by_attribute(
    attributes: list[AttributeFilter],
    logical_operator: LogicalOperator = "and",
    return_type: ReturnType = "entry",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
    chemical: bool = False,
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
) -> dict[str, Any]:
    """Search by one or more structured attribute conditions combined with a single AND/OR —
    preferred over rcsb_search_fulltext whenever the request resolves to clear attribute(s)
    and value(s). NEVER invent, guess, or infer attributes.
    If you don't know a path or its operators, call rcsb_list_pdb_search_attributes
    first. For NESTED boolean logic use rcsb_search_advanced.

    For a biological concept, resolve it to an ontology id first and filter on the matching
    annotation (see the resolver guidance in the server instructions). If a resolver returns no
    usable id, or a concept/annotation filter yields no hits, fall back to rcsb_search_fulltext
    for the concept. (For ordinary constraints — resolution, organism, dates — an empty result
    is a valid answer: report it, don't keyword-search instead.)

    Example ("human X-ray structures better than 2 A"):
        attributes=[
            {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
             "operator": "exact_match", "value": "Homo sapiens"},
            {"attribute": "exptl.method", "operator": "exact_match", "value": "X-RAY DIFFRACTION"},
            {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0},
        ]
    Single-condition examples: a released-after-date filter ->
    {"attribute": "rcsb_accession_info.initial_release_date", "operator": "greater",
    "value": "2024-01-01T00:00:00Z"}; has any ligand (no value) ->
    {"attribute": "rcsb_nonpolymer_entity.pdbx_description", "operator": "exists"}.

    Args:
        attributes: One or more AttributeFilter conditions, each {attribute, operator, value,
            negation?, case_sensitive?}. Operators are TYPE-SPECIFIC (strings use
            exact_match/in or contains_words/contains_phrase; numbers/dates use greater/
            greater_or_equal/less/less_or_equal/equals/range; any type supports exists). A
            numeric value may be a number or a numeric string; a range value is a
            {from, to, include_lower, include_upper} object (bounds EXCLUSIVE unless the
            include flags are true). See rcsb_list_pdb_search_attributes for paths/operators.
        logical_operator: Combine the conditions with "and" (default) or "or".
        return_type: What to return (default "entry"); see the "Return types and fetching
            details" note in the server instructions. E.g. return_type="entry" with a ligand
            attribute finds the structures that contain it.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        chemical: Set True for chemical-component attributes (paths from
            rcsb_list_pdb_search_attributes(schema="chemical"), e.g. "chem_comp.formula_weight").
            Switches to the text_chem service; usually pair with return_type="mol_definition".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        sort_by: Attribute path to order the hits by. A pure attribute filter is a boolean match,
            so hits otherwise come back in near-arbitrary order — set this for "best resolution
            first", "newest first", etc. Only SORTABLE attributes work: those listing exact_match
            (strings) or equals (numbers/dates) in rcsb_list_pdb_search_attributes; full-text-only
            attributes (e.g. struct.title) and return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; hits are ids only — batch them into rcsb_get_entries (or the
        rcsb_get_* tool matching return_type). The per-hit `score` is near-uniform for a pure
        attribute filter and carries NO biological meaning — don't rank hits by it.
        all_hits/facets response variants: see the server instructions.
    """
    _validate_query_attributes(chemical=chemical, attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_combined_query(
        full_text=None,
        filters=_filter_dicts(attributes),
        logical_operator=logical_operator,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
        chemical=chemical,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    if all_hits:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


async def rcsb_search_by_sequence(
    sequence: str,
    sequence_type: SequenceType = "protein",
    identity_cutoff: Annotated[float, Field(ge=0.0, le=1.0)] = 0.3,
    evalue_cutoff: Annotated[float, Field(ge=0.0)] = 1.0,
    return_type: ReturnType = "polymer_entity",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find PDB polymer entities similar to a given sequence (MMseqs2, BLAST-like).

    Args:
        sequence: The query sequence in one-letter code.
        sequence_type: "protein", "dna", or "rna".
        identity_cutoff: Minimum sequence identity as a fraction 0-1 (e.g. 0.3 = 30%).
        evalue_cutoff: Maximum E-value to report.
        return_type: What to return (default "polymer_entity"); see the "Return types and
            fetching details" note in the server instructions.
        limit: Max hits (1-100). Returns polymer_entity IDs like "4HHB_1" — fetch their
            details with rcsb_get_polymer_entities.
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        sort_by: Attribute path to order the hits by, replacing the default similarity ordering
            (each hit's score is still returned); omit to keep it. Only SORTABLE attributes work:
            those listing exact_match (strings) or equals (numbers/dates) in
            rcsb_list_pdb_search_attributes; full-text-only attributes (e.g. struct.title) and
            return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; with `facets`, instead returns {total_count, facets, editor}.
    """
    _validate_query_attributes(attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_sequence_query(
        sequence,
        sequence_type=sequence_type,
        identity_cutoff=identity_cutoff,
        evalue_cutoff=evalue_cutoff,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


async def rcsb_search_by_chemical(
    value: str,
    query_type: ChemQueryType = "descriptor",
    descriptor_type: DescriptorType = "SMILES",
    match_type: ChemMatchType = "graph-relaxed",
    match_subset: bool = False,
    return_type: ReturnType = "mol_definition",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Search PDB chemical components by structure (SMILES/InChI) or formula.

    Args:
        value: A SMILES/InChI string (query_type="descriptor") or a molecular
            formula like "C8H9NO2" (query_type="formula").
        query_type: "descriptor" (default) or "formula".
        descriptor_type: "SMILES" or "InChI" (descriptor queries only).
        match_type: Graph/fingerprint criterion for descriptor queries, one of:
            graph-exact, graph-strict, graph-relaxed (default), graph-relaxed-stereo
            (whole-molecule matches, strict->relaxed = stricter->looser); the
            sub-struct-graph-* variants of each (substructure search); or
            fingerprint-similarity (similar molecules).
        match_subset: Formula queries only — match formulas that merely contain the
            requested atoms.
        return_type: What to return (default "mol_definition" = the chemical component); see the
            "Return types and fetching details" note in the server instructions.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        sort_by: Attribute path to order the hits by, replacing the default score ordering (each
            hit's score is still returned); omit to keep it. Only SORTABLE attributes work: those
            listing exact_match (strings) or equals (numbers/dates) in
            rcsb_list_pdb_search_attributes; full-text-only attributes (e.g. struct.title) and
            return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; with `facets`, instead returns {total_count, facets, editor}.
    """
    _validate_query_attributes(attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_chemical_query(
        value,
        query_type=query_type,
        descriptor_type=descriptor_type,
        match_type=match_type,
        match_subset=match_subset,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


async def rcsb_search_by_structure(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
    return_type: ReturnType | None = None,
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find structures with a similar 3D shape to a reference PDB structure.

    Args:
        entry_id: Reference PDB entry, e.g. "4HHB".
        assembly_id: Use this biological assembly as the reference (e.g. "1").
            Defaults to assembly "1" when neither assembly_id nor asym_id is given.
        asym_id: Use this single chain as the reference instead (mutually exclusive
            with assembly_id).
        return_type: What to return (defaults to "assembly" for an assembly reference or
            "polymer_instance" for a chain reference); see the "Return types and fetching
            details" note in the server instructions.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        sort_by: Attribute path to order the hits by, replacing the default shape-similarity
            ordering (each hit's score is still returned); omit to keep it. Only SORTABLE
            attributes work: those listing exact_match (strings) or equals (numbers/dates) in
            rcsb_list_pdb_search_attributes; full-text-only attributes (e.g. struct.title) and
            return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; with `facets`, instead returns {total_count, facets, editor}.
    """
    _validate_query_attributes(attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_structure_query(
        entry_id,
        assembly_id=assembly_id,
        asym_id=asym_id,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


async def rcsb_search_by_seqmotif(
    pattern: str,
    pattern_type: SeqmotifPatternType = "prosite",
    sequence_type: SequenceType = "protein",
    return_type: ReturnType = "polymer_entity",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find polymers containing a short sequence motif (PROSITE / regex / simple).

    Args:
        pattern: The motif, e.g. "C-x(2,4)-C-x(3)-[LIVMFYWC]-x(8)-H-x(3,5)-H"
            (prosite), "C..H[LIVF]" (regex), or "NXS" (simple wildcards).
        pattern_type: "prosite" (default), "regex", or "simple".
        sequence_type: "protein" (default), "dna", or "rna".
        return_type: What to return (default "polymer_entity"); see the "Return types and
            fetching details" note in the server instructions.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        sort_by: Attribute path to order the hits by, replacing the default score ordering (each
            hit's score is still returned); omit to keep it. Only SORTABLE attributes work: those
            listing exact_match (strings) or equals (numbers/dates) in
            rcsb_list_pdb_search_attributes; full-text-only attributes (e.g. struct.title) and
            return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; with `facets`, instead returns {total_count, facets, editor}.
    """
    _validate_query_attributes(attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_seqmotif_query(
        pattern,
        pattern_type=pattern_type,
        sequence_type=sequence_type,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


async def rcsb_search_advanced(query_body: dict[str, Any]) -> dict[str, Any]:
    """Run a raw RCSB Search API query body (escape hatch).

    Endpoint: https://search.rcsb.org/rcsbsearch/v2/query . The typed rcsb_search_* tools cover
    the common cases (each carries total_count and takes `attributes` + `facets`); use this for
    anything they don't — return_all_hits, group_by "groups", arbitrarily NESTED and/or
    boolean groups, and queries that COMBINE several non-text services (sequence, structure,
    chemical, seqmotif, strucmotif) under one group (e.g. a sequence-similarity match AND a
    chemical-descriptor match — a single non-text service can already be refined with
    `attributes` on its rcsb_search_by_* tool). Build the query from "group"
    nodes (logical_operator + nodes) and "terminal" nodes (service + parameters); full query
    language: https://search.rcsb.org/ . The body is {"query", "return_type",
    "request_options"} and returns the normalized {total_count, returned, hits} result.

    Example — "(Homo sapiens OR Mus musculus) AND released after 2019-08-20":
        query_body={"query": {"type": "group", "logical_operator": "and", "nodes": [
          {"type": "group", "logical_operator": "or", "nodes": [
            {"type": "terminal", "service": "text", "parameters": {
              "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
              "operator": "exact_match", "value": "Homo sapiens"}},
            {"type": "terminal", "service": "text", "parameters": {
              "attribute": "rcsb_entity_source_organism.taxonomy_lineage.name",
              "operator": "exact_match", "value": "Mus musculus"}}]},
          {"type": "terminal", "service": "text", "parameters": {
            "attribute": "rcsb_accession_info.initial_release_date",
            "operator": "greater", "value": "2019-08-20"}}]},
          "return_type": "polymer_entity"}

    Args:
        query_body: A complete RCSB Search API request — {"query", "return_type",
            "request_options"} — built from "group" and "terminal" nodes (full query
            language at https://search.rcsb.org/). Returns the normalized
            {total_count, returned, hits} result.
    """
    _validate_advanced_body(query_body)
    raw = await _post_search(query_body)
    return _format(raw, query_body)


async def rcsb_search_strucmotif(
    entry_id: str,
    residue_ids: list[dict[str, Any]],
    backbone_distance_tolerance: Tolerance = 1,
    side_chain_distance_tolerance: Tolerance = 1,
    angle_tolerance: Tolerance = 1,
    rmsd_cutoff: Annotated[float, Field(ge=0.0)] = 2.0,
    atom_pairing_scheme: AtomPairingScheme = "SIDE_CHAIN",
    motif_pruning_strategy: MotifPruningStrategy = "KRUSKAL",
    return_type: ReturnType = "assembly",
    limit: Limit = 10,
    offset: Offset = 0,
    all_hits: bool = False,
    attributes: list[AttributeFilter] | None = None,
    logical_operator: LogicalOperator = "and",
    facets: list[dict[str, Any]] | None = None,
    sort_by: str | None = None,
    sort_direction: SortDirection = "asc",
    group_by: GroupBy | None = None,
    group_by_ranking: GroupByRanking | None = None,
) -> dict[str, Any]:
    """Find structures containing a 3D STRUCTURAL MOTIF — a geometric arrangement of
    specific residues — like the one in a reference structure.

    This is geometry-based and DIFFERENT from rcsb_search_by_structure (whole-shape similarity)
    and from rcsb_search_by_seqmotif (sequence pattern). Use it for catalytic triads, binding
    sites, metal-coordination geometries, etc.

    Args:
        entry_id: Reference PDB entry defining the motif, e.g. "2MNR".
        residue_ids: 2-10 residues defining the motif, each a dict
            {"label_asym_id": <chain>, "label_seq_id": <int>, "struct_oper_id"?: <str>}.
            IMPORTANT: these are the mmCIF *label* identifiers (the internal numbering),
            which often DIFFER from the author residue numbers seen in papers/the PDB
            site. If you only have author numbering, resolve the label_asym_id/label_seq_id
            first (e.g. via rcsb_get_polymer_entity_instances) — author numbers give wrong/no hits.
            Example (enolase catalytic residues):
            [{"label_asym_id":"A","label_seq_id":162},
             {"label_asym_id":"A","label_seq_id":193},
             {"label_asym_id":"A","label_seq_id":219}]
        backbone_distance_tolerance: Backbone distance tolerance in Å, integer 0-3 (default 1).
        side_chain_distance_tolerance: Side-chain distance tolerance in Å, integer 0-3 (default 1).
        angle_tolerance: Angle tolerance in multiples of 20°, integer 0-3 (default 1).
        rmsd_cutoff: Maximum RMSD of accepted hits (default 2.0).
        atom_pairing_scheme: ALL, BACKBONE, SIDE_CHAIN (default), or PSEUDO_ATOMS.
        motif_pruning_strategy: NONE or KRUSKAL (default).
        return_type: What to return (default "assembly"); see the "Return types and fetching
            details" note in the server instructions.
        limit: Max hits (1-100).
        offset: Number of hits to skip, for paging; pass the response's next_offset back with
            the same query to fetch the next page.
        all_hits: Return the COMPLETE result set in one call (for an explicit "ALL ..." request);
            ignores limit, can't be combined with offset, and is refused above 10000 hits.
            Ignored when `facets` is set.
        attributes: Optional structured filters AND/OR-combined with this match — a list of
            AttributeFilter {attribute, operator, value, negation?, case_sensitive?} (e.g.
            restrict to an organism or resolution). See rcsb_search_by_attribute /
            rcsb_list_pdb_search_attributes for paths and operators.
        logical_operator: Combine this match and the attribute conditions with "and"
            (default) or "or".
        facets: Optional aggregation specs to return a breakdown / distribution instead of hits
            (see the faceting note in the server instructions for the spec).
        group_by, group_by_ranking: Collapse redundant polymer_entity hits into clusters, one
            representative each (needs return_type="polymer_entity") — see the grouping note in
            the server instructions.
        sort_by: Attribute path to order the hits by, replacing the default score ordering (each
            hit's score is still returned); omit to keep it. Only SORTABLE attributes work: those
            listing exact_match (strings) or equals (numbers/dates) in
            rcsb_list_pdb_search_attributes; full-text-only attributes (e.g. struct.title) and
            return_type="mol_definition" are rejected.
        sort_direction: "asc" (default) or "desc"; applies only when sort_by is set.

    Returns:
        {total_count, returned, offset, has_more, next_offset, hits:[{id, score}],
        editor}; with `facets`, instead returns {total_count, facets, editor}.
    """
    _validate_query_attributes(attributes=attributes, facets=facets, sort_by=sort_by)
    body = queries.build_strucmotif_query(
        entry_id,
        residue_ids,
        backbone_distance_tolerance=backbone_distance_tolerance,
        side_chain_distance_tolerance=side_chain_distance_tolerance,
        angle_tolerance=angle_tolerance,
        rmsd_cutoff=rmsd_cutoff,
        atom_pairing_scheme=atom_pairing_scheme,
        motif_pruning_strategy=motif_pruning_strategy,
        return_type=return_type,
        rows=limit,
        start=offset,
        all_hits=all_hits,
        attributes=_filter_dicts(attributes),
        logical_operator=logical_operator,
        facets=facets,
        sort_by=sort_by,
        sort_direction=sort_direction,
        group_by=group_by,
        group_by_ranking=group_by_ranking,
    )
    if all_hits and not facets:
        await _guard_all_hits(body, offset)
    raw = await _post_search(body)
    if facets:
        return _format_facets(raw, body)
    return _format(raw, body, None if all_hits else offset)


# rcsb_search_* are the discovery tools; register_search_tools wires each onto the
# passed FastMCP instance (equivalent to the @mcp.tool decorator, but the functions
# stay importable/testable on their own). Original tool order is preserved.
_SEARCH_TOOLS = (
    rcsb_search_fulltext,
    rcsb_list_pdb_search_attributes,
    rcsb_search_by_attribute,
    rcsb_search_by_sequence,
    rcsb_search_by_chemical,
    rcsb_search_by_structure,
    rcsb_search_by_seqmotif,
    rcsb_search_advanced,
    rcsb_search_strucmotif,
)


def register_search_tools(mcp) -> None:
    """Attach the RCSB Search API tools (rcsb_search_*) to a FastMCP server."""
    for fn in _SEARCH_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
