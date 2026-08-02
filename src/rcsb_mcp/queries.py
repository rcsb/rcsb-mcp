"""Pure helpers that build RCSB Search API v2 and Data API GraphQL request bodies.

These functions contain *no* network code so they can be unit-tested in
isolation. Search builders return a dict ready to be POSTed to
https://search.rcsb.org/rcsbsearch/v2/query ; the GraphQL builders return a
``{"query", "variables"}`` dict ready to be POSTed to
https://data.rcsb.org/graphql
"""
from __future__ import annotations

from typing import Any, NamedTuple, get_args

from rcsb_mcp.attribute_scopes import (
    CHEMICAL_ATTRIBUTE_ENTRY_CONSTANT,
    CHEMICAL_ATTRIBUTE_NESTED_ROOTS,
    CHEMICAL_ATTRIBUTE_REPEATING_ROOTS,
    CHEMICAL_ATTRIBUTE_SCOPES,
    SEARCH_ATTRIBUTE_ENTRY_CONSTANT,
    SEARCH_ATTRIBUTE_NESTED_ROOTS,
    SEARCH_ATTRIBUTE_REPEATING_ROOTS,
    SEARCH_ATTRIBUTE_SCOPES,
)
from rcsb_mcp.attribute_types import AttributeScope, TextOperator
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES
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

# The full set of attribute/text comparison operators from the spec enum. Derived from
# the TextOperator Literal (rcsb_mcp.attribute_types) so the runtime membership check
# and the tool-schema enum can never disagree.
TEXT_OPERATORS = frozenset(get_args(TextOperator))

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


