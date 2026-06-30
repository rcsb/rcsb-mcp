"""Pure helpers that build RCSB Search API v2 and Data API GraphQL request bodies.

These functions contain *no* network code so they can be unit-tested in
isolation. Search builders return a dict ready to be POSTed to
https://search.rcsb.org/rcsbsearch/v2/query ; the GraphQL builders return a
``{"query", "variables"}`` dict ready to be POSTed to
https://data.rcsb.org/graphql
"""
from __future__ import annotations

from typing import Any, NamedTuple

from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES
from rcsb_mcp.graphql_queries import ENTRY_ANNOTATIONS, ENTRY_EXP_INFO
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES

# Valid return types accepted by the Search API.
RETURN_TYPES = {
    "entry",
    "polymer_entity",
    "non_polymer_entity",
    "polymer_instance",
    "assembly",
    "mol_definition",
}

# The full set of attribute/text comparison operators from the spec enum.
TEXT_OPERATORS = {
    "exact_match",
    "in",
    "contains_words",
    "contains_phrase",
    "greater",
    "greater_or_equal",
    "less",
    "less_or_equal",
    "equals",
    "range",
    "exists",
}

# Sequence/seqmotif scope.
SEQUENCE_TYPES = {"protein", "rna", "dna"}

# Chemical descriptor graph-matching criteria (spec enum).
CHEMICAL_MATCH_TYPES = {
    "graph-exact",
    "graph-strict",
    "graph-relaxed",
    "graph-relaxed-stereo",
    "fingerprint-similarity",
    "sub-struct-graph-exact",
    "sub-struct-graph-strict",
    "sub-struct-graph-relaxed",
    "sub-struct-graph-relaxed-stereo",
}

# Seqmotif pattern grammars (spec enum).
SEQMOTIF_PATTERN_TYPES = {"simple", "prosite", "regex"}

# group_by values -> the RCSB aggregation_method spec for collapsing redundant hits
# into clusters (one representative each). Only valid with return_type=polymer_entity.
GROUP_BY_METHODS: dict[str, dict[str, Any]] = {
    "seqid_30": {"aggregation_method": "sequence_identity", "similarity_cutoff": 30},
    "seqid_50": {"aggregation_method": "sequence_identity", "similarity_cutoff": 50},
    "seqid_70": {"aggregation_method": "sequence_identity", "similarity_cutoff": 70},
    "seqid_90": {"aggregation_method": "sequence_identity", "similarity_cutoff": 90},
    "seqid_95": {"aggregation_method": "sequence_identity", "similarity_cutoff": 95},
    "uniprot": {"aggregation_method": "matching_uniprot_accession"},
}
# group_by_ranking value -> (sort_by, fixed direction) choosing each cluster's
# representative. "coverage" (uniprot grouping only) takes no direction.
GROUP_BY_RANKING_SORTS: dict[str, tuple[str, str]] = {
    "resolution": ("rcsb_entry_info.resolution_combined", "asc"),
    "released_date": ("rcsb_accession_info.initial_release_date", "desc"),
    "entity_residue_count": ("entity_poly.rcsb_sample_sequence_length", "desc"),
    "score": ("score", "desc"),
}

# Facet (aggregation) types from the spec enum.
FACET_AGG_TYPES = {"terms", "histogram", "date_histogram", "range", "date_range", "cardinality"}

# Strucmotif tuning enums (spec).
STRUCMOTIF_ATOM_PAIRING = {"ALL", "BACKBONE", "SIDE_CHAIN", "PSEUDO_ATOMS"}
STRUCMOTIF_PRUNING = {"NONE", "KRUSKAL"}


def _request_options(
    start: int,
    rows: int,
    include_computed: bool,
    *,
    all_hits: bool = False,
    scoring_strategy: str | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
    return_type: str | None = None,
) -> dict[str, Any]:
    """Common request_options block: pagination, content type, sort, grouping.

    When `all_hits` is True the query returns the COMPLETE result set
    (`return_all_hits`) and pagination is omitted; otherwise it pages with start/rows.
    `group_by` (see GROUP_BY_METHODS) collapses redundant polymer_entity hits into
    clusters and returns one representative each, chosen by `group_by_ranking` (see
    GROUP_BY_RANKING_SORTS — each ranking has a fixed direction). Requiring
    return_type=polymer_entity is the caller's responsibility.
    """
    content = ["experimental"]
    if include_computed:
        content.append("computational")
    options: dict[str, Any] = {
        "results_content_type": content,
        "sort": [{"sort_by": "score", "direction": "desc"}],
    }
    if all_hits:
        options["return_all_hits"] = True
    else:
        options["paginate"] = {"start": start, "rows": rows}
    if scoring_strategy:
        options["scoring_strategy"] = scoring_strategy
    if group_by_ranking is not None and group_by is None:
        raise ValueError("group_by_ranking requires group_by")
    if group_by is not None:
        if return_type != "polymer_entity":
            raise ValueError("group_by is only available with return_type='polymer_entity'")
        if group_by not in GROUP_BY_METHODS:
            raise ValueError(f"group_by must be one of {sorted(GROUP_BY_METHODS)}")
        gb: dict[str, Any] = dict(GROUP_BY_METHODS[group_by])
        if group_by_ranking == "coverage":
            # UniProt-only ranking: keep the candidate covering the most of the UniProt
            # sequence. Takes NO direction (the API rejects extra keys).
            if group_by != "uniprot":
                raise ValueError('group_by_ranking="coverage" requires group_by="uniprot"')
            gb["ranking_criteria_type"] = {"sort_by": "coverage"}
        elif group_by_ranking is not None:
            if group_by_ranking not in GROUP_BY_RANKING_SORTS:
                raise ValueError(
                    "group_by_ranking must be one of "
                    f"{sorted(GROUP_BY_RANKING_SORTS) + ['coverage']}"
                )
            sort_by, direction = GROUP_BY_RANKING_SORTS[group_by_ranking]
            gb["ranking_criteria_type"] = {"sort_by": sort_by, "direction": direction}
        options["group_by"] = gb
        options["group_by_return_type"] = "representatives"
    return options


