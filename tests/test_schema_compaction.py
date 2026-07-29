"""The pydantic-generated schema noise stays stripped, and the load-bearing parts don't.

Every tool schema is generated from the function signature, and pydantic emits three
keywords that cost tokens in every request while carrying no information the model
doesn't already have from the key beside them. ``tooling.compact_tool_schemas`` drops
them at the composition root; this pins that it happened and, more importantly, that it
did not overreach.

The negative assertions are the cheap half. The positive ones are the point: a future
"strip more keywords" edit that also took non-null defaults or descriptions would leave
the model guessing what `limit` does when omitted, and no other test would notice.

No network, no API key, no model.
"""

import asyncio
from typing import Any

from rcsb_mcp import server


def _schemas() -> list[tuple[str, str, dict[str, Any]]]:
    """(tool name, which schema, schema) for every registered tool, as the client sees it."""
    tools = asyncio.run(server.mcp.list_tools())
    out: list[tuple[str, str, dict[str, Any]]] = []
    for t in tools:
        out.append((t.name, "inputSchema", t.inputSchema or {}))
        if getattr(t, "outputSchema", None):
            out.append((t.name, "outputSchema", t.outputSchema))
    assert out, "no tools registered"
    return out


# Keys inside these maps are names the author chose, not schema keywords. Spelled out
# here independently of the implementation, because conflating the two is the bug this
# module exists to catch: `rcsb_render_report` has a *property* called `title`.
_NAME_MAPS = ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas")

# Every JSON Schema keyword a property could collide with. Deliberately the WHOLE
# vocabulary, not just the three keys compaction removes today: the point is that a
# property is safe because of WHERE it sits, never because of what it is called, so a
# future field named `description` or `format` is covered the day it lands. Two names
# in this server already collide — `ReportRequest.title` and `rcsb_search_by_seqmotif`'s
# `pattern` — and `pattern` is the PROSITE domain term, so renaming out of the problem
# was never on the table.
_JSON_SCHEMA_KEYWORDS = frozenset({
    "$anchor", "$comment", "$defs", "$dynamicAnchor", "$dynamicRef", "$id", "$ref",
    "$schema", "$vocabulary", "additionalProperties", "allOf", "anyOf", "const",
    "contains", "contentEncoding", "contentMediaType", "contentSchema", "default",
    "definitions", "dependentRequired", "dependentSchemas", "deprecated", "description",
    "else", "enum", "examples", "exclusiveMaximum", "exclusiveMinimum", "format", "if",
    "items", "maxContains", "maxItems", "maxLength", "maxProperties", "maximum",
    "minContains", "minItems", "minLength", "minProperties", "minimum", "multipleOf",
    "not", "oneOf", "pattern", "patternProperties", "prefixItems", "properties",
    "propertyNames", "readOnly", "required", "then", "title", "type", "unevaluatedItems",
    "unevaluatedProperties", "uniqueItems", "writeOnly",
})


def _walk(node: Any, path: str = ""):
    """Yield (path, keyword, value) for every schema KEYWORD — never a property name."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _NAME_MAPS and isinstance(v, dict):
                for name, subschema in v.items():
                    yield from _walk(subschema, f"{path}.{k}.{name}")
            else:
                yield path, k, v
                yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _subschemas(node: Any):
    """Yield every dict in the schema tree, including the root."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _subschemas(v)
    elif isinstance(node, list):
        for v in node:
            yield from _subschemas(v)


def _property_names(node: Any, path: str = ""):
    """Yield (path, name) for every declared property / $def name."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _NAME_MAPS and isinstance(v, dict):
                for name, subschema in v.items():
                    yield f"{path}.{k}", name
                    yield from _property_names(subschema, f"{path}.{k}.{name}")
            else:
                yield from _property_names(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _property_names(v, f"{path}[{i}]")


# --- the noise is gone --------------------------------------------------------
def test_no_schema_titles_survive():
    """`title` is pydantic restating the key it sits next to — 2,675 tokens of it."""
    found = [
        f"{name}.{which}{path}: {v!r}"
        for name, which, s in _schemas()
        for path, k, v in _walk(s)
        if k == "title"
    ]
    assert not found, "pydantic auto-`title` is back in the tool schemas:\n  " + "\n  ".join(found)


def test_no_null_defaults_survive():
    """`"default": null` restates the field's absence from `required`."""
    found = [
        f"{name}.{which}{path}"
        for name, which, s in _schemas()
        for path, k, v in _walk(s)
        if k == "default" and v is None
    ]
    assert not found, '`"default": null` is back in the tool schemas:\n  ' + "\n  ".join(found)


def test_no_redundant_additional_properties_survive():
    """`additionalProperties: true` restates the JSON Schema default."""
    found = [
        f"{name}.{which}{path}"
        for name, which, s in _schemas()
        for path, k, v in _walk(s)
        if k == "additionalProperties" and v is True
    ]
    assert not found, "`additionalProperties: true` is back:\n  " + "\n  ".join(found)


