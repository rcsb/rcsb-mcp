"""Network-free tests for rcsb_mcp.nested_attributes: the schema-cache staleness check
and the rcsb_nested_indexing_context parser, exercised against synthetic schemas rather
than the live Search API metadata endpoints.
"""
import os
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import nested_attributes as na  # noqa: E402

# --- synthetic schema shapes (what find_nested_attribute_pairs expects) --------------- #

_STRUCT_SCHEMA = {
    "properties": {
        "rcsb_binding_affinity": {
            "properties": {
                "value": {
                    "rcsb_nested_indexing_context": [
                        {
                            "category_path": "properties.rcsb_binding_affinity.type",
                            "context_attributes": [
                                {
                                    "context_value": "some-value",
                                    "attributes": [{"path": "properties.rcsb_binding_affinity.value"}],
                                }
                            ],
                        }
                    ]
                },
                "type": {"type": "string"},
            }
        }
    }
}

_MALFORMED_SCHEMA = {
    "properties": {
        "rcsb_broken": {
            "rcsb_nested_indexing_context": [
                {"category_path": "properties.rcsb_broken.type"},  # missing context_attributes
            ]
        }
    }
}


def test_find_nested_attribute_pairs_synthetic():
    pairs = na.find_nested_attribute_pairs(_STRUCT_SCHEMA)
    assert pairs == [("rcsb_binding_affinity.value", "rcsb_binding_affinity.type")]
    print("ok: find_nested_attribute_pairs synthetic")


def test_find_nested_attribute_pairs_dedupes_and_sorts():
    schema = {
        "properties": {
            "a": {
                "rcsb_nested_indexing_context": [
                    {
                        "category_path": "properties.z_cat",
                        "context_attributes": [
                            {"context_value": "v", "attributes": [{"path": "properties.a"}]}
                        ],
                    }
                ]
            },
            "b": {
                "rcsb_nested_indexing_context": [
                    {
                        "category_path": "properties.z_cat",
                        "context_attributes": [
                            {"context_value": "v", "attributes": [{"path": "properties.a"}]}
                        ],
                    }
                ]
            },
        }
    }
    # Same (attribute, category) pair reachable via two nodes -> de-duplicated; result sorted.
    pairs = na.find_nested_attribute_pairs(schema)
    assert pairs == [("a", "z_cat")]
    print("ok: find_nested_attribute_pairs dedupes and sorts")


def test_find_nested_attribute_pairs_skips_malformed_context():
    assert na.find_nested_attribute_pairs(_MALFORMED_SCHEMA) == []
    print("ok: find_nested_attribute_pairs skips malformed context")


def test_build_nested_attribute_pairs_keeps_schemas_separate():
    struct_pairs, chem_pairs = na.build_nested_attribute_pairs(_STRUCT_SCHEMA, _MALFORMED_SCHEMA)
    assert struct_pairs == [("rcsb_binding_affinity.value", "rcsb_binding_affinity.type")]
    assert chem_pairs == []
    print("ok: build_nested_attribute_pairs keeps schemas separate")


# --- download_schemas caching (mtime-gated, no network) ------------------------------- #

def test_download_schemas_caches_within_max_age(tmp_path, monkeypatch):
    struct_file = tmp_path / "structure_schema.json"
    chem_file = tmp_path / "chemical_schema.json"
    monkeypatch.setattr(na, "STRUCTURE_SCHEMA_CACHE_FILE", struct_file)
    monkeypatch.setattr(na, "CHEMICAL_SCHEMA_CACHE_FILE", chem_file)

    calls = []

    def fake_fetch(url):
        calls.append(url)
        return {"schema": url}

    monkeypatch.setattr(na, "_fetch_schema", fake_fetch)

    first = na.download_schemas(max_age_seconds=na.ONE_DAY_SECONDS)
    assert len(calls) == 2, "cold cache: both schemas fetched once"
    assert first == ({"schema": na.STRUCTURE_SCHEMA_URL}, {"schema": na.CHEMICAL_SCHEMA_URL})

    second = na.download_schemas(max_age_seconds=na.ONE_DAY_SECONDS)
    assert len(calls) == 2, "warm cache within max_age: no re-fetch"
    assert second == first
    print("ok: download_schemas caches within max_age")


