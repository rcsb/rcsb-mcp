"""Pure helpers that build RCSB Search API v2 and Data API GraphQL request bodies.

These functions contain *no* network code so they can be unit-tested in
isolation. Search builders return a dict ready to be POSTed to
https://search.rcsb.org/rcsbsearch/v2/query ; the GraphQL builders return a
``{"query", "variables"}`` dict ready to be POSTed to
https://data.rcsb.org/graphql
"""
from __future__ import annotations

from typing import Any

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
# GraphQL lets us batch many ids into one request and reach Data API objects
# the single REST entry endpoint can't (polymer entities, ligands, ...).
# Ids are passed via GraphQL variables, so no string interpolation / escaping.

# Compact summary field selections, kept here so they're easy to review/extend.
ENTRIES_QUERY = """
query Entries($ids: [String!]!) {
  entries(entry_ids: $ids) {
    rcsb_id
    struct { title }
    exptl { method }
    rcsb_entry_info { resolution_combined }
    rcsb_accession_info { deposit_date }
  }
}
"""

POLYMER_ENTITIES_QUERY = """
query PolymerEntities($ids: [String!]!) {
  polymer_entities(entity_ids: $ids) {
    rcsb_id
    rcsb_polymer_entity { pdbx_description formula_weight }
    entity_poly { type rcsb_sample_sequence_length pdbx_seq_one_letter_code_can }
    rcsb_entity_source_organism { ncbi_scientific_name }
  }
}
"""

CHEM_COMPS_QUERY = """
query ChemComps($ids: [String!]!) {
  chem_comps(comp_ids: $ids) {
    rcsb_id
    chem_comp { name formula formula_weight type }
    rcsb_chem_comp_descriptor { SMILES InChIKey }
  }
}
"""


def _clean_id_list(ids: list[str]) -> list[str]:
    """Strip/validate a list of identifiers for a GraphQL batch query."""
    cleaned = [str(i).strip() for i in (ids or []) if str(i).strip()]
    if not cleaned:
        raise ValueError("provide at least one non-empty id")
    return cleaned


def build_entries_query(entry_ids: list[str]) -> dict[str, Any]:
    """Batch-fetch summary fields for one or more PDB entries (e.g. "4HHB")."""
    return {"query": ENTRIES_QUERY, "variables": {"ids": _clean_id_list(entry_ids)}}


def build_polymer_entities_query(entity_ids: list[str]) -> dict[str, Any]:
    """Batch-fetch one or more polymer entities (e.g. "4HHB_1")."""
    return {
        "query": POLYMER_ENTITIES_QUERY,
        "variables": {"ids": _clean_id_list(entity_ids)},
    }


def build_chem_comps_query(comp_ids: list[str]) -> dict[str, Any]:
    """Batch-fetch one or more chemical components / ligands (e.g. "HEM")."""
    return {"query": CHEM_COMPS_QUERY, "variables": {"ids": _clean_id_list(comp_ids)}}
