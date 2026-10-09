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

It also asks the live Search API, once per attribute, how many objects hold a value
(an `exists` count). That count drives two lists emitted next to each catalog:

    UNPOPULATED_*  in the schema but empty everywhere in the index, so every condition on
                   one matches nothing. Left OUT of the catalog (an agent never sees them)
                   and rejected by name in rcsb_query_attribute, so the silent zero becomes
                   an error instead.
    SPARSE_*       depositor-reported numbers that many entries reporting their category
                   leave empty (structure catalog only), each mapped to its category's most
                   filled attribute -- the "this entry reports the category" anchor. A value
                   filter on one drops those entries untested; rcsb_search_request counts the
                   ones that report the category and lack the value, and says how many.

Both depend on the archive, not only the schema, so `--check` also reports a catalog
stale when RCSB populates an attribute or fills one in.

Usage:
    python scripts/generate_search_attributes.py            # (re)write both catalogs
    python scripts/generate_search_attributes.py --check    # exit 1 if either is stale (no write)
"""
from __future__ import annotations

import argparse
import http.client
import json
import pathlib
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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
        # How an attribute's coverage is counted: entries, computed models included, so an
        # attribute only computed models fill is not mistaken for an empty one.
        "service": "text",
        "return_type": "entry",
        "content_types": ["experimental", "computational"],
        "sparse_var": "SPARSE_SEARCH_ATTRIBUTES",
    },
    {
        "name": "chemical",
        "schema_url": "https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema",
        "out": _SRC / "chemical_search_attributes.py",
        "var": "CHEMICAL_SEARCH_ATTRIBUTES",
        "label": "chemical** (text_chem)",
        "service": "text_chem",
        "return_type": "mol_definition",
        "content_types": None,
        # Chemical-component definitions come from the CCD, not from depositors, so there
        # is no depositor-reported field to flag.
        "sparse_var": None,
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


SEARCH_QUERY_URL = "https://search.rcsb.org/rcsbsearch/v2/query"

# An attribute is SPARSE when it is a depositor-reported number and fewer than this share
# of the entries reporting anything in its category (its first path segment) give it a
# value. Category-relative on purpose: pH is empty on 27% of X-ray entries, but relative to
# all entries it would look "empty" just because NMR and EM entries never have a crystal.
# Measured 2026-10-08, with the two exclusions below: 0.9 flags pH, Wilson B, Rmerge, mean
# B, mosaicity and ~31 EM fields.
SPARSE_FILL = 0.9
# rcsb_* is computed by RCSB and pdbx_vrpt* by the validation pipeline: a gap there means
# "does not apply", not "the depositor left it out". The threshold alone would flag them
# (ligand molecular weight is filled on 15% of entries -- the ones with a ligand -- and EC
# depth on 36%, the enzymes), so they are excluded by prefix.
_COMPUTED_PREFIXES = ("rcsb_", "pdbx_vrpt")
# A category nearly every experimental entry reports (exptl, struct) cannot tell "left out"
# from "does not apply": exptl.crystals_number is empty on every NMR and EM entry, which
# reads as 75% fill against exptl.method although ~94% of the crystal entries have it. Such
# categories are not judged at all.
UNIVERSAL_SHARE = 0.95
# Counts every experimental entry; the denominator for UNIVERSAL_SHARE.
_ENTRY_ID = "rcsb_entry_container_identifiers.entry_id"


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


def _walk(node: dict, path: str = "", nested_group: str | None = None):
    """Yield (attribute_path, searchable_leaf, nested_group) for every searchable attribute.

    A searchable leaf carries `rcsb_search_context` directly, or — for array
    attributes — on its `items`. The attribute path is the property path; the
    leaf supplying type/context/description may be the array's `items`.

    `nested_group` is the path of the nearest enclosing container the schema marks
    `rcsb_nested_indexing`, or None. That container is the coherence scope: conditions on
    attributes sharing a group must be grouped together AND isolated from everything else,
    or each is answered independently against a different record.

    OUTERMOST wins, which is why it is threaded down rather than recomputed at the leaf.
    `rcsb_polymer_entity_annotation` and its `.annotation_lineage` are BOTH nested, and
    `.type` + `.annotation_lineage.id` describe one annotation — keying the second to the
    deeper container would put them in different groups and split a pair that belongs
    together. Matches `queries._nested_record_of`, which takes the shallowest match.
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
        # A container is nested-indexed via its own flag or, for arrays, its `items`.
        here = nested_group
        if here is None and (val.get("rcsb_nested_indexing")
                             or (items is not None and items.get("rcsb_nested_indexing"))):
            here = attr
        if "rcsb_search_context" in val:
            yield attr, val, nested_group
        elif items is not None and "rcsb_search_context" in items:
            yield attr, items, nested_group
        # Recurse into nested objects (directly and through array items).
        yield from _walk(val, attr, here)
        if items is not None:
            yield from _walk(items, attr, here)