# Attribute -> declared value type, from the generated Search schema catalogs. Clients
# commonly send numbers as strings (e.g. "2.0"), which the API rejects for numeric
# attributes; coercion is driven off this *type* (not the operator) so a date attribute —
# which shares greater/less/range with integers — is never turned into a number, and a
# string attribute never is either.
_ATTR_TYPES: dict[str, str] = {a["attribute"]: a["type"] for a in SEARCH_ATTRIBUTES}
_CHEM_ATTR_TYPES: dict[str, str] = {a["attribute"]: a["type"] for a in CHEMICAL_SEARCH_ATTRIBUTES}

# Operators that require a numeric value — used ONLY as a fallback for attributes absent
# from the catalogs (so coercion still helps an uncatalogued numeric path).
NUMERIC_TEXT_OPERATORS = {
    "greater", "greater_or_equal", "less", "less_or_equal", "equals", "range",
}


def _as_number(v: Any) -> Any:
    """A plain-number string -> int/float; anything else (incl. ISO dates) unchanged."""
    if isinstance(v, str):
        s = v.strip()
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return v
    return v


def _coerce_scalar(v: Any, attr_type: str | None, operator: str) -> Any:
    """Coerce one value to the attribute's declared numeric type.

    'integer' -> int, 'number' -> float; 'date'/'string' (any other known type) are left
    untouched. When the attribute is absent from the catalog (attr_type is None) fall back
    to a numeric-operator heuristic so an uncatalogued numeric path still works.
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    if attr_type == "integer":
        try:
            return int(s)
        except ValueError:
            return v
    if attr_type == "number":
        try:
            return float(s)
        except ValueError:
            return v
    if attr_type is not None:
        return v  # known string / date attribute -> never coerce
    return _as_number(v) if operator in NUMERIC_TEXT_OPERATORS else v  # uncatalogued fallback


def _coerce_value(value: Any, operator: str, attribute: str, service: str) -> Any:
    """Coerce a query value to the attribute's declared type (see _coerce_scalar).

    Applies to a scalar, each element of an 'in' list, and the from/to bounds of a
    'range' object. Driven by the attribute's type from the Search schema catalog.
    """
    attr_type = (_CHEM_ATTR_TYPES if service == "text_chem" else _ATTR_TYPES).get(attribute)
    if isinstance(value, dict):  # range: {from, to, include_lower, include_upper}
        return {k: (_coerce_scalar(v, attr_type, operator) if k in ("from", "to") else v)
                for k, v in value.items()}
    if isinstance(value, list):  # 'in'
        return [_coerce_scalar(v, attr_type, operator) for v in value]
    return _coerce_scalar(value, attr_type, operator)


def _text_node(
    attribute: str,
    operator: str,
    value: Any = None,
    *,
    service: str = "text",
    negation: bool = False,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """Build a terminal attribute query node.

    `service` is "text" for structure attributes or "text_chem" for
    chemical-component attributes. The 'exists' operator takes no value; all
    others require one (a numeric-looking string is coerced to the attribute's
    declared type — see _coerce_value). `negation` inverts the match and
    `case_sensitive` forces exact-case comparison.
    """
    if operator not in TEXT_OPERATORS:
        raise ValueError(f"operator must be one of {sorted(TEXT_OPERATORS)}")
    params: dict[str, Any] = {"attribute": attribute, "operator": operator}
    if operator != "exists":
        params["value"] = _coerce_value(value, operator, attribute, service)
    if negation:
        params["negation"] = True
    if case_sensitive:
        params["case_sensitive"] = True
    return {"type": "terminal", "service": service, "parameters": params}


def _search_node(
    full_text: str | None,
    filters: list[dict[str, Any]] | None,
    logical_operator: str = "and",
    *,
    service: str = "text",
) -> dict[str, Any]:
    """Build one query node from a full-text term and/or attribute filters.

    The full-text term (if any) is always a 'full_text' terminal; each filter is
    a `service` terminal ("text" or "text_chem"). A single condition collapses to
    a plain terminal; several are wrapped in an AND/OR "group". Raises if neither
    a term nor a filter is provided.
    """
    if logical_operator not in {"and", "or"}:
        raise ValueError('logical_operator must be "and" or "or"')
    nodes: list[dict[str, Any]] = []
    if full_text:
        nodes.append({
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": full_text},
        })
    for f in filters or []:
        nodes.append(
            _text_node(
                f["attribute"],
                f.get("operator"),
                f.get("value"),
                service=service,
                negation=f.get("negation", False),
                case_sensitive=f.get("case_sensitive", False),
            )
        )
    if not nodes:
        raise ValueError("provide a full_text term and/or at least one filter")
    if len(nodes) == 1:
        return nodes[0]
    return {"type": "group", "logical_operator": logical_operator, "nodes": nodes}


def _combine_service(
    service_node: dict[str, Any],
    attributes: list[dict[str, Any]] | None,
    logical_operator: str = "and",
) -> dict[str, Any]:
    """AND/OR a primary service terminal (sequence/structure/chemical/motif) with optional
    structured attribute filters. Returns the bare terminal when there are no attributes,
    else a group wrapping the service node and one text terminal per filter — the same shape
    RCSB.org produces when you add attribute refinements to a service search.
    """
    if not attributes:
        return service_node
    if logical_operator not in {"and", "or"}:
        raise ValueError('logical_operator must be "and" or "or"')
    nodes = [service_node]
    for f in attributes:
        nodes.append(
            _text_node(
                f["attribute"], f.get("operator"), f.get("value"),
                negation=f.get("negation", False),
                case_sensitive=f.get("case_sensitive", False),
            )
        )
    return {"type": "group", "logical_operator": logical_operator, "nodes": nodes}


def _facet_options(
    facets: list[dict[str, Any]], include_computed: bool = False
) -> dict[str, Any]:
    """request_options for a facet (aggregation-only) query: rows=0 + validated facets."""
    content = ["experimental"] + (["computational"] if include_computed else [])
    return {
        "paginate": {"start": 0, "rows": 0},
        "results_content_type": content,
        "facets": [_build_facet(f) for f in facets],
    }


def build_combined_query(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
    all_hits: bool = False,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    group_by: str | None = None,
    group_by_ranking: str | None = None,
    chemical: bool = False,
    facets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Combine a full-text term and/or several attribute filters with AND/OR.

    Each filter is a dict {"attribute", "operator", "value"} and may also carry
    optional "negation" and "case_sensitive" booleans. A single condition
    (one full_text term or one filter) collapses to a plain terminal
    node; multiple conditions are wrapped in a "group" node. Set `chemical=True`
    when the filters target chemical-component attributes (the "text_chem"
    service); the full-text term always uses the "full_text" service.

    Example ("human hemoglobin better than 2 A", sorted by resolution):
        build_combined_query(
            full_text="hemoglobin",
            filters=[
                {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
                 "operator": "exact_match", "value": "Homo sapiens"},
                {"attribute": "rcsb_entry_info.resolution_combined",
                 "operator": "less", "value": 2.0},
            ],
            sort_by="rcsb_entry_info.resolution_combined",
        )
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")

    query = _search_node(
        full_text, filters, logical_operator,
        service="text_chem" if chemical else "text",
    )

    if facets:
        options = _facet_options(facets, include_computed)
    else:
        options = _request_options(
            start, rows, include_computed,
            all_hits=all_hits,
            group_by=group_by,
            group_by_ranking=group_by_ranking,
            return_type=return_type,
        )
        if sort_by:
            if sort_direction not in {"asc", "desc"}:
                raise ValueError('sort_direction must be "asc" or "desc"')
            options["sort"] = [{"sort_by": sort_by, "direction": sort_direction}]
    return {
        "query": query,
        "return_type": return_type,
        "request_options": options,
    }


def build_sequence_query(
    sequence: str,
    sequence_type: str = "protein",
    identity_cutoff: float = 0.3,
    evalue_cutoff: float = 1.0,
    return_type: str = "polymer_entity",
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    attributes: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
) -> dict[str, Any]:
    """MMseqs2 sequence-similarity search (BLAST-like), optionally AND/OR-refined with
    attribute filters and/or aggregated into facets.

    identity_cutoff is a fraction in [0, 1]. sequence_type is one of
    "protein", "dna", "rna".
    """
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    if not 0.0 <= identity_cutoff <= 1.0:
        raise ValueError("identity_cutoff must be between 0 and 1")
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    node = {
        "type": "terminal",
        "service": "sequence",
        "parameters": {
            "value": sequence.strip().upper(),
            "sequence_type": sequence_type,
            "identity_cutoff": identity_cutoff,
            "evalue_cutoff": evalue_cutoff,
        },
    }
    options = _facet_options(facets) if facets else _request_options(
        start, rows, False, all_hits=all_hits, scoring_strategy="sequence",
        group_by=group_by, group_by_ranking=group_by_ranking, return_type=return_type)
    return {
        "query": _combine_service(node, attributes, logical_operator),
        "return_type": return_type,
        "request_options": options,
    }


def build_chemical_query(
    value: str,
    query_type: str = "descriptor",
    descriptor_type: str = "SMILES",
    match_type: str = "graph-relaxed",
    match_subset: bool = False,
    return_type: str = "mol_definition",
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    attributes: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
) -> dict[str, Any]:
    """Chemical search by SMILES/InChI descriptor or by molecular formula, optionally
    AND/OR-refined with attribute filters and/or aggregated into facets.

    query_type="descriptor": match `value` (a SMILES or InChI string) using a
    graph/fingerprint `match_type` (e.g. "graph-relaxed" for exact molecules,
    "sub-struct-graph-relaxed" for substructure search).
    query_type="formula": match a molecular formula like "C8H9NO2"; set
    match_subset=True to match formulas containing at least those atoms.
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    if query_type == "descriptor":
        if descriptor_type not in {"SMILES", "InChI"}:
            raise ValueError('descriptor_type must be "SMILES" or "InChI"')
        if match_type not in CHEMICAL_MATCH_TYPES:
            raise ValueError(f"match_type must be one of {sorted(CHEMICAL_MATCH_TYPES)}")
        # SMILES/InChI are case-sensitive: strip only, never upper-case.
        params: dict[str, Any] = {
            "type": "descriptor",
            "value": value.strip(),
            "descriptor_type": descriptor_type,
            "match_type": match_type,
        }
    elif query_type == "formula":
        # Element symbols are case-sensitive (e.g. Co vs CO): do not upper-case.
        params = {"type": "formula", "value": value.strip(), "match_subset": bool(match_subset)}
    else:
        raise ValueError('query_type must be "descriptor" or "formula"')
    node = {"type": "terminal", "service": "chemical", "parameters": params}
    options = (_facet_options(facets) if facets
               else _request_options(start, rows, False, all_hits=all_hits, group_by=group_by, group_by_ranking=group_by_ranking, return_type=return_type, scoring_strategy="chemical"))
    return {
        "query": _combine_service(node, attributes, logical_operator),
        "return_type": return_type,
        "request_options": options,
    }


