"""Pure helpers that build RCSB Search API v2 and Data API GraphQL request bodies.

These functions contain *no* network code so they can be unit-tested in
isolation. Search builders return a dict ready to be POSTed to
https://search.rcsb.org/rcsbsearch/v2/query ; the GraphQL builders return a
``{"query", "variables"}`` dict ready to be POSTed to
https://data.rcsb.org/graphql
"""
from __future__ import annotations

from typing import Any, NamedTuple

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

# Allowed sequence-identity cluster cutoffs for group_by (spec enum).
GROUP_BY_IDENTITY_CUTOFFS = {100, 95, 90, 70, 50, 30}


def _request_options(
    start: int,
    rows: int,
    include_computed: bool,
    *,
    scoring_strategy: str | None = None,
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Common request_options block: pagination, content type, sort, grouping."""
    content = ["experimental"]
    if include_computed:
        content.append("computational")
    options: dict[str, Any] = {
        "paginate": {"start": start, "rows": rows},
        "results_content_type": content,
        "sort": [{"sort_by": "score", "direction": "desc"}],
    }
    if scoring_strategy:
        options["scoring_strategy"] = scoring_strategy
    if group_by_identity is not None:
        if group_by_identity not in GROUP_BY_IDENTITY_CUTOFFS:
            raise ValueError(
                f"group_by_identity must be one of {sorted(GROUP_BY_IDENTITY_CUTOFFS)}"
            )
        # Collapse redundant hits into sequence-identity clusters, one rep each.
        options["group_by"] = {
            "aggregation_method": "sequence_identity",
            "similarity_cutoff": group_by_identity,
        }
        options["group_by_return_type"] = "representatives"
    return options


def _text_node(
    attribute: str,
    operator: str,
    value: Any = None,
    *,
    negation: bool = False,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    """Build a terminal 'text' (attribute) query node.

    The 'exists' operator takes no value; all others require one. `negation`
    inverts the match and `case_sensitive` forces exact-case comparison.
    """
    if operator not in TEXT_OPERATORS:
        raise ValueError(f"operator must be one of {sorted(TEXT_OPERATORS)}")
    params: dict[str, Any] = {"attribute": attribute, "operator": operator}
    if operator != "exists":
        params["value"] = value
    if negation:
        params["negation"] = True
    if case_sensitive:
        params["case_sensitive"] = True
    return {"type": "terminal", "service": "text", "parameters": params}


def build_fulltext_query(
    value: str,
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Unstructured keyword/full-text search across all annotations."""
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    return {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": value},
        },
        "return_type": return_type,
        "request_options": _request_options(
            start, rows, include_computed, group_by_identity=group_by_identity
        ),
    }


