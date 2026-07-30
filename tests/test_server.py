"""Network-free tests for server-side logic that isn't a pure query builder.

Covers _flatten_object_fields (the recursive GraphQL-schema flatten behind
rcsb_describe_data_object's max_depth>1 search mode) by injecting a synthetic, deliberately CYCLIC schema in place
of the live introspection calls — so depth-capping, cycle-guarding, keyword filtering,
and the result cap are all exercised without touching the network.
"""
import asyncio
import sys
import pathlib
from typing import get_args

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import client, graphql, queries, search  # noqa: E402
from rcsb_mcp.attribute_types import AttributeValueType, TextOperator  # noqa: E402
from rcsb_mcp.chemical_search_attributes import CHEMICAL_SEARCH_ATTRIBUTES  # noqa: E402
from rcsb_mcp.search_attributes import SEARCH_ATTRIBUTES  # noqa: E402


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
    """Run an async flatten with graphql._type_fields swapped for the synthetic schema."""
    async def fake_type_fields(type_name, url=None):
        return _SCHEMA.get(type_name, [])

    orig = graphql._type_fields
    graphql._type_fields = fake_type_fields
    try:
        return asyncio.run(coro_factory())
    finally:
        graphql._type_fields = orig


def _flatten(**kw):
    kw.setdefault("root_type", "CoreEntry")
    kw.setdefault("url", "x")
    kw.setdefault("max_depth", 3)
    kw.setdefault("query", None)
    kw.setdefault("max_results", graphql.DATA_FIELDS_RESULT_CAP)
    return _with_fake_schema(lambda: graphql._flatten_object_fields(**kw))


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
    d = graphql._field_descriptor(_list_obj("polymer_entities", "CorePolymerEntity"))
    assert d == {"name": "polymer_entities", "kind": "object", "type": "CorePolymerEntity",
                 "list": True, "description": None}
    s = graphql._field_descriptor(_scalar("rcsb_id", "the id"))
    assert s["kind"] == "scalar" and s["list"] is False and s["type"] == "String"
    print("ok: field descriptor shape")


# --- _enrich_field_errors: raw GraphQL FieldUndefined -> self-correcting hint ------------- #
def _enrich(msgs, root_field="entries", url=None):
    """Run the enricher with the synthetic schema + a fake root-field->type resolver."""
    url = url or client.DATA_GRAPHQL_URL

    async def fake_type_fields(type_name, u=None):
        return _SCHEMA.get(type_name, [])

    async def fake_root_types(u=None):
        return {"entries": "CoreEntry", "alignments": "CoreEntry"}

    orig_tf, orig_rt = graphql._type_fields, graphql._root_field_types
    graphql._type_fields = fake_type_fields
    graphql._root_field_types = fake_root_types
    try:
        return asyncio.run(graphql._enrich_field_errors(msgs, root_field, url))
    finally:
        graphql._type_fields, graphql._root_field_types = orig_tf, orig_rt


def test_enrich_relocation():
    # a field placed on the wrong type is relocated to where it actually lives.
    out = _enrich("Field 'rcsb_pubmed_abstract_text' in type 'CoreEntry' is undefined")
    assert "not defined on type 'CoreEntry'" in out
    assert "pubmed.rcsb_pubmed_abstract_text" in out                 # correct path surfaced
    assert 'rcsb_describe_data_object("entries", query="rcsb_pubmed_abstract_text", max_depth=3)' in out
    print("ok: enrich relocation")


def test_enrich_sibling_typo():
    out = _enrich("Field 'titel' in type 'Struct' is undefined")
    assert "Did you mean: title?" in out
    assert "It exists in the schema at" not in out                   # no spurious relocation
    print("ok: enrich sibling typo")


def test_enrich_passthrough_non_field():
    # a non-FieldUndefined error is returned verbatim (nothing to correct).
    raw = "Some syntax error near '}'"
    assert _enrich(raw) == raw
    print("ok: enrich passthrough")


