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
    object_key: DataObjectKey | None = None,
    into: str | None = None,
    query: str | None = None,
    max_depth: Annotated[int, Field(ge=1, le=6)] | None = None,
) -> dict[str, Any]:
    """Discover the fields available on a Data API object, from the live GraphQL schema.

    Use this to find exactly what to request in a rcsb_get_* tool's `fields=` argument.
    The rcsb_get_* default selections are compact summaries, but the
    underlying GraphQL types have far more (e.g. CoreEntry has ~100 fields). Every path it
    returns is verified against the live schema, so it is safe to pass to `fields=` directly.

    NEVER invent, guess, or infer a field path from memory, from a naming convention, or
    from another API. An unverified path fails GraphQL schema validation and wastes the
    call. Paths shown in a rcsb_get_* tool's own description or examples are already
    verified — use those directly; for anything else, confirm it here FIRST.

    `fields=` accepts EITHER dotted paths ("rcsb_polymer_entity.pdbx_description") OR
    GraphQL nested-brace syntax ("rcsb_polymer_entity { pdbx_description }"); the two may
    be mixed, and multiple paths are separated by spaces or commas.

    Three ways to use it, all returning dotted paths ready for `fields=`:
    - FIND which tool has a field: pass ONLY `query` and omit `object_key`. Searches every
      object and answers with the tool to call and the path to give it, best matches first.
      Start here whenever you know what you want but not where it lives —
      rcsb_describe_data_object(query="release_date") ->
      rcsb_get_entries + "rcsb_accession_info.initial_release_date".
      A SEARCH ATTRIBUTE PATH works as the `query` too: every attribute from
      rcsb_list_pdb_search_attributes is also a Data API field, so pasting one in tells you
      which tool fetches the value you can filter on.
    - SEARCH one object: name `object_key` as well, to keep only that object's matches.
    - BROWSE a level: name `object_key` and omit `query` to list its own fields, then drill
      into a nested one with `into`. Workflow: rcsb_describe_data_object("entries") -> spot a
      nested object such as "rcsb_entry_info" -> rcsb_describe_data_object("entries",
      into="rcsb_entry_info") to list its leaves.
    The walk depth follows which one you are doing, so you do not have to set it: browsing
    lists one level, searching goes three deep. `into` scopes a search to a sub-tree (cheaper
    and more focused than flattening from the root) and needs an `object_key`.

    An empty result from a NAMED object means that object has no matching field — not that
    the field does not exist. Re-run without `object_key` to search them all.

    Each returned field has:
    - path: dotted path from the object root, ready to use in `fields=`
    - kind: "scalar" (a leaf you can select directly) or "object" (drill in, or select with a
      sub-selection)
    - type: the field's GraphQL type name
    - list: whether the field returns a list
    - description: schema description, when present
    - searchable: present (true) only when this field can ALSO be filtered on with
      rcsb_query_attribute — i.e. it is a Search API attribute as well as a Data API field.
      About 3% are. Use it to go from "I can read this" to "I can search by this" without a
      separate lookup; rcsb_list_pdb_search_attributes still has its operators and values.

    Args:
        object_key: Which object to describe — the key matching the rcsb_get_* tool. OMIT it
            to search every object at once and be told which tool owns each match; that needs
            a `query` and cannot be combined with `into`.
        into: Optional dot-path of nested object field(s) to scope to, e.g.
            "rcsb_entry_info" or "polymer_entities.rcsb_polymer_entity".
        query: Optional case-insensitive keyword, matched against each field's path (relative
            to the scope) and its description, e.g. "resolution", "abstract", "organism".
        max_depth: How many levels to walk (1-6). Omit it: the default follows what you are
            doing — 1 when browsing, 3 when searching, which is what it takes to reach
            "polymer_entities.rcsb_polymer_entity.pdbx_description". Set it only to go
            deeper still, or to cap a broad walk. Deeper is slower on a cold cache; prefer
            narrowing with `query` and `into`.

    Returns:
        For a named object: {object_key, graphql_type, path, query, max_depth, field_count,
        fields:[{path, kind, type, list, description, searchable?}], truncated?, note?}.
        Searching every object instead: {object_key: null, searched, query, max_depth,
        field_count, fields:[{tool, path, kind, type, list, description, searchable?}],
        truncated?, note?}
        — each field names the rcsb_get_* `tool` that owns it and the `path` to pass that
        tool's `fields=`. One field is reported once, attributed to the object reaching it
        most directly, and matches are ordered exact field name, then partial, then
        description-only. When the result set is capped, `truncated` is true and `note`
        explains how to narrow it.
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
            "struct.title"); discover/verify paths with rcsb_describe_data_object("entries").
    """
    return await _query_batch("entries", entry_ids, fields)