def build_attribute_query(
    attribute: str,
    operator: str,
    value: Any = None,
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
    negation: bool = False,
    case_sensitive: bool = False,
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Structured search against a specific indexed attribute.

    Example: attribute="rcsb_entry_info.resolution_combined",
             operator="less", value=2.0

    The "exists" operator takes no value. `negation` inverts the match;
    `case_sensitive` forces case-sensitive value comparison.
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    return {
        "query": _text_node(
            attribute, operator, value, negation=negation, case_sensitive=case_sensitive
        ),
        "return_type": return_type,
        "request_options": _request_options(
            start, rows, include_computed, group_by_identity=group_by_identity
        ),
    }


def build_combined_query(
    full_text: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    logical_operator: str = "and",
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    group_by_identity: int | None = None,
) -> dict[str, Any]:
    """Combine a full-text term and/or several attribute filters with AND/OR.

    Each filter is a dict {"attribute", "operator", "value"} (same shape as
    build_attribute_query) and may also carry optional "negation" and
    "case_sensitive" booleans. A single condition collapses to a plain terminal
    node; multiple conditions are wrapped in a "group" node.

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
                negation=f.get("negation", False),
                case_sensitive=f.get("case_sensitive", False),
            )
        )
    if not nodes:
        raise ValueError("provide a full_text term and/or at least one filter")

    query = (
        nodes[0]
        if len(nodes) == 1
        else {"type": "group", "logical_operator": logical_operator, "nodes": nodes}
    )

    options = _request_options(
        start, rows, include_computed, group_by_identity=group_by_identity
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
) -> dict[str, Any]:
    """MMseqs2 sequence-similarity search (BLAST-like).

    identity_cutoff is a fraction in [0, 1]. sequence_type is one of
    "protein", "dna", "rna".
    """
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    if not 0.0 <= identity_cutoff <= 1.0:
        raise ValueError("identity_cutoff must be between 0 and 1")
    return {
        "query": {
            "type": "terminal",
            "service": "sequence",
            "parameters": {
                "value": sequence.strip().upper(),
                "sequence_type": sequence_type,
                "identity_cutoff": identity_cutoff,
                "evalue_cutoff": evalue_cutoff,
            },
        },
        "return_type": return_type,
        "request_options": {
            "paginate": {"start": start, "rows": rows},
            "results_content_type": ["experimental"],
            "scoring_strategy": "sequence",
        },
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
) -> dict[str, Any]:
    """Chemical search by SMILES/InChI descriptor or by molecular formula.

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
    return {
        "query": {"type": "terminal", "service": "chemical", "parameters": params},
        "return_type": return_type,
        "request_options": _request_options(start, rows, False, scoring_strategy="chemical"),
    }


def build_structure_query(
    entry_id: str,
    assembly_id: str | None = None,
    asym_id: str | None = None,
    return_type: str | None = None,
    rows: int = 10,
    start: int = 0,
) -> dict[str, Any]:
    """3D shape-similarity search against an existing PDB structure.

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
    return {
        "query": {"type": "terminal", "service": "structure", "parameters": {"value": value}},
        "return_type": rt,
        "request_options": _request_options(start, rows, False, scoring_strategy="structure"),
    }


def build_seqmotif_query(
    pattern: str,
    pattern_type: str = "prosite",
    sequence_type: str = "protein",
    return_type: str = "polymer_entity",
    rows: int = 10,
    start: int = 0,
) -> dict[str, Any]:
    """Short sequence-motif search (PROSITE pattern, regex, or simple wildcards).

    Examples: pattern_type="prosite" value "C-x(2,4)-C-x(3)-[LIVMFYWC]...",
    pattern_type="regex" value "C..H[LIVF]", pattern_type="simple" value "NXS".
    """
    if pattern_type not in SEQMOTIF_PATTERN_TYPES:
        raise ValueError(f"pattern_type must be one of {sorted(SEQMOTIF_PATTERN_TYPES)}")
    if sequence_type not in SEQUENCE_TYPES:
        raise ValueError(f"sequence_type must be one of {sorted(SEQUENCE_TYPES)}")
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    return {
        "query": {
            "type": "terminal",
            "service": "seqmotif",
            "parameters": {
                "value": pattern.strip(),
                "pattern_type": pattern_type,
                "sequence_type": sequence_type,
            },
        },
        "return_type": return_type,
        "request_options": _request_options(start, rows, False),
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
        "rcsb_entry_info{resolution_combined} "
        "rcsb_accession_info{deposit_date initial_release_date}",
    ),
    "polymer_entities": DataObject(
        "polymer_entities", "entity_ids", True, "String",
        'polymer entity IDs (entry_entity), e.g. "4HHB_1"',
        "rcsb_id rcsb_polymer_entity{pdbx_description formula_weight} "
        "entity_poly{type rcsb_sample_sequence_length pdbx_seq_one_letter_code_can} "
        "rcsb_entity_source_organism{ncbi_scientific_name}",
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
        "rcsb_uniprot_protein{name{value} source_organism{scientific_name}}",
    ),
    "pubmed": DataObject(
        "pubmed", "pubmed_id", False, "Int", "a PubMed integer ID, e.g. 6726807",
        "rcsb_id rcsb_pubmed_central_id rcsb_pubmed_doi rcsb_pubmed_abstract_text",
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


def build_data_query(
    object_key: str, ids: Any, fields: str | None = None
) -> dict[str, Any]:
    """Build a Data API GraphQL body for any object in DATA_OBJECTS.

    Args:
        object_key: A key of DATA_OBJECTS (e.g. "entries", "assemblies").
        ids: A list of ids for batch objects, or a single id for singletons.
        fields: Optional GraphQL selection set to use instead of the curated
            default (omit the surrounding braces), e.g. "rcsb_id struct{title}".

    Returns a {"query", "variables"} dict; ids ride in the "ids" variable.
    """
    try:
        spec = DATA_OBJECTS[object_key]
    except KeyError:
        raise ValueError(
            f"unknown object {object_key!r}; one of {sorted(DATA_OBJECTS)}"
        ) from None

    selection = fields or spec.default_fields
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
# systems (UniProt, NCBI, PDB entity/instance). Each builder returns a
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
    "aligned_regions{ query_begin query_end target_begin target_end } }"
)
SC_ANNOTATIONS_FIELDS = (
    "source target_id "
    "target_identifiers{ entry_id entity_id asym_id interface_id uniprot_id } "
    "features{ type feature_id name description provenance_source value "
    "feature_positions{ beg_seq_id end_seq_id value } }"
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

    Example: query_id="P69905", from_ref="UNIPROT", to_ref="PDB_ENTITY".
    """
    _require_enum(from_ref, SEQUENCE_REFERENCES, "from_ref")
    _require_enum(to_ref, SEQUENCE_REFERENCES, "to_ref")
    qid = str(query_id).strip()
    if not qid:
        raise ValueError("query_id must be a non-empty string")
    selection = fields or SC_ALIGNMENTS_FIELDS
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
    selection = fields or SC_ANNOTATIONS_FIELDS
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
    selection = fields or SC_ALIGNMENTS_FIELDS
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
    selection = fields or SC_ANNOTATIONS_FIELDS
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
