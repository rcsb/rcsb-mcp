"""GraphQL execution + schema-introspection + error-enrichment layer.

Sits ABOVE :mod:`rcsb_mcp.client` (raw transport) and BELOW the tool packages: it runs
a builder's GraphQL body and returns the selected field (:func:`_graphql_field`),
introspects the live schema to power the ``rcsb_describe_*`` field-discovery tools
(:func:`_root_field_types` / :func:`_type_fields` / :func:`_walk_into` /
:func:`_flatten_object_fields`), and rewrites a raw GraphQL ``FieldUndefined`` into a
self-correcting hint (:func:`_enrich_field_errors`). Shared by BOTH the Data API tools
and the Sequence Coordinates tools.

Like :mod:`rcsb_mcp.client`, it imports NOTHING back from :mod:`rcsb_mcp.server` (or any
tool module): the dependency runs one way, so tool definitions can live in their own
packages without a circular import.
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any

from rcsb_mcp import queries
from rcsb_mcp.client import DATA_GRAPHQL_URL, _post_graphql


async def _graphql_field(body: dict[str, Any], field: str, url: str = DATA_GRAPHQL_URL) -> Any:
    """Run a builder's GraphQL body and return data[field] (dict/list/None), raising on errors.

    An undefined-field error (from a bad `fields=` selection) is enriched with where that field
    actually lives in the schema plus the discovery tool, so a wrong guess becomes one guided fix
    rather than blind retry (see _enrich_field_errors). Other errors pass through verbatim.
    """
    payload = await _post_graphql(body["query"], body.get("variables"), url=url)
    if payload.get("errors"):
        msgs = "; ".join(e.get("message", "") for e in payload["errors"])
        raise RuntimeError(f"RCSB GraphQL error: {await _enrich_field_errors(msgs, field, url)}")
    return (payload.get("data") or {}).get(field)


# --------------------------------------------------------------------------- #
# GraphQL schema introspection (powers rcsb_describe_data_object / rcsb_describe_seqcoord_object)
# --------------------------------------------------------------------------- #
# Cached per endpoint so repeated rcsb_describe_* calls don't re-hit the service. Each
# schema is effectively static per process.
_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}
_TYPE_REF = "type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"


def _unwrap_type(type_ref: dict[str, Any] | None) -> tuple[str | None, str | None, bool]:
    """Unwrap a GraphQL type reference to (named_type, named_kind, is_list)."""
    is_list = False
    while type_ref:
        kind = type_ref.get("kind")
        if kind == "LIST":
            is_list = True
        if kind not in ("LIST", "NON_NULL"):
            return type_ref.get("name"), kind, is_list
        type_ref = type_ref.get("ofType")
    return None, None, is_list


def _field_descriptor(f: dict[str, Any]) -> dict[str, Any]:
    """Flatten one introspected field into {name, kind, type, list, description}."""
    name, kind, is_list = _unwrap_type(f.get("type"))
    return {
        "name": f.get("name"),
        "kind": "scalar" if kind in ("SCALAR", "ENUM") else "object",
        "type": name,
        "list": is_list,
        "description": f.get("description") or None,
    }


async def _root_field_types(url: str = DATA_GRAPHQL_URL) -> dict[str, str]:
    """Map each root Query field -> its (unwrapped) return type name, for one endpoint. Cached."""
    cache = _SCHEMA_CACHE.setdefault(url, {})
    if "root_types" not in cache:
        q = "{ __schema { queryType { fields { name %s } } } }" % _TYPE_REF
        payload = await _post_graphql(q, url=url)
        fields = (((payload.get("data") or {}).get("__schema") or {})
                  .get("queryType") or {}).get("fields") or []
        cache["root_types"] = {f["name"]: _unwrap_type(f["type"])[0] for f in fields}
    return cache["root_types"]


async def _type_fields(type_name: str, url: str = DATA_GRAPHQL_URL) -> list[dict[str, Any]]:
    """Introspect one type's fields (name/type/description) on one endpoint. Cached per type."""
    cache = _SCHEMA_CACHE.setdefault(url, {}).setdefault("types", {})
    if type_name not in cache:
        q = '{ __type(name: "%s") { fields { name description %s } } }' % (type_name, _TYPE_REF)
        payload = await _post_graphql(q, url=url)
        t = (payload.get("data") or {}).get("__type")
        cache[type_name] = (t or {}).get("fields") or []
    return cache[type_name]