def build_catalog(schema: dict) -> list[dict]:
    """Build a sorted, de-duplicated attribute catalog from a metadata schema."""
    out: dict[str, dict] = {}
    for attr, leaf, nested_group in _walk(schema):
        if attr in out:  # keep first occurrence
            continue
        typ = _type_of(leaf)
        record = {
            "attribute": attr,
            "type": typ,
            "operators": _operators_of(leaf.get("rcsb_search_context", []), typ),
            "description": _description_of(leaf),
        }
        # The coherence scope, on the ~19% of attributes that have one. Emitted as the
        # container PATH rather than a boolean because the path is the actionable part —
        # "group this with everything else carrying the same value" — and it is not
        # derivable from the attribute: 22 structure attributes have a group that is not
        # their first path segment (drugbank_info.drug_products.approved groups under
        # drugbank_info.drug_products, rcsb_polymer_entity.rcsb_ec_lineage.id under
        # rcsb_polymer_entity.rcsb_ec_lineage). A boolean would leave the caller to guess,
        # and the obvious guess is wrong for exactly those.
        if nested_group:
            record["nested_group"] = nested_group
        # Allowed values, where the schema constrains them (~16% of attributes). Emitted
        # LAST and only when present, so the ~84% without one are byte-identical to before.
        # Kept whole and unsorted: this is the authoritative set the API matches against,
        # and a truncated or reordered list would be worse than none — the caller would
        # pick from what it was shown and never learn a value was omitted.
        if leaf.get("enum"):
            record["enum"] = list(leaf["enum"])
        out[attr] = record
    return [out[k] for k in sorted(out)]


def _exists_count(spec: dict, attribute: str, content_types: list[str] | None = None) -> int:
    """How many objects of the catalog's kind hold a value for `attribute` (live)."""
    options: dict = {"return_counts": True}
    if content_types or spec["content_types"]:
        options["results_content_type"] = content_types or spec["content_types"]
    body = json.dumps({
        "query": {"type": "terminal", "service": spec["service"],
                  "parameters": {"attribute": attribute, "operator": "exists"}},
        "return_type": spec["return_type"],
        "request_options": options,
    }).encode()
    attempts = 5
    for attempt in range(attempts):
        req = urllib.request.Request(SEARCH_QUERY_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                if resp.status == 204:  # the API's "nothing matched"
                    return 0
                return int(json.loads(resp.read().decode())["total_count"])
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"exists probe for {attribute!r} failed: HTTP {exc.code}") from None
        # A dropped connection surfaces from getresponse()/read() unwrapped by urllib.
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
            pass
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)
    # Fatal rather than "assume populated": a catalog generated from partial counts would be
    # committed as if it were complete.
    raise RuntimeError(f"exists probe for {attribute!r} kept failing; nothing was written")


def probe_counts(catalog: list[dict], spec: dict) -> dict[str, int]:
    """The live `exists` count of every attribute in a catalog (seconds, at 8 in flight)."""
    attrs = [a["attribute"] for a in catalog]
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(attrs, pool.map(lambda a: _exists_count(spec, a), attrs)))


def unpopulated(counts: dict[str, int]) -> list[str]:
    """Attributes no object holds a value for."""
    return sorted(a for a, n in counts.items() if n == 0)


