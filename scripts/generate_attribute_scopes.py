#!/usr/bin/env python3
"""Generate the attribute SCOPE map — the granularity each searchable attribute lives at.

Why this exists
---------------
The Search API intersects multiple conditions at the level named by ``return_type``, not
at the level the attributes belong to. AND two polymer-entity conditions but ask for
entries and a structure matches when *different* molecules satisfy each one. Measured on
``AND(source_organism=Homo sapiens, source_organism=Escherichia coli)``:

    return_type=entry            745 entries
    return_type=polymer_entity   550 entities -> 550 distinct parent entries

195 entries (26% of the entry-level answer) are there only because two different molecules
matched. Nothing in the response distinguishes them, so the wrong answer looks normal.

Detecting that needs one fact per attribute: the object it hangs off. This generator
derives it rather than guessing from the path, because the path is a poor guide — every
``em_*`` root (~15 roots, ~100 attributes) is entry-scoped and none says so, while
``entity_src_gen``, ``entity_poly``, ``drugbank_info`` and ``rcsb_entity_source_organism``
are all finer than they read.

How the scope is derived
------------------------
The Data API GraphQL schema IS the containment structure: each root object
(``entries``, ``polymer_entities``, ``assemblies``, ...) exposes exactly the attribute
roots that hang off it. So:

  depth 1  the attribute root is a field of a scope object          -> that scope
  depth 2  it is a field of one of those fields (``entry.pubmed``,
           ``polymer_entity.uniprots``, ``chem_comp.drugbank``)     -> the owning scope

Depth 1 always wins; depth 2 is consulted only for roots depth 1 could not place. That
ordering matters — a depth-2 sweep on its own reports a root at every level that happens
to reach it.

Both catalogs get their own map. That is not symmetry for its own sake: ``rcsb_id`` is
"entry and entity identifiers" in the structure schema and "the chemical definition" in
the chemical one, so a single shared map would silently carry one of them wrong.

Usage:
    python scripts/generate_attribute_scopes.py            # (re)write the map
    python scripts/generate_attribute_scopes.py --check    # exit 1 if stale (no write)

Run scripts/generate_search_attributes.py FIRST when refreshing both: this reads the
vendored catalogs, so the scope map stays in sync with them by construction and --check
fails when a catalog gains an attribute this map has not placed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
import urllib.request

_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES  # noqa: E402
from rcsb_mcp.graphql import (  # noqa: E402
    DATA_GRAPHQL_URL,
    _root_field_types,
    _type_fields,
    _unwrap_type,
)
from rcsb_mcp.queries import RETURN_TYPES  # noqa: E402
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES  # noqa: E402

_OUT = _ROOT / "src" / "rcsb_mcp" / "attribute_scopes.py"

# Data API root field -> the granularity it represents. Deliberately NOT every root the
# Data API exposes: `pubmed`, `uniprot`, `interfaces` and the `*_groups` roots are not
# structure granularities, so they are left out and their attributes resolve through the
# object that OWNS them at depth 2 (entry.pubmed -> entry, polymer_entity.uniprots ->
# polymer_entity). Including them here would invent `pubmed` as a scope of its own.
SCOPE_OF_ROOT_FIELD = {
    "entries": "entry",
    "assemblies": "assembly",
    "polymer_entities": "polymer_entity",
    "nonpolymer_entities": "non_polymer_entity",
    "branched_entities": "branched_entity",
    "polymer_entity_instances": "polymer_instance",
    "nonpolymer_entity_instances": "non_polymer_instance",
    "branched_entity_instances": "branched_instance",
    "chem_comps": "mol_definition",
}

# How deep each scope sits in the containment hierarchy. Used only to collapse a root
# that resolves to several scopes down to the COARSEST one — the conservative direction,
# since a coarser scope can only make the split detector quieter, never noisier.
#
# Ties in RANK are NOT broken alphabetically. An earlier version did, documented as
# "purely for determinism" and asserted harmless; it was not. rcsb_ligand_neighbors
# resolves to {branched_instance, polymer_instance}, both rank 2, and the alphabetical
# winner branched_instance has NO return_type — so the map reported a granularity nothing
# can narrow to, when polymer_instance was available and narrows correctly:
#     AND(ligand_comp_id=ATP, ligand_comp_id=HEM)  @entry 5  ->  @polymer_instance 0
# Ties therefore prefer a scope a caller can actually ASK for, and fall back to the name
# only when neither has a return_type.
SCOPE_RANK = {
    "entry": 0,
    "assembly": 1, "polymer_entity": 1, "non_polymer_entity": 1,
    "branched_entity": 1, "mol_definition": 1,
    "polymer_instance": 2, "non_polymer_instance": 2, "branched_instance": 2,
}

# An attribute whose VALUE is the parent entry's id is identical across every sibling in
# that entry, so two conditions on it can never be satisfied by different siblings — it
# behaves as entry-scoped no matter which object it is filed under. Enumerated by an
# exact leaf-name rule rather than inferred, and asserted in the generated module so the
# list stays reviewable.
_ENTRY_CONSTANT_LEAF = "entry_id"

# Each catalog is indexed over its OWN root, so each gets its own owner map. The chemical
# schema indexes chemical definitions and nothing else; resolving its roots against the
# structure objects as well placed `rcsb_id` at "entry", when the chemical schema documents
# it as "a unique identifier for the chemical definition in this container". Every other
# chemical root is mol_definition, so that one entry stuck out as visibly wrong — a shared
# owner map cannot represent an attribute name that means different things in each index.
CATALOGS = [
    {
        "name": "structure",
        "catalog": SEARCH_ATTRIBUTES,
        "var": "SEARCH_ATTRIBUTE_SCOPES",
        "scope_roots": SCOPE_OF_ROOT_FIELD,
        "schema_url": "https://search.rcsb.org/rcsbsearch/v2/metadata/schema",
    },
    {
        "name": "chemical",
        "catalog": CHEMICAL_SEARCH_ATTRIBUTES,
        "var": "CHEMICAL_ATTRIBUTE_SCOPES",
        "scope_roots": {"chem_comps": "mol_definition"},
        "schema_url": "https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema",
    },
]


def repeating_and_nested_roots(schema_url: str) -> tuple[list[str], list[str]]:
    """Roots that hold MANY records per object, split by whether the API keeps them coherent.

    Scope alone does not make a loose intersection detectable. `software.name` and
    `software.classification` are both entry-scoped, so any scope-equality check stays
    silent — yet an entry holds a LIST of software records, and each condition may land on
    a different one:

        AND(software.name ~ "PHENIX", software.classification ~ "data reduction")
        -> 80,050 entries; of 25 sampled, 18 (72%) have no single software record with both

    That is the same failure as the cross-molecule case one level down, and it affects
    roots at every scope, entry included. So the map records repetition as well.

    The split between the two lists is the part that decides what can be DONE about it:

      nested-indexed (the API tracks the record)  -> keeping the conditions in their own
          group preserves coherence, so this is fixable at the query level
      repeating but not nested-indexed            -> the API offers no such guarantee, so
          nothing in the query can force the conditions onto one record

    Nested indexing is recorded as PATHS, not roots. The flag sits wherever the coherent
    record actually is, which is often a sub-object rather than the top of the path —
    `rcsb_uniprot_container_identifiers` is not itself nested-indexed but its
    `.reference_sequence_identifiers` is, and 5 other roots have the same shape. Marking
    the whole root nested would claim coherence the API does not offer for its other
    fields; an attribute is coherent-able only when it sits under one of these paths.

    Returns (repeating roots, nested paths).
    """
    with urllib.request.urlopen(schema_url, timeout=60) as resp:
        schema = json.loads(resp.read().decode())

    nested: list[str] = []

    def walk(node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("rcsb_nested_indexing") and path:
            nested.append(path)
        items = node.get("items") if isinstance(node.get("items"), dict) else None
        if items is not None:
            # `items` is the array's element schema, not a path segment of its own.
            if items.get("rcsb_nested_indexing") and path and path not in nested:
                nested.append(path)
            walk(items, path)
        for key, val in (node.get("properties") or {}).items():
            walk(val, f"{path}.{key}" if path else key)

    walk(schema, "")
    repeating = [
        root for root, val in (schema.get("properties") or {}).items()
        if isinstance(val, dict) and val.get("type") == "array"
    ]
    return sorted(repeating), sorted(set(nested))


async def _retry(fn, *a, attempts: int = 5):
    """The Data API introspection endpoint times out intermittently under a burst."""
    for i in range(attempts):
        try:
            return await fn(*a)
        except RuntimeError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(2 * (i + 1))


async def build_owner_maps(
    scope_roots: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return (depth1, depth2): attribute-root name -> the scopes that expose it."""
    root_types = await _retry(_root_field_types, DATA_GRAPHQL_URL)
    depth1: dict[str, set[str]] = {}
    depth2: dict[str, set[str]] = {}
    for root_field, scope in scope_roots.items():
        type_name = root_types.get(root_field)
        if not type_name:
            raise RuntimeError(f"Data API no longer exposes root field {root_field!r}")
        for field in await _retry(_type_fields, type_name, DATA_GRAPHQL_URL):
            depth1.setdefault(field["name"], set()).add(scope)
            child_type, _, _ = _unwrap_type(field.get("type"))
            if not child_type:
                continue
            try:
                grandchildren = await _retry(_type_fields, child_type, DATA_GRAPHQL_URL)
            except RuntimeError:
                # Only a transport failure can land here: _type_fields returns [] for
                # scalars, enums and unknown type names rather than raising. An earlier
                # `except Exception` claimed to be skipping scalar children, which it
                # never did — it could only have swallowed real errors.
                continue
            for g in grandchildren:
                depth2.setdefault(g["name"], set()).add(scope)
    return depth1, depth2


