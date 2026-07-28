"""Fetch + parse the RCSB Search API's structure and chemical metadata schemas,
to find their **nested attributes** — attribute pairs that must be queried together
inside a single `nested` search-query group (the Search API rejects one of the pair
used standalone outside that context) — and validate agent-supplied attribute lists
against them.

These schemas change rarely but DO change, so this deliberately does NOT vendor a
generated catalog into the package (unlike search_attributes.py / chemical_search_
attributes.py): everything here is refreshed from the live metadata endpoints, at
most once per day, via an on-disk cache gated by file mtime.

* :func:`download_schemas` — disk-cached fetch of both raw schemas.
* :func:`find_nested_attribute_pairs` / :func:`build_nested_attribute_pairs` — walk a
  schema's `rcsb_nested_indexing_context` annotations and collect the
  (attribute_path, category_path) pairs, one list per schema. This mirrors
  `SearchSchema._find_nested_indexing` in py-rcsb-api, minus the `{True}` placeholder
  value the upstream dict maps each pair to (a leftover of that pair being carried in
  a dict rather than a plain collection — not meaningful here).
* :func:`load_nested_attribute_pairs` — the day-cached pairs themselves (derived from
  the schemas above), also persisted to their own file so the current pairs are
  inspectable without running Python.
* :func:`validate_nested_attributes` — the check `rcsb_search_by_attribute` calls: does
  this flat attribute list contain a nested attribute with none of its partners present.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from rcsb_mcp.client import TIMEOUT, USER_AGENT

_log = logging.getLogger(__name__)

STRUCTURE_SCHEMA_URL = "https://search.rcsb.org/rcsbsearch/v2/metadata/schema"
CHEMICAL_SCHEMA_URL = "https://search.rcsb.org/rcsbsearch/v2/metadata/chemical/schema"

# Override with RCSB_MCP_SCHEMA_CACHE_DIR to relocate the cache (e.g. a persistent
# volume in a container). Defaults next to the OS temp dir so a bare checkout works
# with no setup.
_CACHE_DIR = Path(
    os.environ.get("RCSB_MCP_SCHEMA_CACHE_DIR")
    or Path(tempfile.gettempdir()) / "rcsb-mcp" / "schema-cache"
)
STRUCTURE_SCHEMA_CACHE_FILE = _CACHE_DIR / "structure_schema.json"
CHEMICAL_SCHEMA_CACHE_FILE = _CACHE_DIR / "chemical_schema.json"
# Derived-pairs cache: re-computed from the schemas above every time they're loaded, and
# written here mainly so the current nested-attribute pairs are inspectable as plain text.
STRUCTURE_NESTED_PAIRS_FILE = _CACHE_DIR / "structure_nested_pairs.txt"
CHEMICAL_NESTED_PAIRS_FILE = _CACHE_DIR / "chemical_nested_pairs.txt"

ONE_DAY_SECONDS = 24 * 60 * 60


def _is_stale(path: Path, max_age_seconds: float) -> bool:
    """True if `path` is missing or was last written more than `max_age_seconds` ago."""
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return True
    return (time.time() - mtime) > max_age_seconds


def _fetch_schema(url: str) -> dict[str, Any]:
    resp = httpx.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _load_cached_schema(url: str, cache_file: Path, max_age_seconds: float) -> dict[str, Any]:
    """Return the schema at `cache_file`, refetching from `url` if missing/stale.

    A failed refetch (RCSB unreachable, timeout, ...) falls back to the existing cache
    file even though it's stale — this runs on the live `rcsb_search_by_attribute` path,
    so a transient network hiccup fetching metadata must not be able to break an
    unrelated search. Only raises if there's no cache to fall back to.
    """
    if not _is_stale(cache_file, max_age_seconds):
        return json.loads(cache_file.read_text(encoding="utf-8"))
    try:
        schema = _fetch_schema(url)
    except Exception:
        if cache_file.exists():
            _log.warning("Refetching %s failed; using stale cached copy.", url, exc_info=True)
            return json.loads(cache_file.read_text(encoding="utf-8"))
        raise
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(schema), encoding="utf-8")
    return schema


def download_schemas(max_age_seconds: float = ONE_DAY_SECONDS) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (structure_schema, chemical_schema), each fetched at most once per `max_age_seconds`.

    Every call reads the on-disk cache first; a schema is only re-fetched from the
    live Search API metadata endpoint once its cache file's mtime is older than
    `max_age_seconds` (default: one day), and the fetched copy is written back to
    reset that mtime.
    """
    structure_schema = _load_cached_schema(STRUCTURE_SCHEMA_URL, STRUCTURE_SCHEMA_CACHE_FILE, max_age_seconds)
    chemical_schema = _load_cached_schema(CHEMICAL_SCHEMA_URL, CHEMICAL_SCHEMA_CACHE_FILE, max_age_seconds)
    return structure_schema, chemical_schema