def test_enrich_unknown_field():
    # a pure hallucination still gets the discovery steer, but no false relocation/typo hint.
    out = _enrich("Field 'totally_made_up' in type 'CoreEntry' is undefined")
    assert "not defined on type 'CoreEntry'" in out
    assert "It exists in the schema at" not in out and "Did you mean" not in out
    assert 'rcsb_describe_data_object("entries", query="totally_made_up", max_depth=3)' in out
    print("ok: enrich unknown field")


def test_enrich_seqcoord_steer():
    # on the Sequence Coordinates endpoint the steer names the seqcoord discovery tool.
    out = _enrich("Field 'foo' in type 'CoreEntry' is undefined",
                  root_field="alignments", url=client.SEQCOORD_GRAPHQL_URL)
    assert 'rcsb_describe_seqcoord_object("alignments"' in out
    assert "rcsb_describe_data_object" not in out
    print("ok: enrich seqcoord steer")


def test_enrich_syntax_error():
    # a malformed selection (ANTLR/parse error) gets the accepted format + a discovery steer.
    raw = "Invalid syntax with ANTLR error 'token recognition error at: '.t'' at line 1 column 70"
    out = _enrich(raw)
    assert raw in out                                   # keep the original diagnostic
    assert "`fields=`" in out and "separated by spaces or commas" in out
    assert 'rcsb_describe_data_object("entries"' in out
    print("ok: enrich syntax error")


def test_search_return_type_defaults():
    """Per-tool return_type defaults are deliberate; pin the RESOLVED value, not a signature.

    They used to be signature defaults. Now `return_type` lives in SearchConfiguration, which
    defaults it to None precisely so each tool can apply its own — if the model carried a
    concrete default instead, an omitted return_type would be indistinguishable from an
    explicit "entry" and four of these searches would silently return the wrong entity type.
    So this asserts what `_cfg` actually resolves, which is the thing that can break.
    """
    _, rt = search._cfg(None, "assembly")
    # strucmotif defaults to "assembly" — the most general unit for a 3D motif and the
    # default of RCSB.org advanced search (symmetry mates only exist at assembly level).
    assert rt == "assembly"
    # the other polymer-oriented services default to "polymer_entity"
    assert search._cfg(None, "polymer_entity")[1] == "polymer_entity"
    # chemical defaults to the chemical component itself
    assert search._cfg(None, "mol_definition")[1] == "mol_definition"
    # keyword / attribute searches return whole entries
    assert search._cfg(None, "entry")[1] == "entry"
    # a caller's explicit choice always wins over the tool's default
    explicit = search.SearchConfiguration(return_type="entry")
    assert search._cfg(explicit, "polymer_entity")[1] == "entry"
    # ...and an omitted return_type must NOT be silently read as "entry"
    assert search.SearchConfiguration().return_type is None
    print("ok: search return_type defaults")


def test_search_configuration_defaults_are_uniform():
    """Every field except return_type has ONE default shared by all seven searches.

    That is what made the consolidation safe: only return_type varied per tool, so only it
    needed the None sentinel. If a future field grows per-tool defaults, it needs the same
    treatment and this will not catch it — but a change to these shared values will.
    """
    cfg = search.SearchConfiguration()
    assert (cfg.limit, cfg.offset, cfg.all_hits) == (10, 0, False)
    assert (cfg.logical_operator, cfg.sort_direction) == ("and", "asc")
    assert (cfg.attributes, cfg.facets, cfg.sort_by) == (None, None, None)
    assert (cfg.group_by, cfg.group_by_ranking) == (None, None)
    assert (cfg.chemical_attributes, cfg.include_computed_models) == (False, False)
    print("ok: SearchConfiguration shared defaults")


def test_attribute_search_refuses_an_empty_configuration():
    """`attributes` IS the query for rcsb_search_by_attribute, but the shared object cannot
    mark it required — six other searches treat it as optional refinement. So the tool must
    reject it loudly rather than issue a query matching the whole archive."""
    with pytest.raises(ValueError, match="attributes"):
        asyncio.run(search.rcsb_search_by_attribute(search.SearchConfiguration()))
    print("ok: empty attribute search refused")