def _collapse(scopes: set[str]) -> str:
    """The coarsest scope in the set, preferring one a caller can name as a return_type."""
    return min(sorted(scopes), key=lambda s: (SCOPE_RANK[s], s not in RETURN_TYPES, s))


def build_scope_map(
    catalog: list[dict], depth1: dict[str, set[str]], depth2: dict[str, set[str]]
) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """Map every attribute ROOT in `catalog` to one scope.

    Returns (root -> scope, ambiguous root -> the scopes it resolved to, unplaced roots).
    """
    roots = sorted({a["attribute"].split(".")[0] for a in catalog})
    scopes: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    unplaced: list[str] = []
    for root in roots:
        found = depth1.get(root) or depth2.get(root)
        if not found:
            unplaced.append(root)
            continue
        if len(found) > 1:
            ambiguous[root] = sorted(found)
        scopes[root] = _collapse(found)
    return scopes, ambiguous, unplaced


def entry_constant_attributes(catalog: list[dict]) -> list[str]:
    """Attributes filed under a fine root whose value is the parent entry's id."""
    return sorted(
        a["attribute"] for a in catalog
        if a["attribute"].rsplit(".", 1)[-1] == _ENTRY_CONSTANT_LEAF and "." in a["attribute"]
    )


def render_module(results: list[dict]) -> str:
    """Render the vendored module. Pure data — the lookup logic lives in queries.py."""
    def block(obj) -> str:
        return json.dumps(obj, indent=4, ensure_ascii=False, sort_keys=True)

    parts = [
        '"""Scope (granularity) of every searchable RCSB attribute.\n\n'
        "Auto-generated by scripts/generate_attribute_scopes.py from the Data API GraphQL\n"
        "schema plus the vendored attribute catalogs. Do not edit by hand.\n\n"
        "The maps are keyed by the attribute's ROOT path segment, which is what determines\n"
        "the object it hangs off; `queries.scope_of` does the lookup and applies the\n"
        "entry-constant overrides below. Kept per catalog because `rcsb_id` denotes the\n"
        "entity container in the structure schema and the chemical definition in the\n"
        "chemical one.\n"
        '"""\n\n'
        "from rcsb_mcp.attribute_types import AttributeScope\n"
    ]
    for r in results:
        parts.append(
            f"\n# {r['name']}: {len(r['scopes'])} roots covering {r['n_attributes']} attributes.\n"
            f"{r['var']}: dict[str, AttributeScope] = {block(r['scopes'])}\n"
        )
        if r["ambiguous"]:
            parts.append(
                f"\n# Roots the Data API exposes at more than one granularity, collapsed above to\n"
                f"# the COARSEST — the direction that can only make the split detector quieter.\n"
                f"# Recorded so the collapse is visible rather than buried in the map.\n"
                f"{r['var'].replace('_SCOPES', '_AMBIGUOUS_ROOTS')}: "
                f"dict[str, list[AttributeScope]] = {block(r['ambiguous'])}\n"
            )
        parts.append(
            f"\n# Attributes filed under a finer root whose VALUE is the parent entry's id, so it\n"
            f"# is identical across every sibling and two conditions on it can never be met by\n"
            f"# different siblings. `queries.scope_of` returns \"entry\" for these.\n"
            f"{r['var'].replace('_SCOPES', '_ENTRY_CONSTANT')}: list[str] = {block(r['entry_constant'])}\n"
        )
        parts.append(
            f"\n# Roots holding MANY records per object ({len(r['repeating'])} of {len(r['scopes'])}).\n"
            f"# Two conditions on one of these can land on DIFFERENT records of the SAME object, so\n"
            f"# scope equality does not mean the conditions co-occur — software.name and\n"
            f"# software.classification are both entry-scoped, yet 18 of 25 sampled hits for\n"
            f"# AND(name~PHENIX, classification~'data reduction') have no single record with both.\n"
            f"{r['var'].replace('_SCOPES', '_REPEATING_ROOTS')}: list[str] = {block(r['repeating'])}\n"
            f"\n# The PATHS the Search API nested-indexes ({len(r['nested'])}): it tracks the record, so\n"
            f"# conditions kept together in their OWN group are required to hold on one record.\n"
            f"# That makes these fixable at the query level; the rest of the repeating roots are not.\n"
            f"# Paths, not roots: the flag sits on the coherent sub-object, which for 6 roots is a\n"
            f"# descendant (rcsb_uniprot_container_identifiers.reference_sequence_identifiers, ...),\n"
            f"# so an attribute is coherent-able only when it sits UNDER one of these prefixes.\n"
            f"{r['var'].replace('_SCOPES', '_NESTED_ROOTS')}: list[str] = {block(r['nested'])}\n"
        )
    return "".join(parts)