async def rcsb_get_polymer_entities(entity_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entities (protein/nucleic-acid molecules) — description, length,
    weight, and source organism.

    Default fields: description, length, weight, and source organism.

    Polymer-based (sequence) annotations can be fetched adding rcsb_polymer_entity_annotation.* fields,
    and positional features adding rcsb_polymer_entity_feature.*

    Args:
        entity_ids: entry + entity number, e.g. ["4HHB_1"] — exactly what
            rcsb_query_sequence searches return. Unknown IDs are returned under "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_polymer_entity.pdbx_description"); discover/verify paths with
            rcsb_describe_data_object("polymer_entities").
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
            rcsb_describe_data_object("nonpolymer_entities").
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
            rcsb_describe_data_object("branched_entities").
    """
    return await _query_batch("branched_entities", entity_ids, fields)


async def rcsb_get_polymer_entity_instances(instance_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch polymer entity instances (individual chains), e.g. ["4HHB.A"] (entry.asym_id).

        Instance-based (chain) annotations can be fetched adding rcsb_polymer_instance_annotation.* fields,
        and positional features rcsb_polymer_instance_feature.*

        Default fields: the entry/entity/chain identifiers and modeled-residue count.

        Args:
            instance_ids: entry.asym_id (chain), e.g. ["4HHB.A"]. Unknown IDs are returned
                under "not_found".
            fields: Optional GraphQL selection replacing the curated default
                (e.g. "rcsb_polymer_instance_info.modeled_residue_count"); discover/verify paths
                with rcsb_describe_data_object("polymer_entity_instances").
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
            with rcsb_describe_data_object("nonpolymer_entity_instances").
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
            with rcsb_describe_data_object("branched_entity_instances").
    """
    return await _query_batch("branched_entity_instances", instance_ids, fields)


async def rcsb_get_assemblies(assembly_ids: list[str], fields: str | None = None) -> dict[str, Any]:
    """Fetch biological assemblies, e.g. ["4HHB-1"] (entry-assembly).

    Default fields: composition counts and oligomeric state.

    Assembly-based (complex) annotations can be fetched adding rcsb_assembly_annotation.* fields,
    and positional features rcsb_assembly_feature.*

    Args:
        assembly_ids: entry-assembly, e.g. ["4HHB-1"]. Unknown IDs are returned under
            "not_found".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_assembly_info.polymer_entity_instance_count"); discover/verify paths with
            rcsb_describe_data_object("assemblies").
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
            rcsb_describe_data_object("interfaces").
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
            rcsb_describe_data_object("chem_comps").
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
            rcsb_describe_data_object("entry_groups").
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
            rcsb_describe_data_object("polymer_entity_groups").
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
            rcsb_describe_data_object("nonpolymer_entity_groups").
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
            rcsb_describe_data_object("uniprot").
    """
    return await _query_single("uniprot", uniprot_id, fields)


async def rcsb_get_pubmed(pubmed_id: int, fields: str | None = None) -> dict[str, Any]:
    """Fetch the PubMed record for a citation by its integer ID, e.g. 6726807.

    Default fields: PubMed Central ID, DOI, abstract text.

    Args:
        pubmed_id: integer PubMed ID, e.g. 6726807.
        fields: Optional GraphQL selection replacing the curated default
            (e.g. rcsb_pubmed_doi); discover/verify paths with
            rcsb_describe_data_object("pubmed").
    """
    return await _query_single("pubmed", pubmed_id, fields)


async def rcsb_get_group_provenance(group_provenance_id: str, fields: str | None = None) -> dict[str, Any]:
    """Fetch provenance/method metadata for a grouping, e.g. "provenance_sequence_identity".

    Default fields: the aggregation method/type and provenance id.

    Args:
        group_provenance_id: a provenance token, e.g. "provenance_sequence_identity".
        fields: Optional GraphQL selection replacing the curated default (e.g.
            "rcsb_group_aggregation_method.type"); discover/verify paths with
            rcsb_describe_data_object("group_provenance").
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