def build_structure_query(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
    return_type: str | None = None,
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    attributes: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
) -> dict[str, Any]:
    """3D shape-similarity search against an existing PDB structure, optionally AND/OR-refined
    with attribute filters and/or aggregated into facets.

    Provide a reference by entry + assembly (e.g. entry_id="4HHB", assembly_id="1")
    or entry + chain (asym_id="A"). Defaults to assembly "1" if neither is given.
    Returns assemblies (assembly reference) or polymer instances (chain reference).
    """
    if assembly_id and asym_id:
        raise ValueError("provide assembly_id or asym_id, not both")
    eid = entry_id.strip().upper()
    if asym_id:
        value: dict[str, Any] = {"entry_id": eid, "asym_id": str(asym_id)}
        default_return = "polymer_instance"
    else:
        value = {"entry_id": eid, "assembly_id": str(assembly_id or "1")}
        default_return = "assembly"
    rt = return_type or default_return
    if rt not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    node = {"type": "terminal", "service": "structure", "parameters": {"value": value}}
    options = (_facet_options(facets) if facets
               else _request_options(start, rows, False, all_hits=all_hits, group_by=group_by, group_by_ranking=group_by_ranking, return_type=return_type, scoring_strategy="structure"))
    return {
        "query": _combine_service(node, attributes, logical_operator),
        "return_type": rt,
        "request_options": options,
    }