# --- what compaction must NOT take -------------------------------------------
def test_non_null_defaults_survive():
    """A non-null default is load-bearing: it tells the model what omitting the argument gets.

    The search assistant prompt says "pass `limit=20` (its default is 10)", which only
    parses because the model can see the default. Strip these and it has to guess.
    """
    defaults = {
        (name, path, k): v
        for name, which, s in _schemas()
        for path, k, v in _walk(s)
        if k == "default" and v is not None
    }
    assert defaults, "every non-null default vanished — compaction overreached"
    limits = {v for (_, path, _), v in defaults.items() if path.endswith(".limit")}
    assert 10 in limits, f"the documented limit default (10) is gone; saw {limits}"


def test_properties_named_like_keywords_are_not_stripped():
    """A property may be *called* `title` — dropping it is not compaction, it's deletion.

    `rcsb_render_report`'s ReportRequest has a `title` field (the page heading) and lists
    it in `required`. A walk that treats every key named `title` as pydantic noise deletes
    it, leaving a required property with no definition. That is exactly what the first
    implementation did, so this is a regression guard.

    It checks the WHOLE JSON Schema vocabulary, not only the keys compaction removes
    today, because the invariant is positional: a property is safe because of where it
    sits, never because of what it is called. A field named `format` or `description`
    added next year is covered without touching this test.
    """
    schemas = _schemas()
    collisions = [
        (name, which, path, prop)
        for name, which, s in schemas
        for path, prop in _property_names(s)
        if prop in _JSON_SCHEMA_KEYWORDS
    ]
    assert collisions, (
        "no property is named like a schema keyword any more — this guard has no specimen "
        "left and is toothless. Re-point it at a current collision; do not delete it."
    )
    for name, which, path, prop in collisions:
        schema = next(s for n, w, s in schemas if n == name and w == which)
        node = schema
        for step in path.lstrip(".").split("."):
            node = node[step]
        assert prop in node, (
            f"{name}.{which}{path}.{prop} was stripped — it is a property, not a keyword"
        )


def test_known_keyword_named_properties_are_still_present():
    """The two live specimens, pinned by name so a silent rename can't hollow out the guard above.

    `test_properties_named_like_keywords_are_not_stripped` only proves that whatever
    collisions exist survive — it passes vacuously if they are all renamed away. These are
    the two that exist today; if one is deliberately renamed, update this list in the same
    commit so the coverage loss is visible in review rather than silent.
    """
    found = {
        prop for _, _, s in _schemas() for _, prop in _property_names(s)
        if prop in _JSON_SCHEMA_KEYWORDS
    }
    expected = {"title", "pattern"}  # ReportRequest.title, rcsb_search_by_seqmotif.pattern
    assert expected <= found, f"keyword-named properties disappeared: {sorted(expected - found)}"


def test_required_properties_are_all_defined():
    """Every name in a `required` array must have a matching property — the failure mode above."""
    dangling = []
    for name, which, s in _schemas():
        for node in _subschemas(s):
            req = node.get("required")
            if isinstance(req, list):
                props = set(node.get("properties", {}))
                dangling += [
                    f"{name}.{which}: required {r!r} has no property" for r in req if r not in props
                ]
    assert not dangling, "\n  ".join(dangling)


def test_field_descriptions_survive():
    """Descriptions carry the gotchas (id-as-string, lineage semantics) — never compact them."""
    descs = [
        v for _, _, s in _schemas() for _, k, v in _walk(s) if k == "description" and str(v).strip()
    ]
    assert len(descs) >= 71, f"only {len(descs)} descriptions left — compaction overreached"
    # The one the first implementation silently destroyed, pinned by content.
    assert any("Page title describing the search" in str(d) for d in descs), (
        "rcsb_render_report's `title` field lost its description"
    )


def test_closed_objects_stay_closed():
    """`additionalProperties: false` is a real constraint, unlike its `true` twin."""
    closed = [
        f"{name}.{which}{path}"
        for name, which, s in _schemas()
        for path, k, v in _walk(s)
        if k == "additionalProperties" and v is False
    ]
    assert closed, "every `additionalProperties: false` was stripped — that one is load-bearing"


def test_schemas_are_still_structurally_valid():
    """Compaction rebuilt each dict; every $ref must still resolve and every tool keep its shape."""
    for name, which, s in _schemas():
        assert s.get("type") == "object", f"{name}.{which} lost its root type"
        assert "properties" in s or which == "outputSchema", f"{name}.{which} lost its properties"
        defs = set(s.get("$defs", {}))
        refs = {
            v.rsplit("/", 1)[-1] for _, k, v in _walk(s) if k == "$ref" and isinstance(v, str)
        }
        assert refs <= defs, f"{name}.{which} has dangling $refs: {sorted(refs - defs)}"
