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

import json
from collections import Counter, defaultdict
from typing import Annotated, Any, Literal

from pydantic import Field

from rcsb_mcp import queries
from rcsb_mcp.client import (
    SEQCOORD_GRAPHIQL_URL,
    SEQCOORD_GRAPHQL_URL,
    _graphiql_editor,
)
from rcsb_mcp.descriptions.seqcoord import (
    describe_seqcoord_object,
    seqcoord_alignments,
    seqcoord_annotations,
    shared,
)
from rcsb_mcp.graphql import (
    DATA_FIELDS_RESULT_CAP,
    _flatten_object_fields,
    _graphql_field,
    _walk_into,
    resolve_max_depth,
)
from rcsb_mcp.tooling import READ_ONLY


SequenceRef = Literal["NCBI_GENOME", "NCBI_PROTEIN", "PDB_ENTITY", "PDB_INSTANCE", "UNIPROT"]


# The Sequence Coordinates root fields the rcsb_seqcoord_* tools query, for
# rcsb_describe_seqcoord_object.
SEQCOORD_OBJECTS = {"alignments", "annotations"}
# Derived from the set above (sorted for a deterministic enum), so the valid keys reach the tool
# schema and a bad one is rejected at the boundary. See DataObjectKey.
SeqcoordObjectKey = Literal[tuple(sorted(SEQCOORD_OBJECTS))]  # type: ignore[valid-type]