def build_seqmotif_query(
    pattern: str,
    pattern_type: str = "prosite",
    sequence_type: str = "protein",
    return_type: str = "polymer_entity",
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    attributes: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
) -> dict[str, Any]:
    """Short sequence-motif search (PROSITE pattern, regex, or simple wildcards), optionally
    AND/OR-refined with attribute filters and/or aggregated into facets.

    Examples: pattern_type="prosite" value "C-x(2,4)-C-x(3)-[LIVMFYWC]...",
    pattern_type="regex" value "C..H[LIVF]", pattern_type="simple" value "NXS".
    """
    if pattern_type not in SEQMOTIF_PATTERN_TYPES:
        raise ValueError(f"pattern_type must be one of {sorted(SEQMOTIF_PATTERN_TYPES)}")
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    node = {
        "type": "terminal",
        "service": "seqmotif",
        "parameters": {
            "value": pattern.strip(),
            "pattern_type": pattern_type,
            "sequence_type": sequence_type,
        },
    }
    options = _facet_options(facets) if facets else _request_options(start, rows, False, all_hits=all_hits, group_by=group_by, group_by_ranking=group_by_ranking, return_type=return_type)
    return {
        "query": _combine_service(node, attributes, logical_operator),
        "return_type": return_type,
        "request_options": options,
    }


def _optional_search_node(
    full_text: str | None,
    filters: list[dict[str, Any]] | None,
    logical_operator: str,
    service: str,
) -> dict[str, Any] | None:
    """Like _search_node, but return None (match-all) when no condition is given."""
    if not full_text and not filters:
        return None
    return _search_node(full_text, filters, logical_operator, service=service)


