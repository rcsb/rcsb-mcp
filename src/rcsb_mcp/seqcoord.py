"""RCSB Sequence Coordinates API tools: map alignments and positional annotations across
sequence reference systems (UniProt, NCBI, PDB entity/instance), plus schema discovery.

Self-contained like the sibling tool packages: the reference-system type aliases (which the
schema turns into JSON-schema enums) and the root-field key set live here. The tool functions
are module-level (so they stay directly unit-testable); a FastMCP server attaches them with
register_seqcoord_tools(mcp), the register-onto-mcp pattern. The GraphQL execution and
schema-introspection helpers come from rcsb_mcp.graphql. This module imports nothing back
from server.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from rcsb_mcp import queries
from rcsb_mcp.client import (
    SEQCOORD_GRAPHIQL_URL,
    SEQCOORD_GRAPHQL_URL,
    _graphiql_editor,
)
from rcsb_mcp.graphql import (
    DATA_FIELDS_RESULT_CAP,
    _flatten_object_fields,
    _graphql_field,
    _walk_into,
)
from rcsb_mcp.tooling import READ_ONLY


SequenceRef = Literal["NCBI_GENOME", "NCBI_PROTEIN", "PDB_ENTITY", "PDB_INSTANCE", "UNIPROT"]
GroupRef = Literal["MATCHING_UNIPROT_ACCESSION", "SEQUENCE_IDENTITY"]
AnnotationRef = Literal["PDB_ENTITY", "PDB_INSTANCE", "PDB_INTERFACE", "UNIPROT"]


# The five Sequence Coordinates root fields, for rcsb_describe_seqcoord_object.
SEQCOORD_OBJECTS = {
    "alignments", "annotations",
    "group_alignments", "group_annotations", "group_annotations_summary",
}
# Derived from the set above (sorted for a deterministic enum), so the valid keys reach the tool
# schema and a bad one is rejected at the boundary. See DataObjectKey.
SeqcoordObjectKey = Literal[tuple(sorted(SEQCOORD_OBJECTS))]  # type: ignore[valid-type]


async def rcsb_describe_seqcoord_object(
    object_key: SeqcoordObjectKey,
    into: str | None = None,
    query: str | None = None,
    max_depth: Annotated[int, Field(ge=1, le=6)] = 1,
) -> dict[str, Any]:
    """Discover the fields available on a Sequence Coordinates object, from the live schema.

    The Sequence Coordinates analogue of rcsb_describe_data_object, with the same shape: the
    rcsb_seqcoord_* tools return a compact default selection; use this to find what else you can
    request via their `fields=` argument. Every path it returns is
    verified against the live schema, so it is safe to pass to `fields=` directly.

    Browse a level (default), drill in / scope with `into`, or raise `max_depth` to flatten the
    tree into dotted paths and filter with `query`. This schema is small and only 3 levels deep
    (~20-31 fields per object), so max_depth=3 returns an object in full in ONE call:
    rcsb_describe_seqcoord_object("alignments", max_depth=3) -> pick paths -> call
    rcsb_seqcoord_alignments(..., fields="target_alignments{ ... }").

    Each returned field has path (dotted, ready for `fields=`), kind ("scalar" leaf or "object"),
    type, list (whether it's a list), and description (when present).

    Args:
        object_key: A Sequence Coordinates root field. (alignments and group_alignments share
            the SequenceAlignments type; the annotation roots share SequenceAnnotations.)
        into: Optional dot-path of nested object field(s) to scope to, e.g.
            "target_alignments" or "features.feature_positions".
        query: Optional case-insensitive keyword, matched against each field's path (relative to
            the scope) and its description.
        max_depth: How many levels to walk (1-6, default 1 = this level only). The schema bottoms
            out at 3.

    Returns:
        {object_key, graphql_type, path, query, max_depth, field_count,
        fields:[{path, kind, type, list, description}], truncated?, note?}.
    """
    if object_key not in SEQCOORD_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(SEQCOORD_OBJECTS)}")
    type_name, chain, prefix = await _walk_into(object_key, SEQCOORD_GRAPHQL_URL, into)
    fields, truncated = await _flatten_object_fields(
        type_name, SEQCOORD_GRAPHQL_URL, max_depth, query, DATA_FIELDS_RESULT_CAP,
        path_prefix=prefix,
    )
    result: dict[str, Any] = {
        "object_key": object_key,
        "graphql_type": type_name,
        "path": chain,
        "query": query,
        "max_depth": max_depth,
        "field_count": len(fields),
        "fields": fields,
    }
    if truncated:
        result["truncated"] = True
        result["note"] = (
            "Result set was capped. Add or narrow a `query` keyword, lower `max_depth`, or "
            "scope to a nested object with `into=`."
        )
    return result


async def rcsb_seqcoord_alignments(
    query_id: str,
    from_ref: SequenceRef,
    to_ref: SequenceRef,
    seq_range: list[int] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Cross-reference a sequence across PDB, UniProt, and NCBI, with aligned ranges.

    This is the tool for "which X identifiers correspond to this sequence?" across
    databases — including NCBI. The RCSB Data API only cross-references UniProt, so
    use THIS tool for NCBI RefSeq protein / genome mappings (and PDB<->UniProt too).
    The returned target_alignments[].target_id values are the mapped identifiers in
    the to_ref system, each with its aligned regions.

    Examples:
        - "What NCBI proteins map to PDB entity 4HHB_1?"
          query_id="4HHB_1", from_ref="PDB_ENTITY", to_ref="NCBI_PROTEIN"
        - "Which PDB entities correspond to UniProt P69905?"
          query_id="P69905", from_ref="UNIPROT", to_ref="PDB_ENTITY"

    Args:
        query_id: The sequence id, in the from_ref system's format — UNIPROT "P69905",
            NCBI_PROTEIN "NP_000508", NCBI_GENOME "NC_000016", PDB_ENTITY "4HHB_1"
            (entry_entityNumber), PDB_INSTANCE "4HHB.A" (entry.asym_id). PDB ids must be
            ENTITY-level, never a bare entry: for a whole entry, first get its polymer
            entity ids (4HHB -> 4HHB_1, 4HHB_2) and query each one.
        from_ref: Reference system of query_id.
        to_ref: Reference system to map onto.
        seq_range: Optional [begin, end] (1-based) to restrict the query region.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_alignments_query(query_id, from_ref, to_ref, seq_range, fields)
    editor = _graphiql_editor(SEQCOORD_GRAPHIQL_URL, body)
    data = await _graphql_field(body, "alignments", url=SEQCOORD_GRAPHQL_URL)
    if not data or not (data.get("target_alignments")):
        return {
            "query_id": query_id,
            "from_ref": from_ref,
            "to_ref": to_ref,
            "target_alignments": [],
            "note": (
                "No alignments found. For PDB, query_id must be an entity ("
                f'e.g. "4HHB_1"), not a bare entry. Got {query_id!r}.'
                if from_ref.startswith("PDB") and "_" not in query_id and "." not in query_id
                else "No alignments found for this query."
            ),
            "editor": editor,
        }
    return {**data, "editor": editor}


async def rcsb_seqcoord_annotations(
    query_id: str,
    reference: SequenceRef,
    sources: list[AnnotationRef],
    seq_range: list[int] | None = None,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch positional sequence annotations (features) for one sequence.

    Args:
        query_id: The sequence id, e.g. "4HHB_1" (PDB_ENTITY) or "P69905" (UNIPROT).
        reference: Reference system query_id is given in.
        sources: Annotation provenance — which source(s) to pull features from.
        seq_range: Optional [begin, end] (1-based) to restrict the region.
        filters: Optional list of {field, operation, source?, values} filter dicts,
            where field is TARGET_ID or TYPE and operation is CONTAINS or EQUALS.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_annotations_query(
        query_id, reference, sources, seq_range, filters, fields
    )
    data = await _graphql_field(body, "annotations", url=SEQCOORD_GRAPHQL_URL) or []
    return {
        "count": len(data),
        "annotations": data,
        "editor": _graphiql_editor(SEQCOORD_GRAPHIQL_URL, body),
    }


async def rcsb_seqcoord_group_alignments(
    group: GroupRef,
    group_id: str,
    filter_terms: list[str] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch alignments among the members of a sequence group.

    Args:
        group: How the group is defined.
        group_id: The group id, e.g. "P69905" (a UniProt accession) for
            MATCHING_UNIPROT_ACCESSION.
        filter_terms: Optional list of target ids to restrict the group members.
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_group_alignments_query(group, group_id, filter_terms, fields)
    editor = _graphiql_editor(SEQCOORD_GRAPHIQL_URL, body)
    data = await _graphql_field(body, "group_alignments", url=SEQCOORD_GRAPHQL_URL)
    if data is None:
        return {"group_id": group_id, "error": "no alignment found", "editor": editor}
    return {**data, "editor": editor}


async def rcsb_seqcoord_group_annotations(
    group: GroupRef,
    group_id: str,
    sources: list[AnnotationRef],
    summary: bool = False,
    filters: list[dict[str, Any]] | None = None,
    fields: str | None = None,
) -> dict[str, Any]:
    """Fetch annotations across the members of a sequence group.

    Args:
        group: How the group is defined.
        group_id: The group id, e.g. "P69905" for MATCHING_UNIPROT_ACCESSION.
        sources: Annotation provenance — which source(s) to pull features from.
        summary: If true, return a positional summary aggregated across the group
            (group_annotations_summary) instead of per-member annotations.
        filters: Optional filter dicts (see rcsb_seqcoord_annotations).
        fields: Optional GraphQL selection to override the default.
    """
    body = queries.build_sc_group_annotations_query(
        group, group_id, sources, summary=summary, filters=filters, fields=fields
    )
    field = "group_annotations_summary" if summary else "group_annotations"
    data = await _graphql_field(body, field, url=SEQCOORD_GRAPHQL_URL) or []
    return {
        "count": len(data),
        "annotations": data,
        "editor": _graphiql_editor(SEQCOORD_GRAPHIQL_URL, body),
    }


# rcsb_seqcoord_* (+ rcsb_describe_seqcoord_object) are the Sequence Coordinates tools;
# register_seqcoord_tools wires each onto the passed FastMCP instance (equivalent to the
# @mcp.tool decorator, but the functions stay importable/testable on their own). Original
# tool order is preserved.
_SEQCOORD_TOOLS = (
    rcsb_describe_seqcoord_object,
    rcsb_seqcoord_alignments,
    rcsb_seqcoord_annotations,
    rcsb_seqcoord_group_alignments,
    rcsb_seqcoord_group_annotations,
)


def register_seqcoord_tools(mcp) -> None:
    """Attach the Sequence Coordinates API tools (rcsb_seqcoord_* / rcsb_describe_seqcoord_object) to a FastMCP server."""
    for fn in _SEQCOORD_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
