#!/usr/bin/env python3
"""Generate the chemical search-attribute catalog from the RCSB metadata schema.

The RCSB Search API publishes its searchable attributes as JSON-Schema documents:

    structure: https://search.rcsb.org/rcsbsearch/v2/metadata/schema
    chemical:  https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema

Each searchable leaf carries an ``rcsb_search_context`` array; the supported
query operators are derived from that context plus the value type. This script
walks the *chemical* schema and emits ``src/rcsb_mcp/chemical_search_attributes.py``
with the same ``{attribute, type, operators, description}`` shape as the curated
``search_attributes.py`` (the structure catalog).

The context->operators mapping is validated by ``--verify-structure``, which
regenerates the structure catalog from the live schema and asserts it reproduces
the committed ``SEARCH_ATTRIBUTES`` exactly on attribute path, type, and operators
(descriptions are reported but not asserted: the committed file predates a few
upstream wording/whitespace tweaks). This documents the provenance of the
generated chemical file without overwriting the curated structure file.

Usage:
    python scripts/generate_chemical_attributes.py                 # write chemical catalog
    python scripts/generate_chemical_attributes.py --verify-structure
    python scripts/generate_chemical_attributes.py --check         # fail if catalog is stale
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.request

STRUCTURE_SCHEMA_URL = "https://search.rcsb.org/rcsbsearch/v2/metadata/schema"
CHEMICAL_SCHEMA_URL = "https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema"

OUT_PATH = pathlib.Path(__file__).resolve().parents[1] / "src" / "rcsb_mcp" / "chemical_search_attributes.py"

# Total order over all operators, derived from (and verified against) the curated
# structure catalog: every operator list there is a subsequence of this order, so
# sorting any operator set by it reproduces the catalog's ordering exactly.
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
        ops |= set(_COMPARISON_OPS) if typ in ("number", "integer", "date") else {"exact_match", "in"}
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
        out[attr] = {
            "attribute": attr,
            "type": typ,
            "operators": _operators_of(leaf.get("rcsb_search_context", []), typ),
            "description": _description_of(leaf),
        }
    return [out[k] for k in sorted(out)]


def render_module(catalog: list[dict]) -> str:
    body = json.dumps(catalog, indent=4, ensure_ascii=False)
    return (
        '"""Searchable RCSB **chemical** (text_chem) attributes.\n\n'
        "Auto-generated by scripts/generate_chemical_attributes.py from\n"
        f"{CHEMICAL_SCHEMA_URL}\n"
        "Do not edit by hand; re-run the generator to refresh.\n"
        '"""\n\n'
        "from rcsb_mcp.attribute_types import SearchAttribute\n\n"
        f"CHEMICAL_SEARCH_ATTRIBUTES: list[SearchAttribute] = {body}\n"
    )


def verify_structure() -> int:
    """Regenerate the structure catalog and diff against the committed SEARCH_ATTRIBUTES."""
    sys.path.insert(0, str(OUT_PATH.parents[1]))
    from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES as committed

    derived = {a["attribute"]: a for a in build_catalog(fetch_schema(STRUCTURE_SCHEMA_URL))}
    existing = {a["attribute"]: a for a in committed}

    missing = sorted(set(existing) - set(derived))
    extra = sorted(set(derived) - set(existing))
    type_mismatch = [a for a in existing if a in derived and existing[a]["type"] != derived[a]["type"]]
    op_mismatch = [a for a in existing if a in derived and existing[a]["operators"] != derived[a]["operators"]]
    desc_match = sum(
        1 for a in existing if a in derived and existing[a].get("description") == derived[a].get("description")
    )

    print(f"committed={len(existing)} derived={len(derived)}")
    print(f"missing={len(missing)} extra={len(extra)} type_mismatch={len(type_mismatch)} op_mismatch={len(op_mismatch)}")
    print(f"description parity (informational): {desc_match}/{len(existing)}")
    ok = not (missing or extra or type_mismatch or op_mismatch)
    if not ok:
        for label, items in (("missing", missing), ("extra", extra),
                             ("type_mismatch", type_mismatch), ("op_mismatch", op_mismatch)):
            if items:
                print(f"  {label}: {items[:10]}")
    print("VERIFY:", "PASS — mapping reproduces the structure catalog" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify-structure", action="store_true",
                    help="prove the mapping by reproducing the committed structure catalog (no write)")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed chemical catalog is stale (no write)")
    args = ap.parse_args()

    if args.verify_structure:
        return verify_structure()

    catalog = build_catalog(fetch_schema(CHEMICAL_SCHEMA_URL))
    module = render_module(catalog)

    if args.check:
        current = OUT_PATH.read_text() if OUT_PATH.exists() else ""
        if current != module:
            print(f"STALE: {OUT_PATH} differs from freshly generated catalog ({len(catalog)} attrs)")
            return 1
        print(f"OK: {OUT_PATH} is up to date ({len(catalog)} attrs)")
        return 0

    OUT_PATH.write_text(module)
    print(f"wrote {OUT_PATH} ({len(catalog)} chemical attributes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