async def _walk_into(root_field: str, url: str, into: str | None) -> tuple[str, str, str]:
    """Resolve `root_field`'s GraphQL type on `url`, then walk `into` down nested object fields.

    Returns (type_name, type_chain, field_prefix): the type reached, the "A -> B" chain of type
    names traversed (for display), and the normalized dotted field path walked — so a caller can
    emit root-relative field paths. Raises on an unknown segment or one that is a scalar.
    Shared by rcsb_describe_data_object and rcsb_describe_seqcoord_object.
    """
    type_name = (await _root_field_types(url)).get(root_field)
    if not type_name:
        raise ValueError(f"could not resolve a GraphQL type for root field {root_field!r}")
    chain = [type_name]
    segments: list[str] = []
    for seg in (into.split(".") if into else []):
        seg = seg.strip()
        if not seg:
            continue
        match = next((f for f in await _type_fields(type_name, url) if f.get("name") == seg), None)
        if match is None:
            raise ValueError(f"field {seg!r} not found on type {type_name!r}")
        nxt, kind, _ = _unwrap_type(match.get("type"))
        if kind in ("SCALAR", "ENUM"):
            raise ValueError(f"field {seg!r} is a scalar ({nxt}); nothing to drill into")
        type_name = nxt
        chain.append(type_name)
        segments.append(seg)
    return type_name, " -> ".join(chain), ".".join(segments)



# Bounds for the flat field catalog (rcsb_describe_data_object with max_depth>1). The Data API
# GraphQL schema is a
# large, CYCLIC graph, so a recursive flatten must be bounded three ways: a per-path depth cap
# (the tool's max_depth), a cap on returned rows (keeps the catalog out of context bloat), and a
# hard cap on nodes visited (a backstop so a broad no-keyword walk can't run away). Cycles are
# broken by refusing to re-enter a type already on the current path (see _flatten_object_fields).
DATA_FIELDS_RESULT_CAP = 300
DATA_FIELDS_NODE_CAP = 20000
# A cold flatten introspects every distinct type in the subtree (~100+ round-trips at depth 4);
# fetch each breadth-first level's types concurrently, bounded so we stay polite (avoid 429s).
DATA_FIELDS_FETCH_CONCURRENCY = 8