def sparse(catalog: list[dict], counts: dict[str, int], entries: int) -> dict[str, str]:
    """Depositor-reported numbers left empty by many entries that report their category.

    Maps each to its category's ANCHOR: the category's most filled attribute, i.e. "this
    entry reports the category". The runtime gap count requires it, so an entry the
    attribute cannot apply to (crystal pH on a cryo-EM entry) is not counted as a gap.
    `entries` is the number of experimental entries (see UNIVERSAL_SHARE).
    """
    anchor: dict[str, str] = {}
    for attr in sorted(counts):
        cat = attr.split(".")[0]
        if counts[attr] > counts.get(anchor.get(cat, ""), -1):
            anchor[cat] = attr
    flagged = {}
    for record in catalog:
        attr = record["attribute"]
        if record["type"] not in ("number", "integer") or attr.startswith(_COMPUTED_PREFIXES):
            continue
        top = counts[anchor[attr.split(".")[0]]]
        if top >= UNIVERSAL_SHARE * entries:
            continue
        if 0 < counts[attr] < SPARSE_FILL * top:
            flagged[attr] = anchor[attr.split(".")[0]]
    return dict(sorted(flagged.items()))


def render_module(catalog: list[dict], spec: dict, empty: list[str], thin: dict[str, str]) -> str:
    body = json.dumps(catalog, indent=4, ensure_ascii=False)
    text = (
        f'"""Searchable RCSB **{spec["label"]} attributes.\n\n'
        "Auto-generated by scripts/generate_search_attributes.py from\n"
        f'{spec["schema_url"]}\n'
        "and the live Search API's per-attribute counts.\n"
        "Do not edit by hand; re-run the generator to refresh.\n"
        '"""\n\n'
        "from rcsb_mcp.attribute_types import SearchAttribute\n\n"
        f'{spec["var"]}: list[SearchAttribute] = {body}\n\n'
        "# In the schema but holding no value anywhere in the search index (a live `exists`\n"
        "# count of 0), so every condition on one matches nothing. Left out of the catalog\n"
        "# above; rcsb_query_attribute rejects them by name.\n"
        f'UNPOPULATED_{spec["var"]}: list[str] = {json.dumps(empty, indent=4)}\n'
    )
    if spec["sparse_var"]:
        text += (
            "\n# Depositor-reported numbers that more than 10% of the entries reporting their\n"
            "# category leave empty, each mapped to its category's most filled attribute (the\n"
            "# entry reports the category). A value filter on one drops those entries untested;\n"
            "# rcsb_search_request counts the ones holding the anchor but not the value.\n"
            f'{spec["sparse_var"]}: dict[str, str] = {json.dumps(thin, indent=4)}\n'
        )
    return text


def generate(spec: dict) -> tuple[list[dict], str, list[str], dict[str, str]]:
    """Fetch a schema, count every attribute live, and render one catalog module.

    Returns (catalog, module text, unpopulated, sparse); the catalog excludes unpopulated.
    """
    full = build_catalog(fetch_schema(spec["schema_url"]))
    counts = probe_counts(full, spec)
    empty = unpopulated(counts)
    catalog = [a for a in full if counts[a["attribute"]] > 0]
    thin: dict[str, str] = {}
    if spec["sparse_var"]:
        thin = sparse(catalog, counts, _exists_count(spec, _ENTRY_ID, ["experimental"]))
    return catalog, render_module(catalog, spec, empty, thin), empty, thin


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if either committed catalog is stale (no write)")
    args = ap.parse_args()

    stale = False
    for spec in CATALOGS:
        catalog, module, empty, thin = generate(spec)
        name = spec["out"].name
        sizes = f"{len(catalog)} attrs, {len(empty)} unpopulated, {len(thin)} sparse"
        if args.check:
            current = spec["out"].read_text() if spec["out"].exists() else ""
            if current != module:
                print(f"STALE: {name} differs from the live {spec['name']} schema/counts ({sizes})")
                stale = True
            else:
                print(f"OK: {name} up to date ({sizes})")
        else:
            spec["out"].write_text(module)
            print(f"wrote {name} ({spec['name']}: {sizes})")
    return 1 if (args.check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