def _build_facet(facet: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one facet (aggregation) spec.

    Every facet needs `name`, `aggregation_type`, `attribute`. Additionally:
      histogram / date_histogram -> `interval`
      range / date_range         -> `ranges` (non-empty list of {from?, to?})
    Optional pass-through: `min_interval_population`, `max_num_intervals`,
    `precision_threshold`, and a nested `facets` list (recursively validated).
    """
    if not isinstance(facet, dict):
        raise ValueError("each facet must be a dict")
    agg = facet.get("aggregation_type")
    if agg not in FACET_AGG_TYPES:
        raise ValueError(f"aggregation_type must be one of {sorted(FACET_AGG_TYPES)}")
    name, attribute = facet.get("name"), facet.get("attribute")
    if not name or not attribute:
        raise ValueError("each facet requires 'name' and 'attribute'")
    out: dict[str, Any] = {"name": name, "aggregation_type": agg, "attribute": attribute}
    if agg in {"histogram", "date_histogram"}:
        if facet.get("interval") is None:
            raise ValueError(f"a {agg} facet requires 'interval'")
        out["interval"] = facet["interval"]
    if agg in {"range", "date_range"}:
        if not facet.get("ranges"):
            raise ValueError(f"a {agg} facet requires a non-empty 'ranges' list")
        out["ranges"] = facet["ranges"]
    for k in ("min_interval_population", "max_num_intervals", "precision_threshold"):
        if facet.get(k) is not None:
            out[k] = facet[k]
    if facet.get("facets"):
        out["facets"] = [_build_facet(f) for f in facet["facets"]]
    return out


def build_facet_query(
    facets: list[dict[str, Any]],
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    chemical: bool = False,
    include_computed: bool = False,
) -> dict[str, Any]:
    """Aggregate matches into buckets/statistics instead of returning hits.

    Builds the same query node as build_combined_query (full_text + filters),
    attaches `facets`, and requests rows=0 so only aggregations + total_count
    come back. Requires at least one facet. With no full_text/filters the facets
    run over all structures.
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    if not facets:
        raise ValueError("provide at least one facet")
    content = ["experimental"] + (["computational"] if include_computed else [])
    body: dict[str, Any] = {
        "return_type": return_type,
        "request_options": {
            "paginate": {"start": 0, "rows": 0},
            "results_content_type": content,
            "facets": [_build_facet(f) for f in facets],
        },
    }
    node = _optional_search_node(
        full_text, filters, logical_operator, "text_chem" if chemical else "text"
    )
    if node is not None:
        body["query"] = node
    return body


def build_count_query(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    chemical: bool = False,
    include_computed: bool = False,
) -> dict[str, Any]:
    """Count matches only (return_counts) — no hits are paged or returned.

    Same query node as build_combined_query. With no full_text/filters the count
    is over all structures of `return_type`.
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    content = ["experimental"] + (["computational"] if include_computed else [])
    body: dict[str, Any] = {
        "return_type": return_type,
        "request_options": {"return_counts": True, "results_content_type": content},
    }
    node = _optional_search_node(
        full_text, filters, logical_operator, "text_chem" if chemical else "text"
    )
    if node is not None:
        body["query"] = node
    return body


def _strucmotif_residue(r: dict[str, Any]) -> dict[str, Any]:
    """Normalize one strucmotif residue identifier."""
    asym, seq = r.get("label_asym_id"), r.get("label_seq_id")
    if asym is None or seq is None:
        raise ValueError("each residue needs label_asym_id and label_seq_id")
    out: dict[str, Any] = {"label_asym_id": str(asym), "label_seq_id": int(seq)}
    if r.get("struct_oper_id") is not None:
        out["struct_oper_id"] = str(r["struct_oper_id"])
    return out


def build_strucmotif_query(
    entry_id: str,
    residue_ids: list[dict[str, Any]],
    backbone_distance_tolerance: int = 1,
    side_chain_distance_tolerance: int = 1,
    angle_tolerance: int = 1,
    rmsd_cutoff: float = 2.0,
    atom_pairing_scheme: str = "SIDE_CHAIN",
    motif_pruning_strategy: str = "KRUSKAL",
    exchanges: list[dict[str, Any]] | None = None,
    limit: int | None = None,
    return_type: str = "polymer_entity",
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    attributes: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    facets: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
    group_by_ranking: str | None = None,
) -> dict[str, Any]:
    """3D structural-motif search: find structures containing a geometric
    arrangement of residues like the one in a reference structure. Optionally
    AND/OR-refined with attribute filters and/or aggregated into facets.

    Distinct from build_structure_query (whole-shape similarity). `residue_ids`
    is a list of 2-10 dicts {label_asym_id, label_seq_id, struct_oper_id?}.
    Tolerances are integers in 0..3.
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    eid = str(entry_id).strip().upper()
    if not eid:
        raise ValueError("entry_id must be non-empty")
    residues = [_strucmotif_residue(r) for r in (residue_ids or [])]
    if not 2 <= len(residues) <= 10:
        raise ValueError("provide between 2 and 10 residue_ids")
    for nm, val in (
        ("backbone_distance_tolerance", backbone_distance_tolerance),
        ("side_chain_distance_tolerance", side_chain_distance_tolerance),
        ("angle_tolerance", angle_tolerance),
    ):
        if not 0 <= val <= 3:
            raise ValueError(f"{nm} must be an integer in 0..3")
    if rmsd_cutoff < 0:
        raise ValueError("rmsd_cutoff must be >= 0")
    if atom_pairing_scheme not in STRUCMOTIF_ATOM_PAIRING:
        raise ValueError(f"atom_pairing_scheme must be one of {sorted(STRUCMOTIF_ATOM_PAIRING)}")
    if motif_pruning_strategy not in STRUCMOTIF_PRUNING:
        raise ValueError(f"motif_pruning_strategy must be one of {sorted(STRUCMOTIF_PRUNING)}")
    params: dict[str, Any] = {
        "value": {"entry_id": eid, "residue_ids": residues},
        "backbone_distance_tolerance": backbone_distance_tolerance,
        "side_chain_distance_tolerance": side_chain_distance_tolerance,
        "angle_tolerance": angle_tolerance,
        "rmsd_cutoff": rmsd_cutoff,
        "atom_pairing_scheme": atom_pairing_scheme,
        "motif_pruning_strategy": motif_pruning_strategy,
    }
    if exchanges:
        params["exchanges"] = exchanges
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        params["limit"] = limit
    node = {"type": "terminal", "service": "strucmotif", "parameters": params}
    options = (_facet_options(facets) if facets
               else _request_options(start, rows, False, all_hits=all_hits, group_by=group_by, group_by_ranking=group_by_ranking, return_type=return_type, scoring_strategy="strucmotif"))
    return {
        "query": _combine_service(node, attributes, logical_operator),
        "return_type": return_type,
        "request_options": options,
    }


# --------------------------------------------------------------------------- #
# Data API GraphQL request bodies (https://data.rcsb.org/graphql)
# --------------------------------------------------------------------------- #
# Every Data API root query field is described by one DataObject below, so a
# single generic builder can construct the GraphQL body for any of them. Ids
# are passed via GraphQL variables (never interpolated), and each object ships
# a curated default field selection that callers may override.


class DataObject(NamedTuple):
    """Describes one RCSB Data API root query field."""

    root_field: str       # GraphQL query field, e.g. "assemblies"
    arg: str              # its argument name, e.g. "assembly_ids"
    batch: bool           # True -> arg is a list of ids; False -> a single id
    arg_type: str         # GraphQL scalar type of the id ("String" or "Int")
    id_format: str        # human-readable id hint, for docstrings/errors
    default_fields: str   # default selection set (without the surrounding {})
    upper: bool = True    # upper-case string ids? off for opaque group tokens


# Default selections are compact summaries; every field below is validated
# against the live schema. Pass `fields` to build_data_query to override.
DATA_OBJECTS: dict[str, DataObject] = {
    "entries": DataObject(
        "entries", "entry_ids", True, "String", 'entry IDs, e.g. "4HHB"',
        "rcsb_id struct{title} exptl{method} "
        "rcsb_entry_info{resolution_combined experimental_method molecular_weight "
        "deposited_polymer_entity_instance_count deposited_nonpolymer_entity_instance_count} "
        "rcsb_accession_info{deposit_date initial_release_date} "
        "rcsb_entry_container_identifiers{polymer_entity_ids non_polymer_entity_ids "
        "branched_entity_ids assembly_ids} "
        "rcsb_primary_citation{title rcsb_journal_abbrev year pdbx_database_id_DOI} "
        "pubmed{rcsb_pubmed_abstract_text}",
    ),
    "polymer_entities": DataObject(
        "polymer_entities", "entity_ids", True, "String",
        'polymer entity IDs (entry_entity), e.g. "4HHB_1"',
        "rcsb_id rcsb_polymer_entity{pdbx_description formula_weight pdbx_number_of_molecules} "
        "entity_poly{type rcsb_sample_sequence_length pdbx_seq_one_letter_code_can} "
        "rcsb_entity_source_organism{ncbi_scientific_name ncbi_taxonomy_id}",
    ),
    "nonpolymer_entities": DataObject(
        "nonpolymer_entities", "entity_ids", True, "String",
        'non-polymer (ligand) entity IDs, e.g. "4HHB_3"',
        "rcsb_id "
        "rcsb_nonpolymer_entity{pdbx_description formula_weight pdbx_number_of_molecules} "
        "rcsb_nonpolymer_entity_container_identifiers"
        "{entry_id entity_id nonpolymer_comp_id auth_asym_ids}",
    ),
    "branched_entities": DataObject(
        "branched_entities", "entity_ids", True, "String",
        'branched (carbohydrate) entity IDs, e.g. "5FMB_2"',
        "rcsb_id "
        "rcsb_branched_entity{pdbx_description formula_weight pdbx_number_of_molecules} "
        "pdbx_entity_branch{type rcsb_branched_component_count} "
        "rcsb_branched_entity_container_identifiers{entry_id entity_id auth_asym_ids}",
    ),
    "polymer_entity_instances": DataObject(
        "polymer_entity_instances", "instance_ids", True, "String",
        'polymer instance (chain) IDs (entry.asym), e.g. "4HHB.A"',
        "rcsb_id "
        "rcsb_polymer_entity_instance_container_identifiers"
        "{entry_id entity_id asym_id auth_asym_id} "
        "rcsb_polymer_instance_info{modeled_residue_count}",
    ),
    "nonpolymer_entity_instances": DataObject(
        "nonpolymer_entity_instances", "instance_ids", True, "String",
        'non-polymer instance IDs (entry.asym), e.g. "4HHB.E"',
        "rcsb_id "
        "rcsb_nonpolymer_entity_instance_container_identifiers"
        "{entry_id entity_id asym_id auth_asym_id comp_id auth_seq_id}",
    ),
    "branched_entity_instances": DataObject(
        "branched_entity_instances", "instance_ids", True, "String",
        'branched instance IDs (entry.asym), e.g. "5FMB.C"',
        "rcsb_id "
        "rcsb_branched_entity_instance_container_identifiers"
        "{entry_id entity_id asym_id auth_asym_id}",
    ),
    "assemblies": DataObject(
        "assemblies", "assembly_ids", True, "String",
        'assembly IDs (entry-assembly), e.g. "4HHB-1"',
        "rcsb_id "
        "rcsb_assembly_info"
        "{polymer_entity_instance_count nonpolymer_entity_instance_count polymer_composition} "
        "pdbx_struct_assembly{oligomeric_details oligomeric_count rcsb_details method_details}",
    ),
    "interfaces": DataObject(
        "interfaces", "interface_ids", True, "String",
        'interface IDs (entry-assembly.interface), e.g. "1BMV-1.1"',
        "rcsb_id "
        "rcsb_interface_info"
        "{interface_area interface_character polymer_composition num_interface_residues} "
        "rcsb_interface_container_identifiers{entry_id assembly_id interface_id}",
    ),
    "chem_comps": DataObject(
        "chem_comps", "comp_ids", True, "String",
        'chemical component / ligand IDs, e.g. "HEM", "ATP"',
        "rcsb_id chem_comp{name formula formula_weight type} "
        "rcsb_chem_comp_descriptor{SMILES InChIKey}",
    ),
    "entry_groups": DataObject(
        "entry_groups", "group_ids", True, "String", "entry group IDs",
        "rcsb_id rcsb_group_info{group_name group_description group_members_count} "
        "rcsb_group_container_identifiers{group_id group_member_ids}",
        upper=False,
    ),
    "polymer_entity_groups": DataObject(
        "polymer_entity_groups", "group_ids", True, "String",
        'polymer entity group IDs, e.g. "85_70" (sequence cluster)',
        "rcsb_id rcsb_group_info{group_name group_description group_members_count} "
        "rcsb_group_container_identifiers{group_id group_member_ids}",
        upper=False,
    ),
    "nonpolymer_entity_groups": DataObject(
        "nonpolymer_entity_groups", "group_ids", True, "String",
        "non-polymer entity group IDs",
        "rcsb_id rcsb_group_info{group_name group_description group_members_count} "
        "rcsb_group_container_identifiers{group_id group_member_ids}",
        upper=False,
    ),
    "uniprot": DataObject(
        "uniprot", "uniprot_id", False, "String", 'a UniProt accession, e.g. "P69905"',
        "rcsb_id rcsb_uniprot_accession rcsb_uniprot_entry_name "
        "rcsb_uniprot_protein{name{value} gene{name{value}} ec{number} function{details} "
        "source_organism{scientific_name}} "
        "rcsb_uniprot_keyword{id value}",
    ),
    "pubmed": DataObject(
        "pubmed", "pubmed_id", False, "Int", "a PubMed integer ID, e.g. 6726807",
        "rcsb_id rcsb_pubmed_central_id rcsb_pubmed_doi rcsb_pubmed_abstract_text "
        "rcsb_pubmed_mesh_descriptors",
    ),
    "group_provenance": DataObject(
        "group_provenance", "group_provenance_id", False, "String",
        'a group provenance ID, e.g. "provenance_sequence_identity"',
        "rcsb_id rcsb_group_aggregation_method{type} "
        "rcsb_group_provenance_container_identifiers{group_provenance_id}",
        upper=False,
    ),
    "entry_annotations": DataObject(
        "entries", "entry_ids", True, "String", 'entry IDs, e.g. "4HHB"',
        ENTRY_ANNOTATIONS
    ),
    "entry_exp_info": DataObject(
        "entries", "entry_ids", True, "String", 'entry IDs, e.g. "4HHB"',
        ENTRY_EXP_INFO
    )
}


def _clean_id_list(ids: list[str], upper: bool = True) -> list[str]:
    """Strip (optionally upper-case) and validate a list of identifiers."""
    cleaned = [
        (str(i).strip().upper() if upper else str(i).strip())
        for i in (ids or [])
        if str(i).strip()
    ]
    if not cleaned:
        raise ValueError("provide at least one non-empty id")
    return cleaned


def _normalize_fields(fields: str | None) -> str | None:
    """Accept a GraphQL selection written with dotted paths, braces, or a mix.

    The whole search side of this server speaks dotted attribute paths
    (e.g. "rcsb_polymer_entity.pdbx_description"), so agents naturally write the
    same into the Data API `fields` override — but GraphQL needs nested braces
    ("rcsb_polymer_entity { pdbx_description }") and rejects the dot with a syntax
    error. This normalizes both dialects: each whitespace-separated path is
    expanded ("a.b.c" -> "a { b { c } }") and shared prefixes are merged, while
    already-braced input passes through re-serialized.

    Anything using GraphQL we don't model — arguments, aliases, directives,
    fragments — is returned unchanged, so the raw selection still works verbatim.
    """
    if not fields or not fields.strip():
        return fields
    if "." not in fields:
        return fields  # already a GraphQL selection (or plain names) — leave verbatim
    if any(ch in fields for ch in "():@") or "..." in fields:
        return fields  # dotted but also advanced GraphQL: don't risk mangling it

    # Tokenize into NAME / DOT / LBRACE / RBRACE (whitespace separates).
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(fields)
    while i < n:
        ch = fields[i]
        if ch.isspace():
            i += 1
        elif ch in "{}.":
            tokens.append(({"{": "LBRACE", "}": "RBRACE", ".": "DOT"}[ch], ch))
            i += 1
        elif ch.isalnum() or ch == "_":
            j = i
            while j < n and (fields[j].isalnum() or fields[j] == "_"):
                j += 1
            tokens.append(("NAME", fields[i:j]))
            i = j
        else:
            return fields  # unexpected character: don't risk mangling it

    def _merge(dst: dict, src: dict) -> None:
        for key, sub in src.items():
            _merge(dst.setdefault(key, {}), sub)

    pos = 0

    def _selection() -> dict:
        nonlocal pos
        tree: dict = {}
        while pos < len(tokens) and tokens[pos][0] != "RBRACE":
            if tokens[pos][0] != "NAME":
                raise ValueError("expected a field name")
            names = [tokens[pos][1]]
            pos += 1
            while pos < len(tokens) and tokens[pos][0] == "DOT":
                pos += 1
                if pos >= len(tokens) or tokens[pos][0] != "NAME":
                    raise ValueError("expected a field name after '.'")
                names.append(tokens[pos][1])
                pos += 1
            children: dict = {}
            if pos < len(tokens) and tokens[pos][0] == "LBRACE":
                pos += 1
                children = _selection()
                if pos >= len(tokens) or tokens[pos][0] != "RBRACE":
                    raise ValueError("missing closing '}'")
                pos += 1
            node = tree
            for nm in names[:-1]:
                node = node.setdefault(nm, {})
            _merge(node.setdefault(names[-1], {}), children)
        return tree

    def _render(tree: dict) -> str:
        return " ".join(
            f"{name} {{ {_render(sub)} }}" if sub else name
            for name, sub in tree.items()
        )

    try:
        tree = _selection()
        if pos != len(tokens):
            raise ValueError("unbalanced '}'")
    except ValueError:
        return fields  # malformed in our dialect: hand back as-is

    return _render(tree)


def build_data_query(
    object_key: str, ids: Any, fields: str | None = None
) -> dict[str, Any]:
    """Build a Data API GraphQL body for any object in DATA_OBJECTS.

    Args:
        object_key: A key of DATA_OBJECTS (e.g. "entries", "assemblies").
        ids: A list of ids for batch objects, or a single id for singletons.
        fields: Optional selection set to use instead of the curated default (omit
            the surrounding braces). Accepts GraphQL braces ("rcsb_id struct{title}"),
            dotted paths ("rcsb_id struct.title"), or a mix — see _normalize_fields.

    Returns a {"query", "variables"} dict; ids ride in the "ids" variable.
    """
    try:
        spec = DATA_OBJECTS[object_key]
    except KeyError:
        raise ValueError(
            f"unknown object {object_key!r}; one of {sorted(DATA_OBJECTS)}"
        ) from None

    selection = _normalize_fields(fields) or spec.default_fields
    if spec.batch:
        var_type = f"[{spec.arg_type}!]!"
        id_list = ids if isinstance(ids, (list, tuple)) else [ids]
        variables: dict[str, Any] = {"ids": _clean_id_list(id_list, upper=spec.upper)}
    else:
        var_type = f"{spec.arg_type}!"
        value = ids[0] if isinstance(ids, (list, tuple)) else ids
        if spec.arg_type == "Int":
            variables = {"ids": int(value)}
        else:
            cleaned = str(value).strip()
            if not cleaned:
                raise ValueError("provide a non-empty id")
            variables = {"ids": cleaned.upper() if spec.upper else cleaned}

    query = (
        f"query Q($ids: {var_type}) {{ "
        f"{spec.root_field}({spec.arg}: $ids) {{ {selection} }} "
        f"}}"
    )
    return {"query": query, "variables": variables}


# --------------------------------------------------------------------------- #
# Sequence Coordinates API GraphQL bodies (https://sequence-coordinates.rcsb.org/graphql)
# --------------------------------------------------------------------------- #
# This API maps alignments and positional annotations between sequence reference
# systems (UniProt, NCBI RefSeq protein/genome, PDB entity/instance) — it is the
# only RCSB API that cross-references NCBI. Each builder returns a
# {"query", "variables"} dict; enum arguments are validated against the schema
# and ids ride in GraphQL variables. Pass `fields` to override the selection.

# Reference systems a query/target sequence can be expressed in.
SEQUENCE_REFERENCES = {"NCBI_GENOME", "NCBI_PROTEIN", "PDB_ENTITY", "PDB_INSTANCE", "UNIPROT"}
# How a group of related sequences is defined.
GROUP_REFERENCES = {"MATCHING_UNIPROT_ACCESSION", "SEQUENCE_IDENTITY"}
# Annotation provenance/scope.
ANNOTATION_REFERENCES = {"PDB_ENTITY", "PDB_INSTANCE", "PDB_INTERFACE", "UNIPROT"}

SC_ALIGNMENTS_FIELDS = (
    "query_sequence alignment_length "
    "target_alignments{ target_id orientation "
    "coverage{ query_coverage query_length target_coverage target_length } "
    "aligned_regions{ query_begin query_end target_begin target_end exon_shift } }"
)
SC_ANNOTATIONS_FIELDS = (
    "source target_id "
    "target_identifiers{ entry_id entity_id asym_id assembly_id interface_id "
    "interface_partner_index uniprot_id } "
    "features{ type feature_id name description provenance_source value "
    "feature_positions{ beg_seq_id end_seq_id beg_ori_id end_ori_id value } }"
)


def _require_enum(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")
    return value


def _check_sources(sources: list[str]) -> list[str]:
    if not sources:
        raise ValueError("provide at least one annotation source")
    for s in sources:
        _require_enum(s, ANNOTATION_REFERENCES, "source")
    return list(sources)


def _clean_range(seq_range: Any) -> list[int] | None:
    if seq_range is None:
        return None
    try:
        return [int(x) for x in seq_range]
    except (TypeError, ValueError):
        raise ValueError("range must be a list of integers, e.g. [1, 120]") from None


def build_sc_alignments_query(
    query_id: str,
    from_ref: str,
    to_ref: str,
    seq_range: Any = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Alignments mapping `query_id` from one reference system to another.

    Cross-references identifiers across UNIPROT, NCBI_PROTEIN, NCBI_GENOME,
    PDB_ENTITY, and PDB_INSTANCE. PDB ids must be entity/instance level
    ("4HHB_1" / "4HHB.A"), not a bare entry.

    Examples:
        query_id="4HHB_1", from_ref="PDB_ENTITY", to_ref="NCBI_PROTEIN"
        query_id="P69905", from_ref="UNIPROT", to_ref="PDB_ENTITY"
    """
    _require_enum(from_ref, SEQUENCE_REFERENCES, "from_ref")
    _require_enum(to_ref, SEQUENCE_REFERENCES, "to_ref")
    qid = str(query_id).strip()
    if not qid:
        raise ValueError("query_id must be a non-empty string")
    selection = _normalize_fields(fields) or SC_ALIGNMENTS_FIELDS
    query = (
        "query A($from: SequenceReference!, $to: SequenceReference!, "
        "$queryId: String!, $range: [Int!]) { "
        f"alignments(from: $from, to: $to, queryId: $queryId, range: $range) {{ {selection} }} "
        "}"
    )
    return {
        "query": query,
        "variables": {"from": from_ref, "to": to_ref, "queryId": qid, "range": _clean_range(seq_range)},
    }


def build_sc_annotations_query(
    query_id: str,
    reference: str,
    sources: list[str],
    seq_range: Any = None,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Positional annotations for `query_id` in a given reference system.

    Example: query_id="4HHB_1", reference="PDB_ENTITY", sources=["UNIPROT"].
    """
    _require_enum(reference, SEQUENCE_REFERENCES, "reference")
    srcs = _check_sources(sources)
    qid = str(query_id).strip()
    if not qid:
        raise ValueError("query_id must be a non-empty string")
    selection = _normalize_fields(fields) or SC_ANNOTATIONS_FIELDS
    query = (
        "query An($queryId: String!, $reference: SequenceReference!, "
        "$sources: [AnnotationReference]!, $range: [Int!], $filters: [AnnotationFilterInput!]) { "
        "annotations(queryId: $queryId, reference: $reference, sources: $sources, "
        f"range: $range, filters: $filters) {{ {selection} }} "
        "}"
    )
    return {
        "query": query,
        "variables": {
            "queryId": qid,
            "reference": reference,
            "sources": srcs,
            "range": _clean_range(seq_range),
            "filters": filters,
        },
    }


def build_sc_group_alignments_query(
    group: str,
    group_id: str,
    filter_terms: list[str] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Alignments among the members of a sequence group.

    Example: group="MATCHING_UNIPROT_ACCESSION", group_id="P69905".
    """
    _require_enum(group, GROUP_REFERENCES, "group")
    gid = str(group_id).strip()
    if not gid:
        raise ValueError("group_id must be a non-empty string")
    selection = _normalize_fields(fields) or SC_ALIGNMENTS_FIELDS
    query = (
        "query GA($group: GroupReference!, $groupId: String!, $filter: [String!]) { "
        f"group_alignments(group: $group, groupId: $groupId, filter: $filter) {{ {selection} }} "
        "}"
    )
    return {
        "query": query,
        "variables": {"group": group, "groupId": gid, "filter": filter_terms},
    }


def build_sc_group_annotations_query(
    group: str,
    group_id: str,
    sources: list[str],
    summary: bool = False,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Annotations across a sequence group (or a positional summary if summary=True).

    Example: group="MATCHING_UNIPROT_ACCESSION", group_id="P69905",
             sources=["UNIPROT"].
    """
    _require_enum(group, GROUP_REFERENCES, "group")
    srcs = _check_sources(sources)
    gid = str(group_id).strip()
    if not gid:
        raise ValueError("group_id must be a non-empty string")
    root_field = "group_annotations_summary" if summary else "group_annotations"
    selection = _normalize_fields(fields) or SC_ANNOTATIONS_FIELDS
    query = (
        "query GAn($group: GroupReference!, $groupId: String!, "
        "$sources: [AnnotationReference]!, $filters: [AnnotationFilterInput!]) { "
        f"{root_field}(group: $group, groupId: $groupId, sources: $sources, "
        f"filters: $filters) {{ {selection} }} "
        "}"
    )
    return {
        "query": query,
        "variables": {"group": group, "groupId": gid, "sources": srcs, "filters": filters},
    }