# --- _get_json: a 204 / empty body must not crash the rcsb_find_* resolvers ---------------- #
class _FakeResp:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    @property
    def text(self):
        return self.content.decode() if isinstance(self.content, bytes) else str(self.content)

    def json(self):
        import json as _json
        return _json.loads(self.content)  # raises on empty body — the bug, if 204 isn't handled


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        return self._resp


def _get_json_with(resp):
    # _get_json (and its httpx) live in rcsb_mcp.client now; patch/call it there.
    from rcsb_mcp import client

    orig = client.httpx.AsyncClient
    client.httpx.AsyncClient = lambda *a, **k: _FakeClient(resp)
    try:
        return asyncio.run(client._get_json("http://x", {}, "Test"))
    finally:
        client.httpx.AsyncClient = orig


def test_get_json_204_empty():
    # 204 No Content (what EBI InterPro returns for a no-match query) -> {}, not a JSONDecodeError.
    assert _get_json_with(_FakeResp(204, b"")) == {}
    # a 200 with an empty body is treated the same way.
    assert _get_json_with(_FakeResp(200, b"")) == {}
    # a normal 200 JSON body still decodes.
    assert _get_json_with(_FakeResp(200, b'{"results": [1, 2]}')) == {"results": [1, 2]}
    print("ok: _get_json 204/empty")


def test_interpro_no_match_graceful():
    # with no matches (empty payload) the resolver returns count 0 + a fall-back-to-keyword note,
    # instead of propagating the JSONDecodeError that this input used to trigger.
    # The resolvers live in rcsb_mcp.resolvers now and resolve _get_json via that module's
    # globals, so patch it there (not on server, whose _get_json is only a re-export).
    from rcsb_mcp import resolvers

    async def fake_get_json(url, params, service):
        return {}

    orig = resolvers._get_json
    resolvers._get_json = fake_get_json
    try:
        r = asyncio.run(resolvers.rcsb_find_interpro_domains(
            query="acyltransferase domain polyketide synthase", limit=15, with_pdb_counts=False))
    finally:
        resolvers._get_json = orig
    assert r["count"] == 0 and r["entries"] == []
    assert r.get("note"), "should advise a keyword fallback when nothing matched"
    print("ok: interpro no-match graceful")


def test_resolver_pdb_count_path_runs():
    # The DEFAULT with_pdb_counts=True path fans PDB-count queries out with asyncio.gather,
    # so the resolvers module must import asyncio. Regression: extracting the resolvers into
    # their own module dropped that import (every rcsb_find_* NameError'd on its primary
    # path); no prior test exercised with_pdb_counts=True (the only resolver test used False).
    from rcsb_mcp import resolvers

    async def fake_get_json(url, params, service):
        return {"results": [{"id": "GO:0016301", "name": "kinase activity", "aspect": "molecular_function"}]}

    async def fake_post_search(body):
        return {"total_count": 7}

    oj, ops = resolvers._get_json, resolvers._post_search
    resolvers._get_json = fake_get_json
    resolvers._post_search = fake_post_search
    try:
        r = asyncio.run(resolvers.rcsb_find_go_terms("kinase activity"))  # with_pdb_counts=True default
    finally:
        resolvers._get_json, resolvers._post_search = oj, ops
    assert r["count"] == 1
    assert r["terms"][0]["pdb_entry_count"] == 7, "the gather/count path must run (needs the asyncio import)"
    print("ok: resolver pdb-count path runs")


