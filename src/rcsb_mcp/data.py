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
from rcsb_mcp.graphql import (
    DATA_FIELDS_RESULT_CAP,
    _flatten_object_fields,
    _graphql_field,
    _walk_into,
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
    object_key: DataObjectKey,
    into: str | None = None,
    query: str | None = None,
    max_depth: Annotated[int, Field(ge=1, le=6)] = 1,
) -> dict[str, Any]:
    """Discover the fields available on a Data API object, from the live GraphQL schema.

    Use this to find exactly what to request in a rcsb_get_* tool's `fields=` argument.
    The rcsb_get_* default selections are compact summaries, but the
    underlying GraphQL types have far more (e.g. CoreEntry has ~100 fields). Every path it
    returns is verified against the live schema, so it is safe to pass to `fields=` directly.

    Two ways to use it, both returning dotted paths ready for `fields=`:
    - BROWSE a level (default, max_depth=1): list one object's own fields, then drill into a
      nested one with `into`. Workflow: rcsb_describe_data_object("entries") -> spot a nested
      object such as "rcsb_entry_info" -> rcsb_describe_data_object("entries",
      into="rcsb_entry_info") to list its leaves.
    - SEARCH by keyword: raise `max_depth` (e.g. 3) and pass `query` to flatten the object's
      whole tree — including nested and cross-object paths like
      "pubmed.rcsb_pubmed_abstract_text" — and keep only matching fields.
    Combine them: `into` scopes the walk, so into="rcsb_polymer_entity", max_depth=2 searches
    just that sub-tree (cheaper and more focused than flattening from the root).

    Each returned field has:
    - path: dotted path from the object root, ready to use in `fields=`
    - kind: "scalar" (a leaf you can select directly) or "object" (drill in, or select with a
      sub-selection)
    - type: the field's GraphQL type name
    - list: whether the field returns a list
    - description: schema description, when present

    Args:
        object_key: Which object to describe — the key matching the rcsb_get_* tool.
        into: Optional dot-path of nested object field(s) to scope to, e.g.
            "rcsb_entry_info" or "polymer_entities.rcsb_polymer_entity".
        query: Optional case-insensitive keyword, matched against each field's path (relative
            to the scope) and its description, e.g. "resolution", "abstract", "organism".
        max_depth: How many levels to walk (1-6, default 1 = this level only). Depth 2 reaches
            e.g. "pubmed.rcsb_pubmed_abstract_text"; depth 3 reaches
            "polymer_entities.rcsb_polymer_entity.pdbx_description". Deeper is slower on a cold
            cache; prefer a `query` (and `into`) over a broad deep walk.

    Returns:
        {object_key, graphql_type, path, query, max_depth, field_count,
        fields:[{path, kind, type, list, description}], truncated?, note?}. When the result set
        is capped, `truncated` is true and `note` explains how to narrow it.
    """
    if object_key not in queries.DATA_OBJECTS:
        raise ValueError(f"object_key must be one of {sorted(queries.DATA_OBJECTS)}")
    root_field = queries.DATA_OBJECTS[object_key].root_field
    type_name, chain, prefix = await _walk_into(root_field, DATA_GRAPHQL_URL, into)
    fields, truncated = await _flatten_object_fields(
        type_name, DATA_GRAPHQL_URL, max_depth, query, DATA_FIELDS_RESULT_CAP, path_prefix=prefix,
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


async def rcsb_get_entries(entry_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch metadata for one or more PDB entries (title, method, resolution, size,
    dates, and primary citation).

    The response also lists the entry's component ids under
    rcsb_entry_container_identifiers — use these to drill into the structure. They are
    bare numbers; compose them with the entry id to call the matching rcsb_get_* tool:
    polymer_entity_ids/non_polymer_entity_ids "N" -> "<ENTRY>_N" (rcsb_get_polymer_entities /
    rcsb_get_nonpolymer_entities); assembly_ids "N" -> "<ENTRY>-N" (rcsb_get_assemblies).

    Args:
        entry_ids: 4-character PDB entry codes, e.g. ["4HHB", "1MBN"]; pass a one-element
            list for a single entry. Unknown IDs are returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "struct.title"); discover/verify paths with rcsb_describe_data_object("entries") (see the server instructions).
    """
    return await _query_batch("entries", entry_ids, fields)


async def rcsb_get_polymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entities (protein/nucleic-acid molecules).

    Default fields: description, length, weight, and source organism.

    Args:
        entity_ids: entry + entity number, e.g. ["4HHB_1"] — exactly what
            rcsb_search_by_sequence returns. Unknown IDs are returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_polymer_entity.pdbx_description"); discover/verify paths with
            rcsb_describe_data_object("polymer_entities")
            (see the server instructions).
    """
    return await _query_batch("polymer_entities", entity_ids, fields)


async def rcsb_get_nonpolymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer (ligand/cofactor) entities, e.g. ["4HHB_3"].

    Default fields: description, weight, copy count, and the bound chemical component ID.
    Use rcsb_get_chem_comps for the chemistry of that component.

    Args:
        entity_ids: entry + entity number, e.g. ["4HHB_3"]. Unknown IDs are returned
            under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_nonpolymer_entity.pdbx_description"); discover/verify paths with
            rcsb_describe_data_object("nonpolymer_entities")
            (see the server instructions).
    """
    return await _query_batch("nonpolymer_entities", entity_ids, fields)


async def rcsb_get_branched_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched (carbohydrate / oligosaccharide) entities, e.g. ["5FMB_2"].

    Default fields: description, weight, copy count, branch type, and component count.

    Args:
        entity_ids: entry + entity number, e.g. ["5FMB_2"]. Unknown IDs are returned
            under "not_found".
        fields: Optional GraphQL selection replacing the curated default
            (e.g. "rcsb_branched_entity.pdbx_description"); discover/verify paths with
            rcsb_describe_data_object("branched_entities")
            (see the server instructions).
    """
    return await _query_batch("branched_entities", entity_ids, fields)


async def rcsb_get_polymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity instances (individual chains), e.g. ["4HHB.A"] (entry.asym_id).

        Default fields: the entry/entity/chain identifiers and modeled-residue count.

        Args:
            instance_ids: entry.asym_id (chain), e.g. ["4HHB.A"]. Unknown IDs are returned
                under "not_found".
            fields: Optional GraphQL selection replacing the curated default
                (e.g. "rcsb_polymer_instance_info.modeled_residue_count"); discover/verify paths
                with rcsb_describe_data_object("polymer_entity_instances")
                (see the server instructions).
        """
    return await _query_batch("polymer_entity_instances", instance_ids, fields)


async def rcsb_get_nonpolymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity instances (individual bound ligands), e.g. ["4HHB.E"].

    Default fields: the entry/entity/chain identifiers, bound component id, and author seq id.

    Args:
        instance_ids: entry.asym_id, e.g. ["4HHB.E"]. Unknown IDs are returned under
            "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_nonpolymer_entity_instance_container_identifiers.comp_id"); discover/verify paths
            with rcsb_describe_data_object("nonpolymer_entity_instances")
            (see the server instructions).
    """
    return await _query_batch("nonpolymer_entity_instances", instance_ids, fields)


async def rcsb_get_branched_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch branched entity instances (individual glycan chains), e.g. ["5FMB.C"].

    Default fields: the entry/entity/chain identifiers.

    Args:
        instance_ids: entry.asym_id (glycan chain), e.g. ["5FMB.C"]. Unknown IDs are
            returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_branched_entity_instance_container_identifiers.asym_id"); discover/verify paths
            with rcsb_describe_data_object("branched_entity_instances")
            (see the server instructions).
    """
    return await _query_batch("branched_entity_instances", instance_ids, fields)


async def rcsb_get_assemblies(assembly_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological assemblies, e.g. ["4HHB-1"] (entry-assembly).

    Default fields: composition counts and oligomeric state.

    Args:
        assembly_ids: entry-assembly, e.g. ["4HHB-1"]. Unknown IDs are returned under
            "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_assembly_info.polymer_entity_instance_count"); discover/verify paths with
            rcsb_describe_data_object("assemblies") (see the server
            instructions).
    """
    return await _query_batch("assemblies", assembly_ids, fields)


async def rcsb_get_interfaces(interface_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch assembly interfaces, e.g. ["1BMV-1.1"] (entry-assembly.interface).

    Default fields: buried area, character, composition, residue count.

    Args:
        interface_ids: entry-assembly.interface, e.g. ["1BMV-1.1"]. Unknown IDs are
            returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_interface_info.interface_area"); discover/verify paths with
            rcsb_describe_data_object("interfaces") (see the
            server instructions).
    """
    return await _query_batch("interfaces", interface_ids, fields)


async def rcsb_get_chem_comps(comp_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch chemical components / ligands by their short codes, e.g. ["HEM", "ATP"].

    Default fields: name, formula, weight, type, SMILES, InChIKey.

    Args:
        comp_ids: chemical-component short codes, e.g. ["HEM", "ATP"]. Unknown IDs are
            returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "chem_comp.name"); discover/verify paths with
            rcsb_describe_data_object("chem_comps") (see the
            server instructions).
    """
    return await _query_batch("chem_comps", comp_ids, fields)


async def rcsb_get_entry_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch entry groups (clusters of related entries) by group ID.

    Default fields: group name, description, member count, and member ids.

    Args:
        group_ids: entry-group ids, e.g. ["G_1002266"]. Unknown IDs are returned under
            "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_group_info.group_name"); discover/verify paths with
            rcsb_describe_data_object("entry_groups") (see the
            server instructions).
    """
    return await _query_batch("entry_groups", group_ids, fields)


async def rcsb_get_polymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity groups (e.g. sequence clusters), e.g. ["85_70"].

    Default fields: group name, description, member count, and member ids.

    Args:
        group_ids: sequence-cluster group ids, e.g. ["85_70"]. Unknown IDs are returned
            under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_group_info.group_name"); discover/verify paths with
            rcsb_describe_data_object("polymer_entity_groups")
            (see the server instructions).
    """
    return await _query_batch("polymer_entity_groups", group_ids, fields)


async def rcsb_get_nonpolymer_entity_groups(group_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch non-polymer entity groups (clusters of related ligands) by group ID.

    Default fields: group name, description, member count, and member ids.

    Args:
        group_ids: non-polymer entity group ids, e.g. ["ATP"]. Unknown IDs are returned
            under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_group_info.group_name"); discover/verify paths with
            rcsb_describe_data_object("nonpolymer_entity_groups")
            (see the server instructions).
    """
    return await _query_batch("nonpolymer_entity_groups", group_ids, fields)


async def rcsb_get_uniprot(uniprot_id: str, fields: str | None = None) -> dict[str, Any]:
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

    Args:
        uniprot_id: a UniProt accession, e.g. "P69905".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_uniprot_protein.name"); discover/verify paths with
            rcsb_describe_data_object("uniprot") (see the
            server instructions).
    """
    return await _query_single("uniprot", uniprot_id, fields)


async def rcsb_get_pubmed(pubmed_id: int, fields: str | None = None) -> dict[str, Any]:
    """Fetch the PubMed record for a citation by its integer ID, e.g. 6726807.

    Default fields: PubMed Central ID, DOI, abstract text.

    Args:
        pubmed_id: integer PubMed ID, e.g. 6726807.
        fields: Optional GraphQL selection replacing the curated default
            (e.g. rcsb_pubmed_doi); discover/verify paths with
            rcsb_describe_data_object("pubmed") (see the
            server instructions).
    """
    return await _query_single("pubmed", pubmed_id, fields)


async def rcsb_get_group_provenance(group_provenance_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch provenance/method metadata for a grouping, e.g. "provenance_sequence_identity".

    Default fields: the aggregation method/type and provenance id.

    Args:
        group_provenance_id: a provenance token, e.g. "provenance_sequence_identity".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_group_aggregation_method.type"); discover/verify paths with
            rcsb_describe_data_object("group_provenance")
            (see the server instructions).
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