def test_download_schemas_refetches_when_stale(tmp_path, monkeypatch):
    struct_file = tmp_path / "structure_schema.json"
    chem_file = tmp_path / "chemical_schema.json"
    monkeypatch.setattr(na, "STRUCTURE_SCHEMA_CACHE_FILE", struct_file)
    monkeypatch.setattr(na, "CHEMICAL_SCHEMA_CACHE_FILE", chem_file)

    calls = []
    monkeypatch.setattr(na, "_fetch_schema", lambda url: calls.append(url) or {"schema": url})

    na.download_schemas(max_age_seconds=na.ONE_DAY_SECONDS)
    assert len(calls) == 2

    # Back-date both cache files past max_age -> next call must re-fetch both.
    stale_time = time.time() - na.ONE_DAY_SECONDS - 60
    os.utime(struct_file, (stale_time, stale_time))
    os.utime(chem_file, (stale_time, stale_time))

    na.download_schemas(max_age_seconds=na.ONE_DAY_SECONDS)
    assert len(calls) == 4, "stale cache: both schemas re-fetched"
    print("ok: download_schemas refetches when stale")


def test_load_cached_schema_falls_back_to_stale_on_fetch_failure(tmp_path, monkeypatch):
    cache_file = tmp_path / "schema.json"
    cache_file.write_text('{"schema": "old"}', encoding="utf-8")
    stale_time = time.time() - na.ONE_DAY_SECONDS - 60
    os.utime(cache_file, (stale_time, stale_time))

    def boom(url):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(na, "_fetch_schema", boom)
    # Refetch fails, but a (stale) cache exists -> must return it rather than raising, since
    # this runs on the live search path and a metadata-endpoint hiccup can't be allowed to
    # break an unrelated search.
    result = na._load_cached_schema("http://example/schema", cache_file, na.ONE_DAY_SECONDS)
    assert result == {"schema": "old"}
    print("ok: _load_cached_schema falls back to stale cache on fetch failure")


def test_load_cached_schema_raises_when_no_cache_and_fetch_fails(tmp_path, monkeypatch):
    cache_file = tmp_path / "schema.json"  # never written -> no fallback available

    def boom(url):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(na, "_fetch_schema", boom)
    try:
        na._load_cached_schema("http://example/schema", cache_file, na.ONE_DAY_SECONDS)
    except RuntimeError:
        pass
    else:
        raise AssertionError("no cache to fall back to -> the fetch failure must propagate")
    print("ok: _load_cached_schema raises when there's no cache to fall back to")


# --- load_nested_attribute_pairs (derives + persists pairs from the schemas) ---------- #

def test_load_nested_attribute_pairs_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(na, "STRUCTURE_NESTED_PAIRS_FILE", tmp_path / "structure_nested_pairs.txt")
    monkeypatch.setattr(na, "CHEMICAL_NESTED_PAIRS_FILE", tmp_path / "chemical_nested_pairs.txt")
    monkeypatch.setattr(na, "download_schemas", lambda max_age_seconds: (_STRUCT_SCHEMA, _MALFORMED_SCHEMA))

    result = na.load_nested_attribute_pairs(max_age_seconds=na.ONE_DAY_SECONDS)
    assert result == {
        "structure": [("rcsb_binding_affinity.value", "rcsb_binding_affinity.type")],
        "chemical": [],
    }
    import json as _json
    on_disk = _json.loads(na.STRUCTURE_NESTED_PAIRS_FILE.read_text(encoding="utf-8"))
    assert on_disk == [["rcsb_binding_affinity.value", "rcsb_binding_affinity.type"]]
    print("ok: load_nested_attribute_pairs writes files")


# --- orphan detection + the public validation entry point ---------------------------- #

_PAIRS = [("rcsb_binding_affinity.value", "rcsb_binding_affinity.type")]


def test_find_orphan_attributes_flags_lone_dependent():
    orphans = na.find_orphan_attributes(["rcsb_binding_affinity.value"], _PAIRS)
    assert orphans == {"rcsb_binding_affinity.value": ["rcsb_binding_affinity.type"]}
    print("ok: find_orphan_attributes flags lone dependent")