async def rcsb_describe_seqcoord_object(
    object_key: Annotated[
        SeqcoordObjectKey, Field(description=describe_seqcoord_object.OBJECT_KEY_DOC)
    ],
    into: Annotated[str | None, Field(description=describe_seqcoord_object.INTO_DOC)] = None,
    query: Annotated[str | None, Field(description=describe_seqcoord_object.QUERY_DOC)] = None,
    max_depth: Annotated[
        Annotated[int, Field(ge=1, le=6)] | None, Field(description=describe_seqcoord_object.MAX_DEPTH_DOC)
    ] = None,
) -> dict[str, Any]:
    """Discover the fields available on a Sequence Coordinates object, from the live schema.

    The Sequence Coordinates analogue of rcsb_describe_data_object, with the same shape: the
    rcsb_seqcoord_* tools return a compact default selection; use this to find what else you can
    request via their `fields=` argument. Every path it returns is
    verified against the live schema, so it is safe to pass to `fields=` directly.

    Browse a level, drill in / scope with `into`, or pass `query` to flatten the tree into
    dotted paths and keep only matching fields. The walk depth follows which one you are
    doing, so you do not have to set it: browsing lists one level, searching goes three deep.
    This schema is small and bottoms out at 3 levels (~20-31 fields per object), so a search
    covers an object in full in ONE call:
    rcsb_describe_seqcoord_object("alignments", max_depth=3) -> pick paths -> call
    rcsb_seqcoord_alignments(..., fields="target_alignments{ ... }").

    Each returned field has path (dotted, ready for `fields=`), kind ("scalar" leaf or "object"),
    type, list (whether it's a list), and description (when present).

    NEVER invent, guess, or infer a field path — an unverified path fails schema validation
    and wastes the call. `fields=` accepts dotted paths or GraphQL nested-brace syntax, the
    two may be mixed, and multiple paths are separated by spaces or commas.

    Returns:
        {object_key, graphql_type, path, query, max_depth, field_count,
        fields:[{path, kind, type, list, description}], truncated?, note?}.
    """
    if object_key not in SEQCOORD_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(SEQCOORD_OBJECTS)}")
    depth = resolve_max_depth(max_depth, query)
    type_name, chain, prefix = await _walk_into(object_key, SEQCOORD_GRAPHQL_URL, into)
    fields, truncated = await _flatten_object_fields(
        type_name, SEQCOORD_GRAPHQL_URL, depth, query, DATA_FIELDS_RESULT_CAP,
        path_prefix=prefix,
    )
    result: dict[str, Any] = {
        "object_key": object_key,
        "graphql_type": type_name,
        "path": chain,
        "query": query,
        "max_depth": depth,
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
    query_id: Annotated[str, Field(description=seqcoord_alignments.QUERY_ID_DOC)],
    from_ref: Annotated[SequenceRef, Field(description=seqcoord_alignments.FROM_REF_DOC)],
    to_ref: Annotated[SequenceRef, Field(description=seqcoord_alignments.TO_REF_DOC)],
    seq_range: Annotated[
        list[int] | None, Field(description=seqcoord_alignments.SEQ_RANGE_DOC)
    ] = None,
    fields: Annotated[str | None, Field(description=shared.FIELDS_DOC)] = None,
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


# The largest annotations answer returned whole. Annotation JSON runs ~2.8 characters per
# cl100k token compact (measured 2026-10-09 on 8 sequences), and FastMCP's text copy of a result
# is indented, ~1.24x the tokens; 45,000 compact characters keep either form near 20k tokens,
# under the 25k Claude Code accepts from an MCP tool by default. Every source of 4HHB_1 is ~33k
# tokens, of GroEL 1AON_1 ~165k: an entity's instance features come once per copy. Larger
# answers are refused, never cut, with the types the sequence has (_too_large).
_ANNOTATIONS_BUDGET = 45_000  # compact JSON characters
_CHARS_PER_TOKEN = 2.8
_INVENTORY_FIELDS = "source target_id features{ type }"
_INSTANCES_SHOWN = 8


def _kilotokens(chars: int) -> str:
    return f"~{chars / _CHARS_PER_TOKEN / 1000:.1f}k tokens"


async def _annotations(body: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    try:
        return await _graphql_field(body, "annotations", url=SEQCOORD_GRAPHQL_URL) or []
    except RuntimeError as exc:
        if "timed out" not in str(exc):
            raise
        hint = ("" if "." in qid else
                " If it keeps timing out, the entity may have very many copies (3J3Q_1 does): ask "
                "for one of its instances (rcsb_get_polymer_entities lists them), without "
                "feature_types to see what it has.")
        raise RuntimeError(f"Sequence Coordinates timed out on {qid}; try again shortly.{hint}") from None


def _has_inventory(data: list[dict[str, Any]]) -> bool:
    return all("source" in a and "target_id" in a and "features" in a
               and all("type" in f for f in a["features"] or []) for a in data)


def _one_instance_fits(data: list[dict[str, Any]], overhead: int) -> bool:
    """Whether one instance's answer would fit, judged from the entity's: the same UniProt and
    entity features, one copy's instance features and a share of the interfaces."""
    by_source: dict[str, int] = defaultdict(int)
    per_instance: dict[str, int] = defaultdict(int)
    for a in data:
        size = len(json.dumps(a))
        by_source[a["source"]] += size
        if a["source"] == "PDB_INSTANCE":
            per_instance[a["target_id"]] += size
    if len(per_instance) < 2:
        return False
    estimate = (by_source["UNIPROT"] + by_source["PDB_ENTITY"] + max(per_instance.values())
                + by_source["PDB_INTERFACE"] // len(per_instance) + overhead)
    return estimate <= _ANNOTATIONS_BUDGET


def _too_large(query_id: str, chars: int, data: list[dict[str, Any]], types: int,
               instance_fits: bool) -> str:
    """Why the answer was refused, and what this sequence has to ask for instead (`types`: how
    many distinct feature types were asked for)."""
    counts: dict[str, Counter] = defaultdict(Counter)
    instances: set[str] = set()
    for a in data:
        for f in a.get("features") or []:
            counts[f["type"]][a["source"]] += 1
        if a["source"] == "PDB_INSTANCE":
            instances.add(a["target_id"])
    have = "; ".join(f"{t} ({', '.join(f'{s} {n}' for s, n in by.items())})"
                     for t, by in sorted(counts.items()))
    asks = []
    if types != 1:
        asks.append("fewer feature_types" if types else "some of its feature_types")
    if instance_fits:
        ordered = sorted(instances, key=lambda i: (len(i), i))
        shown = ", ".join(ordered[:_INSTANCES_SHOWN])
        more = f" and {len(ordered) - _INSTANCES_SHOWN} more" if len(ordered) > _INSTANCES_SHOWN else ""
        asks.append(f"one instance ({shown}{more}) instead of the entity")
    ask = " or ".join(asks) or "a smaller `fields` selection"
    return (f"The annotations of {query_id} are {_kilotokens(chars)}, over this tool's "
            f"{_kilotokens(_ANNOTATIONS_BUDGET)}. Ask for {ask}. Feature types it has (source, "
            f"features): {have}.")


async def rcsb_seqcoord_annotations(
    query_id: Annotated[str, Field(description=seqcoord_annotations.QUERY_ID_DOC)],
    feature_types: Annotated[
        list[str] | None, Field(description=seqcoord_annotations.FEATURE_TYPES_DOC)
    ] = None,
    fields: Annotated[str | None, Field(description=shared.FIELDS_DOC)] = None,
) -> dict[str, Any]:
    """Residue-level features of one PDB polymer entity (4HHB_1) or instance (4HHB.A),
    positioned on its sequence.

    The tool for questions about specific residues: which form an active site, bind a ligand or
    metal, are modified, glycosylated or disulfide-bonded, lie in a domain, helix or membrane
    segment, are unobserved or poorly fitted.

    Without feature_types every feature is returned. An answer too large to return (an entity's
    chain features come once per copy) fails with the feature types the sequence has and their
    counts: ask again for the ones needed, or for one instance. With feature_types only those
    come back, from the sources that have them.
    """
    body = queries.build_sc_annotations_query(query_id, feature_types, fields)
    qid = body["variables"]["queryId"]
    data = await _annotations(body, qid)
    if not data:
        # An unknown id answers with nothing, like a sequence without the asked types.
        found = feature_types and await _annotations(
            queries.build_sc_annotations_query(qid, None, "source"), qid)
        if not found:
            raise ValueError(
                f"Sequence Coordinates has no annotations for {qid}: it matches no PDB polymer "
                "sequence it indexes. Instance ids use the RCSB chain id (label_asym_id), which "
                "can differ from the author's (6M0J: author chain E is B); entity ids number "
                "polymer entities only.")
    result: dict[str, Any] = {"count": len(data), "annotations": data,
                              "editor": _graphiql_editor(SEQCOORD_GRAPHQL_URL, body)}
    if not data:
        result["note"] = (f"{qid} has none of these feature types. Call without feature_types "
                          "to see the ones it has.")
        return result
    chars = len(json.dumps(result))
    if chars > _ANNOTATIONS_BUDGET:
        types = len(body["variables"]["filters"][0]["values"]) if body["variables"]["filters"] else 0
        complete = _has_inventory(data)
        fits = "." not in qid and complete and _one_instance_fits(data, chars - len(json.dumps(data)))
        if not complete:  # a custom `fields` left out what the inventory needs
            data = await _annotations(
                queries.build_sc_annotations_query(qid, feature_types, _INVENTORY_FIELDS), qid)
        raise ValueError(_too_large(qid, chars, data, types, fits))
    return result


# rcsb_seqcoord_* (+ rcsb_describe_seqcoord_object) are the Sequence Coordinates tools;
# register_seqcoord_tools wires each onto the passed FastMCP instance (equivalent to the
# @mcp.tool decorator, but the functions stay importable/testable on their own). Original
# tool order is preserved.
_SEQCOORD_TOOLS = (
    rcsb_describe_seqcoord_object,
    rcsb_seqcoord_alignments,
    rcsb_seqcoord_annotations,
)


def register_seqcoord_tools(mcp) -> None:
    """Attach the Sequence Coordinates API tools (rcsb_seqcoord_* / rcsb_describe_seqcoord_object) to a FastMCP server."""
    for fn in _SEQCOORD_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
