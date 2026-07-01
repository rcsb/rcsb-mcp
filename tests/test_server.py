"""Network-free tests for server-side logic that isn't a pure query builder.

Covers _flatten_object_fields (the recursive GraphQL-schema flatten behind
rcsb_list_data_fields) by injecting a synthetic, deliberately CYCLIC schema in place
of the live introspection calls — so depth-capping, cycle-guarding, keyword filtering,
and the result cap are all exercised without touching the network.
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import server  # noqa: E402


# --- synthetic introspection shapes (what _field_descriptor/_unwrap_type expect) ---------- #
def _scalar(name, desc=""):
    return {"name": name, "description": desc, "type": {"kind": "SCALAR", "name": "String", "ofType": None}}


def _obj(name, type_name, desc=""):
    return {"name": name, "description": desc, "type": {"kind": "OBJECT", "name": type_name, "ofType": None}}


def _list_obj(name, type_name, desc=""):
    return {"name": name, "description": desc,
            "type": {"kind": "LIST", "name": None,
                     "ofType": {"kind": "OBJECT", "name": type_name, "ofType": None}}}


# CoreEntry -> polymer_entities -> entry is a back-reference: the classic schema cycle.
_SCHEMA = {
    "CoreEntry": [
        _scalar("rcsb_id"),
        _obj("struct", "Struct", "structure info"),
        _obj("pubmed", "CorePubmed"),
        _list_obj("polymer_entities", "CorePolymerEntity"),
    ],
    "Struct": [_scalar("title", "the structure title")],
    "CorePubmed": [_scalar("rcsb_pubmed_abstract_text", "the paper abstract")],
    "CorePolymerEntity": [
        _obj("rcsb_polymer_entity", "RcsbPolymerEntity"),
        _obj("entry", "CoreEntry"),  # cycle back to the root type
    ],
    "RcsbPolymerEntity": [_scalar("pdbx_description", "molecule description")],
}


def _with_fake_schema(coro_factory):
    """Run an async flatten with server._type_fields swapped for the synthetic schema."""
    async def fake_type_fields(type_name, url=None):
        return _SCHEMA.get(type_name, [])

    orig = server._type_fields
    server._type_fields = fake_type_fields
    try:
        return asyncio.run(coro_factory())
    finally:
        server._type_fields = orig


def _flatten(**kw):
    kw.setdefault("root_type", "CoreEntry")
    kw.setdefault("url", "x")
    kw.setdefault("max_depth", 3)
    kw.setdefault("query", None)
    kw.setdefault("max_results", server.DATA_FIELDS_RESULT_CAP)
    return _with_fake_schema(lambda: server._flatten_object_fields(**kw))


def test_flatten_depth_and_traversal():
    fields, truncated = _flatten(max_depth=3)
    paths = {f["path"] for f in fields}
    # nested within-object + one traversal hop + that hop's nested object are all reached
    assert "struct.title" in paths
    assert "pubmed.rcsb_pubmed_abstract_text" in paths           # the motivating field
    assert "polymer_entities.rcsb_polymer_entity.pdbx_description" in paths
    # object fields are listed too (not just leaves), so they can be drilled/selected
    assert "polymer_entities" in paths and "struct" in paths
    assert not truncated
    print("ok: flatten depth + traversal")


def test_flatten_cycle_guard():
    # polymer_entities.entry re-enters CoreEntry (already on the path): the edge is listed,
    # but the walk does NOT recurse back into it, so nothing appears beneath it.
    fields, _ = _flatten(max_depth=6)
    paths = {f["path"] for f in fields}
    assert "polymer_entities.entry" in paths
    assert not any(p.startswith("polymer_entities.entry.") for p in paths), \
        "cycle guard should stop recursion into an ancestor type"
    print("ok: flatten cycle guard")


def test_flatten_depth_one():
    fields, _ = _flatten(max_depth=1)
    paths = {f["path"] for f in fields}
    assert paths == {"rcsb_id", "struct", "pubmed", "polymer_entities"}  # top level only
    assert not any("." in p for p in paths)
    print("ok: flatten depth=1")


def test_flatten_keyword_filter():
    # keyword matches the path OR the description; "abstract" hits only the pubmed leaf.
    fields, _ = _flatten(query="abstract")
    assert [f["path"] for f in fields] == ["pubmed.rcsb_pubmed_abstract_text"]
    # description-only match: "molecule" appears only in pdbx_description's description.
    desc_hit, _ = _flatten(query="molecule")
    assert [f["path"] for f in desc_hit] == ["polymer_entities.rcsb_polymer_entity.pdbx_description"]
    # a keyword matching nothing returns an empty catalog (not an error).
    none_hit, _ = _flatten(query="zzz_no_such_field")
    assert none_hit == []
    print("ok: flatten keyword filter")


def test_flatten_result_cap():
    # the result cap truncates and reports it (breadth-first, so shallow fields are kept).
    fields, truncated = _flatten(max_depth=3, max_results=2)
    assert truncated and len(fields) == 2
    print("ok: flatten result cap")


def test_field_descriptor_shape():
    # list-of-object unwraps to kind=object, list=True, with the inner type name.
    d = server._field_descriptor(_list_obj("polymer_entities", "CorePolymerEntity"))
    assert d == {"name": "polymer_entities", "kind": "object", "type": "CorePolymerEntity",
                 "list": True, "description": None}
    s = server._field_descriptor(_scalar("rcsb_id", "the id"))
    assert s["kind"] == "scalar" and s["list"] is False and s["type"] == "String"
    print("ok: field descriptor shape")


if __name__ == "__main__":
    test_flatten_depth_and_traversal()
    test_flatten_cycle_guard()
    test_flatten_depth_one()
    test_flatten_keyword_filter()
    test_flatten_result_cap()
    test_field_descriptor_shape()
    print("\nAll server tests passed.")
