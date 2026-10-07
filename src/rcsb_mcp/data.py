"""RCSB Data API tools: fetch entry / entity / assembly / ligand metadata and annotations
from the Data API GraphQL endpoint (https://data.rcsb.org/graphql), plus schema discovery.

Self-contained like the sibling tool packages: the object-key type alias (which the schema
turns into a JSON-schema enum) and the two batch/single GraphQL fetch helpers live here. The
tool functions are module-level (so they stay directly unit-testable); a FastMCP server attaches
them with register_data_tools(mcp), the register-onto-mcp pattern. The GraphQL execution and
schema-introspection helpers come from rcsb_mcp.graphql. This module imports nothing back from
server.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from rcsb_mcp import queries
from rcsb_mcp.client import (
    DATA_GRAPHIQL_URL,
    DATA_GRAPHQL_URL,
    _graphiql_editor,
)
from rcsb_mcp.descriptions.data import (
    describe_data_object,
    get_assemblies,
    get_branched_entities,
    get_branched_entity_instances,
    get_chem_comps,
    get_entries,
    get_entry_groups,
    get_group_provenance,
    get_interfaces,
    get_nonpolymer_entities,
    get_nonpolymer_entity_groups,
    get_nonpolymer_entity_instances,
    get_polymer_entities,
    get_polymer_entity_groups,
    get_polymer_entity_instances,
    get_pubmed,
    get_uniprot,
    shared,
)
from rcsb_mcp.graphql import (
    DATA_FIELDS_RESULT_CAP,
    _flatten_object_fields,
    search_all_objects,
    _graphql_field,
    _walk_into,
    resolve_max_depth,
)
from rcsb_mcp.tooling import READ_ONLY


# Data API object keys, derived from the registry so the two can never drift — adding an object
# stays a one-line registry entry and its key shows up in the tool schema automatically. Sorted
# for a deterministic enum. Typing it (vs a bare str) puts the valid keys in the JSON schema, so
# the caller picks from a list instead of guessing and a bad key is rejected at the boundary.
DataObjectKey = Literal[tuple(sorted(queries.DATA_OBJECTS))]  # type: ignore[valid-type]


async def _query_batch(
    object_key: str, ids: list[str], fields: str | None
) -> dict[str, Any]:
    """Fetch a batch Data API object, returning {count, <object>: [...], not_found?}.

    The API silently drops unknown ids, so we report which requested ids did
    not come back. Returned field selections are passed through as-is.
    """
    spec = queries.DATA_OBJECTS[object_key]
    body = queries.build_data_query(object_key, ids, fields)
    nodes = await _graphql_field(body, spec.root_field)
    # Unknown ids are either dropped or returned as null depending on the field.
    nodes = [n for n in (nodes or []) if n is not None]
    returned = {str(n.get("rcsb_id", "")).upper() for n in nodes}
    requested = [str(i).strip().upper() for i in ids if str(i).strip()]
    missing = [i for i in requested if i not in returned]
    result: dict[str, Any] = {"count": len(nodes), spec.root_field: nodes}
    if missing:
        result["not_found"] = missing
    result["editor"] = _graphiql_editor(DATA_GRAPHIQL_URL, body)
    return result


async def _query_single(
    object_key: str, id_value: Any, fields: str | None
) -> dict[str, Any]:
    """Fetch a singleton Data API object, or a not-found marker."""
    spec = queries.DATA_OBJECTS[object_key]
    body = queries.build_data_query(object_key, id_value, fields)
    node = await _graphql_field(body, spec.root_field)
    if node is None:
        return {"id": id_value, "error": "not found"}
    return {**node, "editor": _graphiql_editor(DATA_GRAPHIQL_URL, body)}


async def rcsb_describe_data_object(
    object_key: Annotated[
        DataObjectKey | None, Field(description=describe_data_object.OBJECT_KEY_DOC)
    ] = None,
    into: Annotated[str | None, Field(description=describe_data_object.INTO_DOC)] = None,
    query: Annotated[str | None, Field(description=describe_data_object.QUERY_DOC)] = None,
    max_depth: Annotated[
        Annotated[int, Field(ge=1, le=6)] | None,
        Field(description=describe_data_object.MAX_DEPTH_DOC),
    ] = None,
) -> dict[str, Any]:
    """Discover the fields available on a Data API object, from the live GraphQL schema.

    Use this to find what to request in a rcsb_get_* tool's `fields=` argument: its default
    selection is a compact summary of a far richer type (CoreEntry has ~100 fields). Every
    path returned is verified against the live schema, so it is safe to pass directly.

    NEVER invent, guess, or infer a field path from memory, from a naming convention, or
    from another API. An unverified path fails GraphQL schema validation and wastes the
    call. Paths shown in a rcsb_get_* tool's own description or examples are already
    verified — use those directly; for anything else, confirm it here FIRST.

    `fields=` takes dotted paths ("rcsb_polymer_entity.pdbx_description"), GraphQL brace
    syntax ("rcsb_polymer_entity { pdbx_description }"), or both, separated by spaces or
    commas.

    Start with only a `query` when you know what you want but not where it lives: it
    searches every object and answers with the tool to call and the path to give it, best
    matches first — rcsb_describe_data_object(query="release_date") -> rcsb_get_entries +
    "rcsb_accession_info.initial_release_date". Name an `object_key` to search just that
    object, or omit `query` to browse its fields level by level with `into`.

    Returns:
        For a named object: {object_key, graphql_type, path, query, max_depth, field_count,
        fields, truncated?, note?}. Searching every object: the same with object_key null
        plus `searched`, and each field also names the rcsb_get_* `tool` that owns it. Each
        field is {path, kind, type, list, description, searchable?}: `kind` is "scalar"
        (select it directly) or "object" (drill in, or select with a sub-selection);
        `searchable` (about 3% of fields) marks one you can ALSO filter on with
        rcsb_query_attribute. A field is reported once, under the object reaching it most
        directly. A capped result sets `truncated`, and `note` says how to narrow it.
    """
    depth = resolve_max_depth(max_depth, query)
    if object_key is None:
        if not (query and query.strip()):
            raise ValueError(
                "Searching every object needs a `query` keyword — without one this would "
                "return the whole Data API schema. Either pass query=\"<keyword>\", or name "
                f"an object_key to browse: {sorted(queries.DATA_OBJECTS)}."
            )
        if into:
            raise ValueError(
                "`into` scopes a walk inside ONE object, so it needs an object_key. Drop "
                "`into` to search every object, or name the object you want to scope."
            )
        fields, truncated = await search_all_objects(
            {k: s.root_field for k, s in queries.DATA_OBJECTS.items()},
            DATA_GRAPHQL_URL, query, depth,
        )
        result: dict[str, Any] = {
            "object_key": None,
            "searched": "all objects",
            "query": query,
            "max_depth": depth,
            "field_count": len(fields),
            # Each row carries the object that owns it, so `tool` is the one to call and
            # `path` is what goes in its `fields=`.
            "fields": [
                {"tool": f"rcsb_get_{f.pop('object_key')}", **f} for f in fields
            ],
        }
        if truncated:
            result["truncated"] = True
            result["note"] = (
                "More fields matched than are shown. The best matches are listed first "
                "(exact field-name matches, then partial, then description-only). Use a "
                "more specific keyword, or re-run with object_key set to narrow to one tool."
            )
        return result

    if object_key not in queries.DATA_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(queries.DATA_OBJECTS)}")
    root_field = queries.DATA_OBJECTS[object_key].root_field
    type_name, chain, prefix = await _walk_into(root_field, DATA_GRAPHQL_URL, into)
    fields, truncated = await _flatten_object_fields(
        type_name, DATA_GRAPHQL_URL, depth, query, DATA_FIELDS_RESULT_CAP, path_prefix=prefix,
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


def _fields_doc(example: str, object_key: str) -> str:
    """The shared `fields` wording (descriptions/data/shared.py), filled in for one rcsb_get_* tool.

    Pass `object_key` the same literal the tool's own body queries, so the text always names the
    object the tool actually hits.
    """
    return shared.FIELDS_DOC.format(example=example, object_key=object_key)


async def rcsb_get_entries(
    entry_ids: Annotated[list[str], Field(description=get_entries.ENTRY_IDS_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_entries.FIELDS_EXAMPLE, "entries"))
    ] = None,
) -> dict[str, Any]:
    """Fetch metadata for one or more PDB entries (title, method, resolution, size,
    dates, and primary citation).

    The response also lists the entry's component ids under
    rcsb_entry_container_identifiers — use these to drill into the structure. They are
    bare numbers; compose them with the entry id to call the matching rcsb_get_* tool:
    polymer_entity_ids/non_polymer_entity_ids "N" -> "<ENTRY>_N" (rcsb_get_polymer_entities /
    rcsb_get_nonpolymer_entities); assembly_ids "N" -> "<ENTRY>-N" (rcsb_get_assemblies).
    """
    return await _query_batch("entries", entry_ids, fields)


async def rcsb_get_polymer_entities(
    entity_ids: Annotated[list[str], Field(description=get_polymer_entities.ENTITY_IDS_DOC)],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_polymer_entities.FIELDS_EXAMPLE, "polymer_entities"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch polymer entities (protein/nucleic-acid molecules) — description, length,
    weight, and source organism.

    Default fields: description, length, weight, and source organism.

    Polymer-based (sequence) annotations can be fetched adding rcsb_polymer_entity_annotation.* fields,
    and positional features adding rcsb_polymer_entity_feature.*
    """
    return await _query_batch("polymer_entities", entity_ids, fields)


