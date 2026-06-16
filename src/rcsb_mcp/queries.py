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

# A small allow-list of the most common text-search comparison operators.
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
}


def _request_options(start: int, rows: int, include_computed: bool) -> dict[str, Any]:
    """Common request_options block: pagination + which databases to search."""
    content = ["experimental"]
    if include_computed:
        content.append("computational")
    return {
        "paginate": {"start": start, "rows": rows},
        "results_content_type": content,
        "sort": [{"sort_by": "score", "direction": "desc"}],
    }


def build_fulltext_query(
    value: str,
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
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
        "request_options": _request_options(start, rows, include_computed),
    }


def build_attribute_query(
    attribute: str,
    operator: str,
    value: Any,
    return_type: str = "entry",
    rows: int = 10,
    start: int = 0,
    include_computed: bool = False,
) -> dict[str, Any]:
    """Structured search against a specific indexed attribute.

    Example: attribute="rcsb_entry_info.resolution_combined",
             operator="less", value=2.0
    """
    if return_type not in RETURN_TYPES:
        raise ValueError(f"return_type must be one of {sorted(RETURN_TYPES)}")
    if operator not in TEXT_OPERATORS:
        raise ValueError(f"operator must be one of {sorted(TEXT_OPERATORS)}")
    return {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": attribute,
                "operator": operator,
                "value": value,
            },
        },
        "return_type": return_type,
        "request_options": _request_options(start, rows, include_computed),
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
) -> dict[str, Any]:
    """Combine a full-text term and/or several attribute filters with AND/OR.

    Each filter is a dict {"attribute", "operator", "value"} (same shape as
    build_attribute_query). A single condition collapses to a plain terminal
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
        operator = f.get("operator")
        if operator not in TEXT_OPERATORS:
            raise ValueError(f"operator must be one of {sorted(TEXT_OPERATORS)}")
        nodes.append({
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": f["attribute"],
                "operator": operator,
                "value": f["value"],
            },
        })
    if not nodes:
        raise ValueError("provide a full_text term and/or at least one filter")

    query = (
        nodes[0]
        if len(nodes) == 1
        else {"type": "group", "logical_operator": logical_operator, "nodes": nodes}
    )

    options = _request_options(start, rows, include_computed)
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
    if sequence_type not in {"protein", "dna", "rna"}:
        raise ValueError('sequence_type must be "protein", "dna", or "rna"')
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