async def _flatten_object_fields(
    root_type: str, url: str, max_depth: int, query: str | None, max_results: int,
    path_prefix: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    """Breadth-first flatten of a GraphQL type into dotted field paths, filtered by keyword.

    `path_prefix` is prepended to each emitted path (used when the caller scoped the walk with
    `into=`, so the returned paths stay root-relative and can be pasted straight into `fields=`).
    It is deliberately NOT part of the `query` match: filtering runs on the path RELATIVE to the
    walk root, so a scoped depth-1 walk matches on the field's own name (what a level listing
    should do) and an unscoped walk matches on the full path.

    Walks nested object fields up to `max_depth` levels deep, recording every field as a
    dotted path (e.g. "pubmed.rcsb_pubmed_abstract_text"). Guards against the schema's cycles
    by not re-entering a type already on the current path — so a type may still appear under
    different branches, but a back-reference (entry -> polymer_entities -> entry) stops. Returns
    (fields, truncated); `truncated` is True if the result cap or node backstop cut the walk short.
    Breadth-first so, when truncated, the shallower (usually more relevant) fields are the ones kept.

    Each level's distinct types are introspected concurrently (bounded by
    DATA_FIELDS_FETCH_CONCURRENCY) to keep a cold walk's wall-clock reasonable; _type_fields
    caches per type, so the subsequent per-node reads are served from cache.
    """
    ql = query.strip().lower() if query and query.strip() else None
    results: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(DATA_FIELDS_FETCH_CONCURRENCY)

    async def _warm(type_name: str) -> None:
        async with sem:
            await _type_fields(type_name, url)

    # level items: (type_name, path_prefix, ancestor_types_on_path, depth)
    level: list[tuple[str, str, frozenset[str], int]] = [(root_type, "", frozenset({root_type}), 1)]
    nodes = 0
    while level:
        # Warm the cache for every distinct type on this level in parallel before reading them.
        await asyncio.gather(*(_warm(t) for t in {item[0] for item in level}))
        nxt: list[tuple[str, str, frozenset[str], int]] = []
        for type_name, prefix, ancestors, depth in level:
            for raw in await _type_fields(type_name, url):
                nodes += 1
                if nodes > DATA_FIELDS_NODE_CAP:
                    return results, True
                d = _field_descriptor(raw)
                path = f"{prefix}.{d['name']}" if prefix else d["name"]
                if ql is None or ql in path.lower() or ql in (d["description"] or "").lower():
                    results.append({
                        "path": f"{path_prefix}.{path}" if path_prefix else path,
                        "kind": d["kind"], "type": d["type"],
                        "list": d["list"], "description": d["description"],
                    })
                    if len(results) >= max_results:
                        return results, True
                if (d["kind"] == "object" and d["type"] and depth < max_depth
                        and d["type"] not in ancestors):
                    nxt.append((d["type"], path, ancestors | {d["type"]}, depth + 1))
        level = nxt
    return results, False


# --- Field-error enrichment: turn a raw GraphQL "FieldUndefined" into a self-correcting hint --- #
# graphql-java validation message, e.g. "Field 'rcsb_entity_source_organism' in type 'CoreEntry'
# is undefined". This is the choke point that catches a bad `fields=` guess (the schema has no
# interfaces/unions/args, so an undefined field is always a genuine mistake, never ambiguity).
_FIELD_UNDEFINED_RE = re.compile(r"Field '([^']+)' in type '([^']+)' is undefined")
# A malformed `fields=` selection (e.g. paths the normalizer couldn't expand) reaches the parser
# and comes back as a syntax error; match it so we can explain the accepted format instead.
_SYNTAX_ERR_RE = re.compile(r"invalid syntax|token recognition|antlr|parse error", re.IGNORECASE)
# Reverse the DATA_OBJECTS registry so an error carrying a root field can name the object_key to
# fix it with (currently an identity map, but kept derived so it stays correct if they diverge).
_ROOT_FIELD_TO_OBJECT_KEY = {spec.root_field: key for key, spec in queries.DATA_OBJECTS.items()}


async def _enrich_field_errors(msgs: str, root_field: str, url: str) -> str:
    """Rewrite a GraphQL undefined-field error into an actionable, self-correcting message.

    For each undefined field named in `msgs`, add (best-effort) where that field actually lives in
    the schema and a close-name suggestion on the offending type, then steer to the field-discovery
    tool — so a wrong `fields=` guess becomes one guided fix instead of blind retry. A malformed
    selection (syntax error) instead gets the accepted `fields=` format explained. Returns the
    original `msgs` unchanged for other errors, or if schema introspection is unavailable.
    """
    is_data = url == DATA_GRAPHQL_URL

    def _discover(example: str) -> str:
        return (
            f'rcsb_describe_data_object("{_ROOT_FIELD_TO_OBJECT_KEY.get(root_field, root_field)}", '
            f'query="{example}", max_depth=3)' if is_data
            else f'rcsb_describe_seqcoord_object("{root_field}", query="{example}")'
        )

    undefined = _FIELD_UNDEFINED_RE.findall(msgs)
    if not undefined:
        if _SYNTAX_ERR_RE.search(msgs):
            return (
                f"{msgs}. The `fields=` value must be a GraphQL selection: dotted paths like "
                '"struct.title exptl.method" or braces like "struct { title }" (the two may be '
                "mixed), with multiple paths separated by spaces or commas. Discover valid paths "
                f"with {_discover('<keyword>')}, and pass verified paths (never guess)."
            )
        return msgs
    example = undefined[0][0]
    discover = _discover(example)
    try:
        root_type = (await _root_field_types(url)).get(root_field)
    except Exception:
        root_type = None
    hints: list[str] = []
    for field_name, type_name in undefined[:3]:  # cap so the message stays readable
        parts = [f"Field '{field_name}' is not defined on type '{type_name}'."]
        try:  # close-name suggestion (typo) among the offending type's real fields
            siblings = [f.get("name") for f in await _type_fields(type_name, url)]
            close = difflib.get_close_matches(field_name, [s for s in siblings if s], n=3, cutoff=0.7)
            if close:
                parts.append("Did you mean: " + ", ".join(close) + "?")
        except Exception:
            pass
        if root_type:  # relocation: where this exact field name lives under the root object
            try:
                found, _ = await _flatten_object_fields(root_type, url, 3, field_name, 50)
                elsewhere = [f["path"] for f in found if f["path"].split(".")[-1] == field_name][:5]
                if elsewhere:
                    parts.append("It exists in the schema at: " + ", ".join(elsewhere) + ".")
            except Exception:
                pass
        hints.append(" ".join(parts))
    return (" ".join(hints)
            + f" Discover valid paths with {discover}, then pass verified paths to `fields=` "
              "(never guess field names).")