def test_attribute_catalogs_conform():
    # No type checker runs in CI, so this is what actually pins the SearchAttribute
    # shape — and it catches a bad regeneration of the auto-generated chemical file.
    ops = set(get_args(TextOperator))
    types = set(get_args(AttributeValueType))
    assert ops == set(queries.TEXT_OPERATORS), "TEXT_OPERATORS must derive from TextOperator"
    for name, catalog in (("structure", SEARCH_ATTRIBUTES), ("chemical", CHEMICAL_SEARCH_ATTRIBUTES)):
        assert catalog, f"{name}: catalog is empty"
        paths = [e["attribute"] for e in catalog]
        assert len(paths) == len(set(paths)), f"{name}: duplicate attribute paths"
        for e in catalog:
            assert set(e) == {"attribute", "type", "operators", "description"}, \
                f"{name}: unexpected keys on {e.get('attribute')!r}"
            assert e["type"] in types, f"{name}: bad type on {e['attribute']!r}: {e['type']!r}"
            unknown = set(e["operators"]) - ops
            assert not unknown, f"{name}: unknown operators on {e['attribute']!r}: {sorted(unknown)}"
            assert e["operators"], f"{name}: no operators on {e['attribute']!r}"
            assert e["attribute"] and e["description"], f"{name}: empty field on {e!r}"
    print(f"ok: attribute catalogs conform ({len(SEARCH_ATTRIBUTES)} structure, "
          f"{len(CHEMICAL_SEARCH_ATTRIBUTES)} chemical)")


def _list_attrs(**kw):
    return asyncio.run(search.rcsb_list_pdb_search_attributes(**kw))


def test_list_attributes_exact_match():
    r = _list_attrs(query="comp_id")
    assert r["match_mode"] == "exact"
    assert r["count"] == len(r["attributes"]) > 0
    assert "note" not in r, "a successful match should not spend tokens on a note"
    assert all("comp_id" in a["attribute"].lower() or "comp_id" in a["description"].lower()
               for a in r["attributes"])
    print("ok: list attributes exact match")


def test_list_attributes_multiword_explains_itself():
    # The motivating bug: a multi-word query matches nothing, and the bare [] used to be
    # indistinguishable from "the PDB has no such attribute" (and reached the model as ZERO
    # content blocks). It must now say the query SHAPE is the likely cause.
    r = _list_attrs(query="nonpolymer comp_id")
    assert r["count"] == 0 and r["attributes"] == [] and r["match_mode"] == "none"
    note = r["note"]
    assert "single keyword" in note and "substring" in note
    assert "nonpolymer comp_id" in note, "should quote the query back"
    assert 'schema="chemical"' in note, "structure searches should mention the other catalog"
    # single-word misses get the other wording, and no phrase advice
    r1 = _list_attrs(query="zzz_no_such_attribute")
    assert r1["match_mode"] == "none" and "single keyword" not in r1["note"]
    # ...and the chemical catalog does not advertise itself
    r2 = _list_attrs(query="nonpolymer comp_id", schema="chemical")
    assert r2["match_mode"] == "none" and "chemical" not in r2["note"]
    print("ok: list attributes multi-word explains itself")


def test_list_attributes_full_catalog():
    r = _list_attrs()
    assert r["match_mode"] == "all"
    assert r["count"] == len(SEARCH_ATTRIBUTES) == len(r["attributes"])
    assert "large" in r["note"], "the ~675-attribute dump should warn about its size"
    assert _list_attrs(query="   ")["match_mode"] == "all", "blank query == omitted"
    assert _list_attrs(schema="chemical")["count"] == len(CHEMICAL_SEARCH_ATTRIBUTES)
    print("ok: list attributes full catalog")


def test_list_attributes_bad_schema():
    try:
        _list_attrs(schema="nope")
    except ValueError as e:
        assert "structure" in str(e) and "chemical" in str(e)
    else:
        raise AssertionError("an unknown schema must raise")
    print("ok: list attributes bad schema")


if __name__ == "__main__":
    test_attribute_catalogs_conform()
    test_list_attributes_exact_match()
    test_list_attributes_multiword_explains_itself()
    test_list_attributes_full_catalog()
    test_list_attributes_bad_schema()
    test_flatten_depth_and_traversal()
    test_flatten_cycle_guard()
    test_flatten_depth_one()
    test_flatten_keyword_filter()
    test_flatten_result_cap()
    test_field_descriptor_shape()
    test_enrich_relocation()
    test_enrich_sibling_typo()
    test_enrich_passthrough_non_field()
    test_enrich_unknown_field()
    test_enrich_seqcoord_steer()
    test_enrich_syntax_error()
    test_search_return_type_defaults()
    test_get_json_204_empty()
    test_interpro_no_match_graceful()
    print("\nAll server tests passed.")