def _sort_clause(sort_by: str, sort_direction: str, return_type: str | None) -> dict[str, str]:
    """One request_options.sort entry for a caller-specified ordering.

    Sorting is a Search-API request option honored across every service (text, sequence,
    structure, seqmotif, strucmotif, ...), but only for attributes that are indexed for
    sorting: those exposing the ``exact_match`` (string) or ``equals`` (number/date)
    operator in the search schema (see rcsb_list_pdb_search_attributes). Full-text-only
    attributes (e.g. ``struct.title``) are rejected by the API. The one service-level
    limit is ``return_type="mol_definition"`` (chemical-component definitions), whose
    result set is ranked by score only — caught here with a clearer error than the raw 400.
    """
    if return_type == "mol_definition":
        raise ValueError(
            'sort_by is not supported with return_type="mol_definition": chemical-component '
            "results are ranked by relevance score only. Choose an entry/entity/assembly "
            "return_type to sort by an attribute, or omit sort_by."
        )
    if sort_direction not in {"asc", "desc"}:
        raise ValueError('sort_direction must be "asc" or "desc"')
    return {"sort_by": sort_by, "direction": sort_direction}


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
    sort_by: str | None = None,
    sort_direction: str = "asc",
) -> dict[str, Any]:
    """Common request_options block: pagination, content type, sort, grouping.

    When `all_hits` is True the query returns the COMPLETE result set
    (`return_all_hits`) and pagination is omitted; otherwise it pages with start/rows.
    `group_by` (see GROUP_BY_METHODS) collapses redundant polymer_entity hits into
    clusters and returns one representative each, chosen by `group_by_ranking` (see
    GROUP_BY_RANKING_SORTS — each ranking has a fixed direction). Requiring
    return_type=polymer_entity is the caller's responsibility.

    Results are ordered by score (descending) by default; passing `sort_by` (an attribute
    path) replaces that with an attribute ordering — see _sort_clause for the constraints.
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
            # NB: distinct names — must not shadow the sort_by/sort_direction params,
            # which drive the independent top-level result ordering below.
            rank_by, rank_dir = GROUP_BY_RANKING_SORTS[group_by_ranking]
            gb["ranking_criteria_type"] = {"sort_by": rank_by, "direction": rank_dir}
        options["group_by"] = gb
        options["group_by_return_type"] = "representatives"
    if sort_by:
        options["sort"] = [_sort_clause(sort_by, sort_direction, return_type)]
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


# --------------------------------------------------------------------------- #
# Composable query nodes
#
# The rcsb_query_* tools each build ONE node here; rcsb_query_composer joins nodes;
# rcsb_search_request turns a node plus the result-shaping envelope into a request
# body. The build_*_query functions below are the pre-composer entry points and now
# delegate to these, so the two paths cannot drift (tests/test_query_baseline.py
# renders all 37 baseline cases both ways and requires byte-identical bodies).
# --------------------------------------------------------------------------- #

# Service -> the scoring_strategy its results are ranked by. seqmotif is deliberately
# ABSENT: it has never set one, so it takes the API default, and reproducing that
# exactly is what keeps the composer path byte-identical to the old builders.
SERVICE_SCORING: dict[str, str] = {
    "sequence": "sequence",
    "chemical": "chemical",
    "structure": "structure",
    "strucmotif": "strucmotif",
}

# Service -> the return_type that service implies when the caller does not name one.
# The `structure` service is absent because its default depends on the reference:
# a chain reference returns instances, an assembly reference returns assemblies (see
# default_return_type_for). Getting this wrong is silent -- the search succeeds and
# returns the wrong KIND of identifier -- which is why return_type must stay None
# until it is resolved here rather than defaulting to "entry" in a signature.
SERVICE_RETURN_TYPE: dict[str, str] = {
    "sequence": "polymer_entity",
    "seqmotif": "polymer_entity",
    "chemical": "mol_definition",
    "strucmotif": "assembly",
}

# Services that refine a query rather than drive it; they never pick the return type
# or the scoring strategy.
REFINEMENT_SERVICES = frozenset({"text", "text_chem", "full_text"})


def _nested_record_of(attribute: str, service: str) -> str | None:
    """The nested-indexed record `attribute` belongs to, or None.

    The SHALLOWEST matching path, not the deepest: nested paths nest inside each other
    (`rcsb_polymer_entity_annotation` and its `.annotation_lineage`), and a condition on
    `.type` and one on `.annotation_lineage.id` describe the same ANNOTATION. Keying them
    to different records would let them be split apart, which is the exact defect this
    exists to prevent.
    """
    paths = CHEMICAL_ATTRIBUTE_NESTED_ROOTS if service == "text_chem" else SEARCH_ATTRIBUTE_NESTED_ROOTS
    matches = [p for p in paths if attribute == p or attribute.startswith(p + ".")]
    return min(matches, key=len) if matches else None


def _pins_a_nested_record(group: dict[str, Any]) -> bool:
    """Whether this group holds 2+ conditions on ONE nested-indexed record.

    Only the group's own terminal children count: splicing moves them into the parent,
    while any sub-group keeps its own nesting and its own coherence.
    """
    seen: dict[tuple[str, str], int] = {}
    for child in group.get("nodes") or []:
        if not isinstance(child, dict) or child.get("type") != "terminal":
            continue
        service = child.get("service")
        if service not in ("text", "text_chem"):
            continue
        attribute = (child.get("parameters") or {}).get("attribute")
        record = _nested_record_of(attribute, service) if attribute else None
        if record is None:
            continue
        key = (service, record)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 2:
            return True
    return False


def group_node(nodes: list[dict[str, Any]], logical_operator: str = "and") -> dict[str, Any]:
    """Join nodes with one AND/OR, collapsing what does not need to nest.

    Two normalisations that keep composed trees shallow:

    * a single node needs no group and is returned as-is;
    * a child group sharing this group's operator is SPLICED IN rather than nested,
      because AND/OR are associative -- ``and(a, and(b, c))`` is ``and(a, b, c)``.

    The splice keeps an iterative composer from growing a tower of same-operator wrappers
    that would hit the depth cap for no reason. A child with the OPPOSITE operator is
    never spliced: that nesting is the whole point of the composer.

    BUT associativity is not the whole story, and a group that pins two conditions to one
    NESTED-INDEXED record is never spliced. For the 41 paths the Search API nested-indexes,
    a group is also the record-coherence scope: conditions inside it must hold on the SAME
    sub-record, and flattening them only requires each to hold SOMEWHERE in the object.
    That turns a restriction into a relaxation, so the count can go UP -- which no correct
    AND can do. Measured at return_type=entry, before this carve-out:

        citation.journal=Nature AND citation.year=1995            137
          spliced with exptl.method=X-RAY                         298   <- larger
          kept nested                                             124
        binding_affinity.comp_id=PTR AND .type=IC50                 0   (PTR only has Kd)
          spliced with exptl.method=X-RAY                           5   <- all false
        polymer_entity_annotation.type=Pfam AND .annotation_id=GO:0004672
                                                                    0
          spliced with exptl.method=X-RAY                       3,846   <- all false

    Verified against the Data API: none of those hits carry both conditions on one record.
    """
    if logical_operator not in {"and", "or"}:
        raise ValueError('logical_operator must be "and" or "or"')
    if not nodes:
        raise ValueError("provide at least one query to compose")
    flat: list[dict[str, Any]] = []
    for node in nodes:
        if (
            isinstance(node, dict)
            and node.get("type") == "group"
            and node.get("logical_operator") == logical_operator
            and not _pins_a_nested_record(node)
        ):
            flat.extend(node["nodes"])
        else:
            flat.append(node)
    if len(flat) == 1:
        return flat[0]
    return {"type": "group", "logical_operator": logical_operator, "nodes": flat}


def fulltext_node(value: str) -> dict[str, Any]:
    """A free-text terminal matched against all text annotations."""
    if not value or not value.strip():
        raise ValueError("provide a non-empty search term")
    return {"type": "terminal", "service": "full_text", "parameters": {"value": value}}


def attribute_node(
    filters: list[dict[str, Any]],
    logical_operator: str = "and",
    chemical: bool = False,
) -> dict[str, Any]:
    """One or more structured attribute conditions joined by a single AND/OR."""
    if not filters:
        raise ValueError("provide at least one attribute condition")
    service = "text_chem" if chemical else "text"
    return group_node(
        [
            _text_node(
                f["attribute"], f.get("operator"), f.get("value"), service=service,
                negation=f.get("negation", False),
                case_sensitive=f.get("case_sensitive", False),
            )
            for f in filters
        ],
        logical_operator,
    )


def sequence_node(
    sequence: str,
    sequence_type: str = "protein",
    identity_cutoff: float = 0.3,
    evalue_cutoff: float = 1.0,
) -> dict[str, Any]:
    """MMseqs2 sequence-similarity terminal (BLAST-like)."""
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    if not 0.0 <= identity_cutoff <= 1.0:
        raise ValueError("identity_cutoff must be between 0 and 1")
    return {
        "type": "terminal",
        "service": "sequence",
        "parameters": {
            "value": sequence.strip().upper(),
            "sequence_type": sequence_type,
            "identity_cutoff": identity_cutoff,
            "evalue_cutoff": evalue_cutoff,
        },
    }


def chemical_node(
    value: str,
    query_type: str = "descriptor",
    descriptor_type: str = "SMILES",
    match_type: str = "graph-relaxed",
    match_subset: bool = False,
) -> dict[str, Any]:
    """Chemical terminal: a SMILES/InChI descriptor match, or a formula match."""
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
    return {"type": "terminal", "service": "chemical", "parameters": params}


def structure_node(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
) -> dict[str, Any]:
    """3D shape-similarity terminal, referencing an assembly or a single chain."""
    if assembly_id and asym_id:
        raise ValueError("provide assembly_id or asym_id, not both")
    eid = entry_id.strip().upper()
    if asym_id:
        value: dict[str, Any] = {"entry_id": eid, "asym_id": str(asym_id)}
    else:
        value = {"entry_id": eid, "assembly_id": str(assembly_id or "1")}
    return {"type": "terminal", "service": "structure", "parameters": {"value": value}}


def seqmotif_node(
    pattern: str,
    pattern_type: str = "prosite",
    sequence_type: str = "protein",
) -> dict[str, Any]:
    """Short sequence-motif terminal (PROSITE pattern, regex, or simple wildcards)."""
    if pattern_type not in SEQMOTIF_PATTERN_TYPES:
        raise ValueError(f"pattern_type must be one of {sorted(SEQMOTIF_PATTERN_TYPES)}")
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    return {
        "type": "terminal",
        "service": "seqmotif",
        "parameters": {
            "value": pattern.strip(),
            "pattern_type": pattern_type,
            "sequence_type": sequence_type,
        },
    }


def strucmotif_node(
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
) -> dict[str, Any]:
    """Structural-motif terminal: a geometric arrangement of 2-10 residues."""
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
    return {"type": "terminal", "service": "strucmotif", "parameters": params}


def driving_services(node: dict[str, Any]) -> list[str]:
    """The non-refinement services in a query tree, in encounter order.

    A composed query can mix services (a sequence match AND a shape match), which the
    flat tools could never express -- so both the scoring strategy and the default
    return type have to be derived from the tree rather than known by one builder.
    """
    found: list[str] = []

    def walk(n: Any) -> None:
        if not isinstance(n, dict):
            return
        if n.get("type") == "group":
            for child in n.get("nodes") or []:
                walk(child)
        else:
            service = n.get("service")
            if service and service not in REFINEMENT_SERVICES:
                found.append(service)

    walk(node)
    return found


def uses_chemical_attributes(node: dict[str, Any]) -> bool:
    """Whether a query filters on the chemical-component catalog (the text_chem service).

    rcsb_search_request validates `sort_by` and `facets` paths against one catalog, and
    only the query itself says which: the flat tools took a `chemical` flag, the composer
    has to read it back off the tree.
    """
    return any(t.get("service") == "text_chem" for t in _terminals(node))


def scope_of(attribute: str, service: str = "text") -> AttributeScope | None:
    """The object `attribute` hangs off — entry, assembly, an entity, an instance, or a
    chemical definition.

    This is the fact needed to tell whether ANDed conditions can be satisfied by
    DIFFERENT objects: the Search API intersects at the level named by `return_type`, not
    at the level the attributes live at, so two polymer-entity conditions asked for as
    entries match when one molecule carries the annotation and another supplies the
    organism. Measured on AND(source_organism="Homo sapiens", source_organism="Escherichia
    coli"): 745 entries but 550 entities, so 195 entries — 26% — are cross-molecule.

    `service` picks the catalog, because the two disagree: `rcsb_id` is the entity
    container in the structure schema and the chemical definition in the chemical one.

    Returns None when the attribute is not in that catalog. Callers must treat that as
    "unknown", never as a scope — an unrecognised path is usually a typo, and guessing a
    scope for one would put a confident claim behind a value the API will reject anyway.
    """
    chemical = service == "text_chem"
    entry_constant = CHEMICAL_ATTRIBUTE_ENTRY_CONSTANT if chemical else SEARCH_ATTRIBUTE_ENTRY_CONSTANT
    if attribute in entry_constant:
        return "entry"
    scopes = CHEMICAL_ATTRIBUTE_SCOPES if chemical else SEARCH_ATTRIBUTE_SCOPES
    return scopes.get(attribute.split(".")[0])


# The containment the SEARCH INDEX implements — which is NOT the PDB structural hierarchy.
#
# Structurally the PDB nests entry > assembly > entity > instance: an assembly really does
# hold a subset of the entry's instances. The index does not follow that. Entities hang off
# the ENTRY, and nothing is indexed as being "inside" an assembly, so a match anywhere in
# the entry lights up EVERY assembly of it. Measured on 1DEE (S. aureus protein A bound to
# a human IgM Fab), whose five assemblies genuinely differ:
#
#     1DEE-1  chains A,B    entities 1,2    Homo sapiens only
#     1DEE-2  chains C,D,G  entities 1,2,3  + Staphylococcus aureus
#     1DEE-3  chains E,F,H  entities 1,2,3  + Staphylococcus aureus
#     1DEE-4  chains E,F    entities 1,2    Homo sapiens only
#     1DEE-5  chains C,D    entities 1,2    Homo sapiens only
#
#     organism="Staphylococcus aureus"      @assembly -> all five, incl. the three with none
#     auth_asym_id=G (present ONLY in 1DEE-2) @assembly -> all five
#                                             @polymer_instance -> 1DEE.G alone
#
# So assembly is a LEAF here, not a container. Along entry > entity > instance the index
# does respect containment: the same instance probe returned 0 false positives in 200.
_INDEX_PARENT: dict[str, str] = {
    "assembly": "entry",
    # Entities and chemical definitions hang off the entry, never off an assembly.
    "polymer_entity": "entry",
    "non_polymer_entity": "entry",
    "branched_entity": "entry",
    "mol_definition": "entry",
    "polymer_instance": "polymer_entity",
    "non_polymer_instance": "non_polymer_entity",
    "branched_instance": "branched_entity",
}


def scope_contains(outer: str, inner: str) -> bool:
    """Whether `outer` strictly contains `inner` in the SEARCH INDEX (not structurally).

    Strict: a scope does not contain itself. Following _INDEX_PARENT upward, so
    entry contains every scope, polymer_entity contains polymer_instance, and assembly
    contains nothing at all — see the measurements on _INDEX_PARENT.
    """
    seen = set()
    cursor = _INDEX_PARENT.get(inner)
    while cursor and cursor not in seen:
        if cursor == outer:
            return True
        seen.add(cursor)
        cursor = _INDEX_PARENT.get(cursor)
    return False


def scopes_are_comparable(a: str, b: str) -> bool:
    """Whether one scope contains the other, or they are the same.

    Comparable scopes are the safe case for a LONE condition: every object of the finer
    scope belongs to exactly one object of the coarser one, so projecting a match in
    either direction cannot invent a hit. Incomparable scopes (assembly against an entity
    or instance) can, which is what `answers_at_entry_level` is for.
    """
    return a == b or scope_contains(a, b) or scope_contains(b, a)


def answers_at_entry_level(return_type: str, scope: str) -> bool:
    """Whether asking for `return_type` will answer a `scope` condition at ENTRY level and
    project the result onto every assembly of that entry, whatever that assembly holds.

    True only for return_type="assembly" with a condition finer than the entry. There is
    no query shape that fixes it and no return_type that tightens it: the honest reading
    of such a result is "assemblies of ENTRIES that match", not "assemblies that match".

    One condition is enough — this needs no AND, which is what separates it from the
    cross-object case.
    """
    return (
        return_type == "assembly"
        and scope not in ("entry", "assembly")
        and scope in _INDEX_PARENT
    )


MAX_INTERSECTION_NOTES = 3


def _and_groups(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Every AND group in the tree.

    ONLY "and" groups. Under OR, different objects satisfying different conditions is
    precisely what was asked for, so there is nothing to report.
    """
    found: list[dict[str, Any]] = []

    def walk(n: dict[str, Any]) -> None:
        if not isinstance(n, dict) or n.get("type") != "group":
            return
        if n.get("logical_operator") == "and":
            found.append(n)
        for child in n.get("nodes") or []:
            walk(child)

    walk(node)
    return found


def _attribute_terminals(group: dict[str, Any]) -> list[dict[str, Any]]:
    """A group's DIRECT attribute terminals.

    Direct children only: a sub-group is its own intersection scope and is walked on its
    own turn, so its terminals must not be judged as siblings of this group's.
    """
    return [
        c for c in (group.get("nodes") or [])
        if isinstance(c, dict) and c.get("type") == "terminal"
        and c.get("service") in ("text", "text_chem")
        and (c.get("parameters") or {}).get("attribute")
    ]


def _terminal_scope(terminal: dict[str, Any]) -> tuple[str, str, AttributeScope | None]:
    attribute = terminal["parameters"]["attribute"]
    service = terminal.get("service", "text")
    return attribute, service, scope_of(attribute, service)


def intersection_notes(node: dict[str, Any], return_type: str) -> list[str]:
    """Where this query's conditions are intersected more loosely than they read.

    The Search API intersects at the level named by `return_type`, and within an object it
    intersects across repeated records. Neither is visible in the response, so a too-loose
    answer looks exactly like a correct one. Each note below fires only in its own case and
    costs nothing otherwise — the silence is as load-bearing as the text, because a note on
    every query trains the reader to skip it.

    Three findings, in descending order of what the caller can do about them:

    1. two comparable conditions finer than return_type -- FIXABLE by return_type
    2. conditions on one repeated record -- fixable only if the API nested-indexes it
    3. return_type="assembly" with anything finer -- NOT fixable at all

    Returns [] when nothing applies, which is the common case.
    """
    notes: list[str] = []
    seen: set[str] = set()

    def add(note: str) -> None:
        # Capped: a wall of notes reads as boilerplate and gets skipped whole, which
        # costs more than the notes past the cap were worth.
        if note not in seen and len(notes) < MAX_INTERSECTION_NOTES:
            seen.add(note)
            notes.append(note)

    for group in _and_groups(node):
        terminals = _attribute_terminals(group)
        scoped = [(a, s, sc) for a, s, sc in map(_terminal_scope, terminals) if sc]

        # 1. Two conditions finer than return_type that COULD describe one object.
        #    Incomparable scopes are skipped: "a human protein and an ATP ligand" is two
        #    different objects by definition and flagging it would be noise.
        for i, (attr_a, _, scope_a) in enumerate(scoped):
            for attr_b, _, scope_b in scoped[i + 1:]:
                if not (scope_contains(return_type, scope_a) and scope_contains(return_type, scope_b)):
                    continue
                if not scopes_are_comparable(scope_a, scope_b):
                    continue
                finer = scope_b if scope_contains(scope_a, scope_b) else scope_a
                if finer not in RETURN_TYPES:
                    continue
                subject = (f'Two conditions on `{attr_a}`' if attr_a == attr_b
                           else f'`{attr_a}` and `{attr_b}`')
                add(
                    f'{subject} are {finer}-scoped but return_type is "{return_type}", so a '
                    f'DIFFERENT {finer} can satisfy each one. Use return_type="{finer}" to '
                    f'require the same one.'
                )

        # 2. Two conditions on one repeated record inside a single object.
        by_root: dict[tuple[str, str], list[str]] = {}
        for attr, service, _ in scoped:
            by_root.setdefault((service, attr.split(".")[0]), []).append(attr)
        for (service, root), attrs in by_root.items():
            if len(attrs) < 2:
                continue
            repeating = (CHEMICAL_ATTRIBUTE_REPEATING_ROOTS if service == "text_chem"
                         else SEARCH_ATTRIBUTE_REPEATING_ROOTS)
            if root not in repeating:
                continue
            subject = (f'Two conditions on `{attrs[0]}`' if attrs[0] == attrs[1]
                       else f'`{attrs[0]}` and `{attrs[1]}`')
            if _nested_record_of(attrs[0], service):
                # Nested-indexed: the API DOES keep such a pair on one record, but only
                # while it is ALONE in its group. Measured on a pair that can never
                # co-occur (rcsb_binding_affinity comp_id=PTR + type=IC50, correct answer
                # 0 everywhere):
                #     and[PTR, IC50]              -> 0   alone, coherent
                #     and[PTR, IC50, XRAY]        -> 5   one foreign terminal breaks it
                #     and[ and[PTR,IC50], XRAY ]  -> 0   own group, coherent again
                # So the note fires only when something else shares the group -- and it
                # has an exact fix, which is why it names one.
                if len(group.get("nodes") or []) <= len(attrs):
                    continue
                add(
                    f'{subject} share a group with other conditions, so they can match '
                    f'DIFFERENT {root} records of the same object. Put them in ONE '
                    f'rcsb_query_attribute call to require the same record.'
                )
            else:
                add(
                    f'One object holds many {root} records, and the Search API cannot '
                    f'require {subject[0].lower() + subject[1:]} to hold on the SAME one. '
                    f'No return_type or query shape changes this.'
                )

    # 3. Assembly. This one needs no AND, no second condition and no group at all, so it
    #    walks EVERY terminal rather than the AND groups -- a lone attribute query with
    #    return_type="assembly" is the simplest case that triggers it.
    if return_type == "assembly":
        for terminal in _terminals(node):
            if (terminal.get("service") not in ("text", "text_chem")
                    or not (terminal.get("parameters") or {}).get("attribute")):
                continue
            attr, _, scope = _terminal_scope(terminal)
            if scope and answers_at_entry_level(return_type, scope):
                add(
                    f'`{attr}` is {scope}-scoped, and return_type="assembly" answers it at '
                    f'ENTRY level: every assembly of a matching entry is returned, including '
                    f'assemblies that do not contain the match. No return_type narrows this.'
                )
                break

    return notes


def scoring_strategy_for(node: dict[str, Any]) -> str | None:
    """The scoring_strategy a query node implies, or None for the API default.

    Only an unambiguous single-service query gets a service-specific strategy. A query
    mixing two services has no one right ranking, so it falls back to the API's default
    ("combined") rather than silently ranking a cross-service result by one half of it.
    """
    services = set(driving_services(node))
    if len(services) != 1:
        return None
    return SERVICE_SCORING.get(next(iter(services)))


def default_return_type_for(node: dict[str, Any]) -> str:
    """The return_type to use when the caller did not name one.

    Mirrors what each flat tool defaulted to. A mixed-service query falls back to
    "entry", the one type every service can return.
    """
    services = driving_services(node)
    if len(set(services)) != 1:
        return "entry"
    service = services[0]
    if service == "structure":
        # A chain reference returns instances; an assembly reference returns assemblies.
        for terminal in _terminals(node):
            if terminal.get("service") == "structure":
                value = terminal.get("parameters", {}).get("value", {})
                return "polymer_instance" if "asym_id" in value else "assembly"
    return SERVICE_RETURN_TYPE.get(service, "entry")


def _terminals(node: Any):
    """Yield every terminal in a query tree."""
    if not isinstance(node, dict):
        return
    if node.get("type") == "group":
        for child in node.get("nodes") or []:
            yield from _terminals(child)
    else:
        yield node


def build_search_request(
    node: dict[str, Any],
    return_type: str | None = None,
    rows: int = 10,
    start: int = 0,
    all_hits: bool = False,
    include_computed: bool = False,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    group_by: str | None = None,
    group_by_ranking: str | None = None,
    facets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn a composed query node plus the result-shaping envelope into a request body.

    ``return_type=None`` means "the caller did not choose", and is resolved from the
    query itself -- never defaulted to "entry" in a signature, because an omitted
    return_type would then be indistinguishable from an explicit one and four of the
    seven services would silently return the wrong kind of identifier.
    """
    resolved = return_type or default_return_type_for(node)
    if resolved not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    if facets:
        options = _facet_options(facets, include_computed)
    else:
        options = _request_options(
            start, rows, include_computed,
            all_hits=all_hits,
            scoring_strategy=scoring_strategy_for(node),
            group_by=group_by,
            group_by_ranking=group_by_ranking,
            return_type=resolved,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
    return {"query": node, "return_type": resolved, "request_options": options}


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


def build_count_query(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    chemical: bool = False,
    include_computed: bool = False,
) -> dict[str, Any]:
    """Count matches only (return_counts) — no hits are paged or returned.

    Builds the same text/attribute node the query tools do. With no full_text/filters
    the count
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
        "rcsb_primary_citation{title rcsb_journal_abbrev year pdbx_database_id_DOI}",
    ),
    "polymer_entities": DataObject(
        "polymer_entities", "entity_ids", True, "String",
        'polymer entity IDs (entry_entity), e.g. "4HHB_1"',
        "rcsb_id rcsb_polymer_entity{pdbx_description formula_weight pdbx_number_of_molecules} "
        "entity_poly{type rcsb_sample_sequence_length} "
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
    error. This normalizes both dialects: each path (separated by whitespace and/or
    commas — GraphQL treats commas as insignificant, and agents naturally write a
    comma-separated list) is expanded ("a.b.c" -> "a { b { c } }") and shared
    prefixes are merged, while already-braced input passes through re-serialized.

    Anything using GraphQL we don't model — arguments, aliases, directives,
    fragments — is returned unchanged, so the raw selection still works verbatim.
    """
    if not fields or not fields.strip():
        return fields
    if "." not in fields:
        return fields  # already a GraphQL selection (or plain names) — leave verbatim
    if any(ch in fields for ch in "():@") or "..." in fields:
        return fields  # dotted but also advanced GraphQL: don't risk mangling it

    # Tokenize into NAME / DOT / LBRACE / RBRACE (whitespace and commas separate:
    # commas are insignificant in GraphQL, so accept "a.b, c.d" as "a.b c.d").
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(fields)
    while i < n:
        ch = fields[i]
        if ch.isspace() or ch == ",":
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
            Top-level rcsb_id is always included (injected if your `fields` omits it)
            so results stay identifiable and batch lookups can map them back to ids.

    Returns a {"query", "variables"} dict; ids ride in the "ids" variable.
    """
    try:
        spec = DATA_OBJECTS[object_key]
    except KeyError:
        raise ValueError(
            f"unknown object {object_key!r}; one of {sorted(DATA_OBJECTS)}"
        ) from None

    selection = _normalize_fields(fields) or spec.default_fields
    # Every Data API query MUST select top-level rcsb_id: batch results are mapped
    # back to the requested ids by it (without it, every id wrongly reports as
    # not_found — see _query_batch), and it makes each returned node identifiable.
    # Curated defaults already lead with rcsb_id; a custom `fields` override might
    # omit it, so inject it when the top-level selection lacks it. (A duplicate
    # top-level field is harmless — GraphQL merges identically-named selections.)
    if "rcsb_id" not in selection.split("{", 1)[0].split():
        selection = f"rcsb_id {selection}"
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