def _pairs_from_context_entry(entry: Any) -> list[tuple[str, str]] | None:
    """Return the (attribute_path, category_path) pairs from one `rcsb_nested_indexing_context`
    entry, or None if the entry doesn't have the full expected shape.

    Expected shape:
        {"category_path": "...", "context_attributes": [{"context_value": ..., "attributes": [{"path": "..."}, ...]}, ...]}
    """
    if not isinstance(entry, dict):
        return None
    category_path = entry.get("category_path")
    context_attrs = entry.get("context_attributes")
    if not isinstance(category_path, str) or not category_path or not isinstance(context_attrs, list):
        return None
    category_path = category_path.replace("properties.", "")

    pairs: list[tuple[str, str]] = []
    for context_attr in context_attrs:
        if not isinstance(context_attr, dict) or "attributes" not in context_attr:
            return None
        attributes = context_attr["attributes"]
        if not isinstance(attributes, list):
            return None
        for attr in attributes:
            if not isinstance(attr, dict):
                return None
            attribute_path = attr.get("path")
            if not isinstance(attribute_path, str) or not attribute_path:
                return None
            pairs.append((attribute_path.replace("properties.", ""), category_path))
    return pairs


def find_nested_attribute_pairs(schema: dict[str, Any]) -> list[tuple[str, str]]:
    """Walk one metadata schema and collect its nested-attribute pairs.

    Each leaf carrying an `rcsb_nested_indexing_context` array pairs a category_path
    with one or more attributes nested under it; every such (attribute_path,
    category_path) pair is returned. A malformed context entry (missing any of the
    required keys) is skipped rather than raising, since the published metadata
    schema is outside our control.

    Returns a sorted, de-duplicated list of (attribute_path, category_path) tuples.
    """
    found: dict[tuple[str, str], None] = {}
    queue: list[tuple[Any, str]] = [(schema, "")]

    while queue:
        node, path = queue.pop(0)
        if not isinstance(node, dict):
            continue

        context = node.get("rcsb_nested_indexing_context")
        if isinstance(context, list):
            for entry in context:
                pairs = _pairs_from_context_entry(entry)
                if pairs is None:
                    continue
                for pair in pairs:
                    found.setdefault(pair, None)

        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(value, dict):
                queue.append((value, child_path))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        queue.append((item, child_path))

    return sorted(found)