async def generate() -> str:
    results = []
    for spec in CATALOGS:
        depth1, depth2 = await build_owner_maps(spec["scope_roots"])
        scopes, ambiguous, unplaced = build_scope_map(spec["catalog"], depth1, depth2)
        if unplaced:
            raise RuntimeError(
                f"{spec['name']}: {len(unplaced)} attribute root(s) could not be placed in the "
                f"Data API object graph: {unplaced}. A silently missing scope would make the "
                f"split detector skip those attributes, so this is fatal rather than a warning."
            )
        repeating, nested = repeating_and_nested_roots(spec["schema_url"])
        known = set(scopes)
        results.append({
            **spec,
            "scopes": scopes,
            "ambiguous": ambiguous,
            "entry_constant": entry_constant_attributes(spec["catalog"]),
            "n_attributes": len(spec["catalog"]),
            # Restricted to roots this catalog actually exposes, so the lists describe
            # attributes a caller can really filter on rather than the whole schema.
            "repeating": [r for r in repeating if r in known],
            "nested": [n for n in nested if n.split(".")[0] in known],
        })
    return render_module(results)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed map is stale (no write)")
    args = ap.parse_args()

    module = asyncio.run(generate())
    if args.check:
        current = _OUT.read_text() if _OUT.exists() else ""
        if current != module:
            print(f"STALE: {_OUT.name} differs from the live Data API object graph")
            return 1
        print(f"OK: {_OUT.name} up to date")
        return 0
    _OUT.write_text(module)
    print(f"wrote {_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