async def rcsb_get_nonpolymer_entities(
    entity_ids: Annotated[list[str], Field(description=get_nonpolymer_entities.ENTITY_IDS_DOC)],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_nonpolymer_entities.FIELDS_EXAMPLE, "nonpolymer_entities"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch non-polymer (ligand/cofactor) entities, e.g. ["4HHB_3"].

    Default fields: description, weight, copy count, and the bound chemical component ID.
    Use rcsb_get_chem_comps for the chemistry of that component.
    """
    return await _query_batch("nonpolymer_entities", entity_ids, fields)


async def rcsb_get_branched_entities(
    entity_ids: Annotated[list[str], Field(description=get_branched_entities.ENTITY_IDS_DOC)],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_branched_entities.FIELDS_EXAMPLE, "branched_entities"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch branched (carbohydrate / oligosaccharide) entities, e.g. ["5FMB_2"].

    Default fields: description, weight, copy count, branch type, and component count.
    """
    return await _query_batch("branched_entities", entity_ids, fields)


async def rcsb_get_polymer_entity_instances(
    instance_ids: Annotated[
        list[str], Field(description=get_polymer_entity_instances.INSTANCE_IDS_DOC)
    ],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_polymer_entity_instances.FIELDS_EXAMPLE, "polymer_entity_instances"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch polymer entity instances (individual chains), e.g. ["4HHB.A"] (entry.asym_id).

    Instance-based (chain) annotations can be fetched adding rcsb_polymer_instance_annotation.* fields,
    and positional features rcsb_polymer_instance_feature.*

    Default fields: the entry/entity/chain identifiers and modeled-residue count.
    """
    return await _query_batch("polymer_entity_instances", instance_ids, fields)


async def rcsb_get_nonpolymer_entity_instances(
    instance_ids: Annotated[
        list[str], Field(description=get_nonpolymer_entity_instances.INSTANCE_IDS_DOC)
    ],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_nonpolymer_entity_instances.FIELDS_EXAMPLE, "nonpolymer_entity_instances"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch non-polymer entity instances (individual bound ligands), e.g. ["4HHB.E"].

    Default fields: the entry/entity/chain identifiers, bound component id, and author seq id.
    """
    return await _query_batch("nonpolymer_entity_instances", instance_ids, fields)


async def rcsb_get_branched_entity_instances(
    instance_ids: Annotated[
        list[str], Field(description=get_branched_entity_instances.INSTANCE_IDS_DOC)
    ],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_branched_entity_instances.FIELDS_EXAMPLE, "branched_entity_instances"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch branched entity instances (individual glycan chains), e.g. ["5FMB.C"].

    Default fields: the entry/entity/chain identifiers.
    """
    return await _query_batch("branched_entity_instances", instance_ids, fields)


async def rcsb_get_assemblies(
    assembly_ids: Annotated[list[str], Field(description=get_assemblies.ASSEMBLY_IDS_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_assemblies.FIELDS_EXAMPLE, "assemblies"))
    ] = None,
) -> dict[str, Any]:
    """Fetch biological assemblies, e.g. ["4HHB-1"] (entry-assembly).

    Default fields: composition counts and oligomeric state.

    Assembly-based (complex) annotations can be fetched adding rcsb_assembly_annotation.* fields,
    and positional features rcsb_assembly_feature.*
    """
    return await _query_batch("assemblies", assembly_ids, fields)


async def rcsb_get_interfaces(
    interface_ids: Annotated[list[str], Field(description=get_interfaces.INTERFACE_IDS_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_interfaces.FIELDS_EXAMPLE, "interfaces"))
    ] = None,
) -> dict[str, Any]:
    """Fetch assembly interfaces, e.g. ["1BMV-1.1"] (entry-assembly.interface).

    Default fields: buried area, character, composition, residue count.
    """
    return await _query_batch("interfaces", interface_ids, fields)


async def rcsb_get_chem_comps(
    comp_ids: Annotated[list[str], Field(description=get_chem_comps.COMP_IDS_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_chem_comps.FIELDS_EXAMPLE, "chem_comps"))
    ] = None,
) -> dict[str, Any]:
    """Fetch chemical components / ligands by their short codes, e.g. ["HEM", "ATP"].

    Default fields: name, formula, weight, type, SMILES, InChIKey.
    """
    return await _query_batch("chem_comps", comp_ids, fields)


async def rcsb_get_entry_groups(
    group_ids: Annotated[list[str], Field(description=get_entry_groups.GROUP_IDS_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_entry_groups.FIELDS_EXAMPLE, "entry_groups"))
    ] = None,
) -> dict[str, Any]:
    """Fetch entry groups (clusters of related entries) by group ID.

    Default fields: group name, description, member count, and member ids.
    """
    return await _query_batch("entry_groups", group_ids, fields)


async def rcsb_get_polymer_entity_groups(
    group_ids: Annotated[list[str], Field(description=get_polymer_entity_groups.GROUP_IDS_DOC)],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_polymer_entity_groups.FIELDS_EXAMPLE, "polymer_entity_groups"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch polymer entity groups (e.g. sequence clusters), e.g. ["85_70"].

    Default fields: group name, description, member count, and member ids.
    """
    return await _query_batch("polymer_entity_groups", group_ids, fields)


async def rcsb_get_nonpolymer_entity_groups(
    group_ids: Annotated[list[str], Field(description=get_nonpolymer_entity_groups.GROUP_IDS_DOC)],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_nonpolymer_entity_groups.FIELDS_EXAMPLE, "nonpolymer_entity_groups"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch non-polymer entity groups (clusters of related ligands) by group ID.

    Default fields: group name, description, member count, and member ids.
    """
    return await _query_batch("nonpolymer_entity_groups", group_ids, fields)


async def rcsb_get_uniprot(
    uniprot_id: Annotated[str, Field(description=get_uniprot.UNIPROT_ID_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_uniprot.FIELDS_EXAMPLE, "uniprot"))
    ] = None,
) -> dict[str, Any]:
    """Fetch the UniProt record RCSB maps to an accession, e.g. "P69905".

    Default fields give a functional snapshot: accession(s), entry name, protein and gene
    names, EC number, the UniProt function comment, source organism, and keywords (which
    often summarize biology directly, e.g. "ATP-binding", "Viral attachment to host entry
    receptor").

    RCSB's UniProt integration is rich — `fields` can also pull the heavier annotation sets
    (kept out of the default because they can run to hundreds of entries):
    `rcsb_uniprot_annotation` (GO terms, InterPro, disease associations),
    `rcsb_uniprot_feature` (domains, sites, binding sites, sequence variants), and
    `rcsb_uniprot_external_reference`.
    """
    return await _query_single("uniprot", uniprot_id, fields)


async def rcsb_get_pubmed(
    pubmed_id: Annotated[int, Field(description=get_pubmed.PUBMED_ID_DOC)],
    fields: Annotated[
        str | None, Field(description=_fields_doc(get_pubmed.FIELDS_EXAMPLE, "pubmed"))
    ] = None,
) -> dict[str, Any]:
    """Fetch the PubMed record for a citation by its integer ID, e.g. 6726807.

    Default fields: PubMed Central ID, DOI, abstract text.
    """
    return await _query_single("pubmed", pubmed_id, fields)


async def rcsb_get_group_provenance(
    group_provenance_id: Annotated[
        str, Field(description=get_group_provenance.GROUP_PROVENANCE_ID_DOC)
    ],
    fields: Annotated[
        str | None,
        Field(
            description=_fields_doc(
                get_group_provenance.FIELDS_EXAMPLE, "group_provenance"
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Fetch provenance/method metadata for a grouping, e.g. "provenance_sequence_identity".

    Default fields: the aggregation method/type and provenance id.
    """
    return await _query_single("group_provenance", group_provenance_id, fields)


# The rcsb_get_* / rcsb_describe_data_object tools are the Data API tools;
# register_data_tools wires each onto the passed FastMCP instance (equivalent to the @mcp.tool
# decorator, but the functions stay importable/testable on their own). Original tool order is
# preserved.
_DATA_TOOLS = (
    rcsb_describe_data_object,
    rcsb_get_entries,
    rcsb_get_polymer_entities,
    rcsb_get_nonpolymer_entities,
    rcsb_get_branched_entities,
    rcsb_get_polymer_entity_instances,
    rcsb_get_nonpolymer_entity_instances,
    rcsb_get_branched_entity_instances,
    rcsb_get_assemblies,
    rcsb_get_interfaces,
    rcsb_get_chem_comps,
    rcsb_get_entry_groups,
    rcsb_get_polymer_entity_groups,
    rcsb_get_nonpolymer_entity_groups,
    rcsb_get_uniprot,
    rcsb_get_pubmed,
    rcsb_get_group_provenance,
)


def register_data_tools(mcp) -> None:
    """Attach the RCSB Data API tools (rcsb_get_* / rcsb_describe_data_object) to a FastMCP server."""
    for fn in _DATA_TOOLS:
        mcp.tool(annotations=READ_ONLY)(fn)