def build_nested_attribute_pairs(
    structure_schema: dict[str, Any], chemical_schema: dict[str, Any]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (structure_pairs, chemical_pairs): the nested-attribute pairs found in
    each schema, kept separate (unlike py-rcsb-api's SEARCH_SCHEMA.nested_attribute_schema,
    which merges both schemas into one dict)."""
    return find_nested_attribute_pairs(structure_schema), find_nested_attribute_pairs(chemical_schema)


def _write_pairs_file(pairs: list[tuple[str, str]], path: Path) -> None:
    """Persist a pair list as JSON (a list of [attribute_path, category_path] pairs) — plain
    text, so the current nested-attribute pairs can be inspected without running Python."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([list(pair) for pair in pairs], indent=2), encoding="utf-8")


def load_nested_attribute_pairs(
    max_age_seconds: float = ONE_DAY_SECONDS,
) -> dict[str, list[tuple[str, str]]]:
    """Return {"structure": [...], "chemical": [...]} nested-attribute pairs, re-derived
    from the live schemas at most once per `max_age_seconds` (default: one day).

    Delegates the actual network/cache gating to `download_schemas`; this just re-parses
    whichever copy (fresh or cached) comes back and writes each schema's pairs to
    STRUCTURE_NESTED_PAIRS_FILE / CHEMICAL_NESTED_PAIRS_FILE.
    """
    structure_schema, chemical_schema = download_schemas(max_age_seconds)
    structure_pairs, chemical_pairs = build_nested_attribute_pairs(structure_schema, chemical_schema)
    _write_pairs_file(structure_pairs, STRUCTURE_NESTED_PAIRS_FILE)
    _write_pairs_file(chemical_pairs, CHEMICAL_NESTED_PAIRS_FILE)
    return {"structure": structure_pairs, "chemical": chemical_pairs}


def partner_map(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """{attribute: sorted [valid partner attributes]} from a flat pair list.

    An attribute on EITHER side of a pair needs one of its partners present in the
    same query; a category/type attribute (e.g. `...type`) commonly partners several
    different dependent attributes, so this is one-to-many, not one-to-one. Public
    (not just an internal helper for find_orphan_attributes below) because callers
    that also need to check STRUCTURAL grouping — not just presence — need direct
    access to "what are this attribute's valid partners" (see search._validate_
    nested_attribute_grouping).
    """
    partners: dict[str, set[str]] = {}
    for a, b in pairs:
        partners.setdefault(a, set()).add(b)
        partners.setdefault(b, set()).add(a)
    return {attr: sorted(partner_set) for attr, partner_set in partners.items()}


def find_orphan_attributes(
    attributes: list[str], pairs: list[tuple[str, str]]
) -> dict[str, list[str]]:
    """Return {orphan_attribute: [its valid partners]} for every entry in `attributes`
    that is nested (per `pairs`) but has none of its partner attributes also present
    in `attributes`. Empty if there are no orphans."""
    partners_by_attr = partner_map(pairs)
    present = set(attributes)
    orphans: dict[str, list[str]] = {}
    for attr in attributes:
        partners = partners_by_attr.get(attr)
        if partners and not present.intersection(partners):
            orphans[attr] = partners
    return orphans


def validate_nested_attributes(
    attributes: list[str], schema: str, max_age_seconds: float = ONE_DAY_SECONDS
) -> None:
    """Raise ValueError if `attributes` contains an orphan nested attribute for `schema`
    ("structure" or "chemical") — one whose required partner attribute is missing from
    the same list.

    Pulls the current pairs via `load_nested_attribute_pairs` (day-cached). If that fails
    outright (no network AND no prior cache — see `_load_cached_schema`), this validation
    is skipped rather than raised: it's a client-side guard against a malformed query, not
    a hard requirement, so it must not be able to block an otherwise-valid search.
    """
    try:
        pairs = load_nested_attribute_pairs(max_age_seconds).get(schema, [])
    except Exception:
        _log.warning("Could not load nested-attribute pairs; skipping this check.", exc_info=True)
        return
    orphans = find_orphan_attributes(attributes, pairs)
    if not orphans:
        return
    attr, partners = next(iter(orphans.items()))
    msg = (
        f"'{attr}' is a nested attribute and cannot be queried on its own — it must be "
        f"paired with one of its partner attributes in the same `attributes` list: "
        f"{', '.join(partners)}."
    )
    _log.warning(msg)
    raise ValueError(msg)
