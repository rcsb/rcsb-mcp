#!/usr/bin/env python3
"""Generate BOTH RCSB search-attribute catalogs from the live metadata schemas.

The RCSB Search API publishes its searchable attributes as JSON-Schema documents:

    structure: https://search.rcsb.org/rcsbsearch/v2/metadata/schema
    chemical:  https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema

Each searchable leaf carries an ``rcsb_search_context`` array; the supported query
operators are derived from that context plus the value type. One pipeline walks BOTH
schemas and emits the two vendored catalog modules with the identical
``{attribute, type, operators, description}`` record shape:

    src/rcsb_mcp/search_attributes.py           (SEARCH_ATTRIBUTES, structure/text)
    src/rcsb_mcp/chemical_search_attributes.py  (CHEMICAL_SEARCH_ATTRIBUTES, chemical/text_chem)

The catalogs are VENDORED, not fetched at runtime: the server boots offline, its
validation is deterministic and reviewable in git, and every replica agrees. Re-run
this to refresh, or `--check` in CI to fail when a committed catalog drifts from the
live schema. (A leaf that no longer carries a searchable context is dropped — those
paths 400 at the Search API — so a regenerate also prunes stale attributes.)

Usage:
    python scripts/generate_search_attributes.py            # (re)write both catalogs
    python scripts/generate_search_attributes.py --check    # exit 1 if either is stale (no write)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import urllib.request

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "rcsb_mcp"

# One entry per catalog: the live schema to walk, the module to (re)write, the variable
# it exports, and the label for that module's docstring first line.
CATALOGS = [
    {
        "name": "structure",
        "schema_url": "https://search.rcsb.org/rcsbsearch/v2/metadata/schema",
        "out": _SRC / "search_attributes.py",
        "var": "SEARCH_ATTRIBUTES",
        "label": "structure** (text)",
    },
    {
        "name": "chemical",
        "schema_url": "https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema",
        "out": _SRC / "chemical_search_attributes.py",
        "var": "CHEMICAL_SEARCH_ATTRIBUTES",
        "label": "chemical** (text_chem)",
    },
]

# Total order over all operators. Every operator list is emitted sorted by it, so the
# catalog ordering is stable and diffs stay minimal across regenerations.
CANONICAL_OP_ORDER = [
    "equals", "greater", "in", "exact_match", "contains_phrase", "contains_words",
    "less", "greater_or_equal", "less_or_equal", "range", "exists",
]
_OP_RANK = {op: i for i, op in enumerate(CANONICAL_OP_ORDER)}

# Numeric/temporal comparison operators (used when context is "default-match").
_COMPARISON_OPS = ["equals", "greater", "less", "greater_or_equal", "less_or_equal", "range"]


def fetch_schema(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _type_of(leaf: dict) -> str:
    """Resolve the value type, treating date/date-time formats as 'date'."""
    if leaf.get("format") in ("date", "date-time"):
        return "date"
    return leaf.get("type")


def _operators_of(context: list[str], typ: str) -> list[str]:
    """Map an rcsb_search_context (+ type) to the supported operators, canonically ordered."""
    ops: set[str] = {"exists"}
    if "full-text" in context:
        ops |= {"contains_words", "contains_phrase"}
    if "exact-match" in context:
        ops |= {"exact_match", "in"}
    if "default-match" in context:
        # `in` (list match) works on every default-match attribute — including numeric/date,
        # which the published metadata schema omits it for but the live query API accepts
        # (adversarial review, 2026-07-26), so include it rather than under-report the schema.
        ops |= (set(_COMPARISON_OPS) | {"in"}) if typ in ("number", "integer", "date") else {"exact_match", "in"}
    return sorted(ops, key=lambda o: _OP_RANK[o])


def _description_of(leaf: dict) -> str | None:
    """Prefer the standard `description`, then the dictionary/brief rcsb_description."""
    by_ctx: dict[str | None, str] = {}
    rd = leaf.get("rcsb_description")
    if isinstance(rd, list):
        for item in rd:
            by_ctx[item.get("context")] = item.get("text")
    text = leaf.get("description") or by_ctx.get("dictionary") or by_ctx.get("brief")
    return " ".join(text.split()) if isinstance(text, str) else text


def _walk(node: dict, path: str = ""):
    """Yield (attribute_path, searchable_leaf) for every searchable attribute.

    A searchable leaf carries `rcsb_search_context` directly, or — for array
    attributes — on its `items`. The attribute path is the property path; the
    leaf supplying type/context/description may be the array's `items`.
    """
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if not isinstance(props, dict):
        return
    for key, val in props.items():
        if not isinstance(val, dict):
            continue
        attr = f"{path}.{key}" if path else key
        items = val.get("items") if isinstance(val.get("items"), dict) else None
        if "rcsb_search_context" in val:
            yield attr, val
        elif items is not None and "rcsb_search_context" in items:
            yield attr, items
        # Recurse into nested objects (directly and through array items).
        yield from _walk(val, attr)
        if items is not None:
            yield from _walk(items, attr)


def build_catalog(schema: dict) -> list[dict]:
    """Build a sorted, de-duplicated attribute catalog from a metadata schema."""
    out: dict[str, dict] = {}
    for attr, leaf in _walk(schema):
        if attr in out:  # keep first occurrence
            continue
        typ = _type_of(leaf)
        record = {
            "attribute": attr,
            "type": typ,
            "operators": _operators_of(leaf.get("rcsb_search_context", []), typ),
            "description": _description_of(leaf),
        }
        # Allowed values, where the schema constrains them (~15% of attributes). Emitted
        # LAST and only when present, so the 85% without one are byte-identical to before.
        # Kept whole and unsorted: this is the authoritative set the API matches against,
        # and a truncated or reordered list would be worse than none — the caller would
        # pick from what it was shown and never learn a value was omitted.
        if leaf.get("enum"):
            record["enum"] = list(leaf["enum"])
        out[attr] = record
    return [out[k] for k in sorted(out)]


def render_module(catalog: list[dict], spec: dict) -> str:
    body = json.dumps(catalog, indent=4, ensure_ascii=False)
    return (
        f'"""Searchable RCSB **{spec["label"]} attributes.\n\n'
        "Auto-generated by scripts/generate_search_attributes.py from\n"
        f'{spec["schema_url"]}\n'
        "Do not edit by hand; re-run the generator to refresh.\n"
        '"""\n\n'
        "from rcsb_mcp.attribute_types import SearchAttribute\n\n"
        f'{spec["var"]}: list[SearchAttribute] = {body}\n'
    )


def generate(spec: dict) -> tuple[list[dict], str]:
    """Fetch a schema and return (catalog, rendered module text) for one catalog spec."""
    catalog = build_catalog(fetch_schema(spec["schema_url"]))
    return catalog, render_module(catalog, spec)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if either committed catalog is stale (no write)")
    args = ap.parse_args()

    stale = False
    for spec in CATALOGS:
        catalog, module = generate(spec)
        name = spec["out"].name
        if args.check:
            current = spec["out"].read_text() if spec["out"].exists() else ""
            if current != module:
                print(f"STALE: {name} differs from the live {spec['name']} schema ({len(catalog)} attrs)")
                stale = True
            else:
                print(f"OK: {name} up to date ({len(catalog)} attrs)")
        else:
            spec["out"].write_text(module)
            print(f"wrote {name} ({len(catalog)} {spec['name']} attributes)")
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