def test_find_orphan_attributes_flags_lone_category_too():
    orphans = na.find_orphan_attributes(["rcsb_binding_affinity.type"], _PAIRS)
    assert orphans == {"rcsb_binding_affinity.type": ["rcsb_binding_affinity.value"]}
    print("ok: find_orphan_attributes flags lone category")


def test_find_orphan_attributes_empty_when_paired_or_unrelated():
    assert na.find_orphan_attributes(
        ["rcsb_binding_affinity.value", "rcsb_binding_affinity.type"], _PAIRS
    ) == {}
    assert na.find_orphan_attributes(["some.other.attribute"], _PAIRS) == {}
    print("ok: find_orphan_attributes empty when paired or unrelated")


def test_validate_nested_attributes_raises_for_an_orphan(monkeypatch):
    monkeypatch.setattr(na, "load_nested_attribute_pairs", lambda *a, **k: {"structure": _PAIRS, "chemical": []})
    try:
        na.validate_nested_attributes(["rcsb_binding_affinity.value"], "structure")
    except ValueError as e:
        assert "nested attribute" in str(e)
    else:
        raise AssertionError("an orphan nested attribute must raise ValueError")
    print("ok: validate_nested_attributes raises for an orphan")


def test_validate_nested_attributes_passes_when_paired(monkeypatch):
    monkeypatch.setattr(na, "load_nested_attribute_pairs", lambda *a, **k: {"structure": _PAIRS, "chemical": []})
    na.validate_nested_attributes(
        ["rcsb_binding_affinity.value", "rcsb_binding_affinity.type"], "structure"
    )  # both present -> no raise
    print("ok: validate_nested_attributes passes when paired")


def test_validate_nested_attributes_skips_when_pairs_cannot_be_loaded(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(na, "load_nested_attribute_pairs", boom)
    # Must not propagate: this is a client-side guard, not a hard requirement, and must
    # never be able to break an otherwise-valid search over a metadata-endpoint hiccup.
    na.validate_nested_attributes(["rcsb_binding_affinity.value"], "structure")
    print("ok: validate_nested_attributes skips when pairs cannot be loaded")


if __name__ == "__main__":
    import tempfile

    test_find_nested_attribute_pairs_synthetic()
    test_find_nested_attribute_pairs_dedupes_and_sorts()
    test_find_nested_attribute_pairs_skips_malformed_context()
    test_build_nested_attribute_pairs_keeps_schemas_separate()
    test_find_orphan_attributes_flags_lone_dependent()
    test_find_orphan_attributes_flags_lone_category_too()
    test_find_orphan_attributes_empty_when_paired_or_unrelated()

    class _MonkeyPatch:
        """Minimal setattr-with-restore shim so this file's tests also run as a plain script
        (no pytest), matching the tests/test_server.py convention."""

        def __init__(self):
            self._restore = []

        def setattr(self, obj, name, value):
            self._restore.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, value in reversed(self._restore):
                setattr(obj, name, value)

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as d:
        test_download_schemas_caches_within_max_age(pathlib.Path(d), mp)
    mp.undo()

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as d:
        test_download_schemas_refetches_when_stale(pathlib.Path(d), mp)
    mp.undo()

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as d:
        test_load_cached_schema_falls_back_to_stale_on_fetch_failure(pathlib.Path(d), mp)
    mp.undo()

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as d:
        test_load_cached_schema_raises_when_no_cache_and_fetch_fails(pathlib.Path(d), mp)
    mp.undo()

    mp = _MonkeyPatch()
    with tempfile.TemporaryDirectory() as d:
        test_load_nested_attribute_pairs_writes_files(pathlib.Path(d), mp)
    mp.undo()

    mp = _MonkeyPatch()
    test_validate_nested_attributes_raises_for_an_orphan(mp)
    mp.undo()

    mp = _MonkeyPatch()
    test_validate_nested_attributes_passes_when_paired(mp)
    mp.undo()

    mp = _MonkeyPatch()
    test_validate_nested_attributes_skips_when_pairs_cannot_be_loaded(mp)
    mp.undo()

    print("\nAll nested_attributes tests passed.")
