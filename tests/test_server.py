"""Network-free tests for server-side logic that isn't a pure query builder.

Covers _flatten_object_fields (the recursive GraphQL-schema flatten behind
rcsb_describe_data_object's max_depth>1 search mode) by injecting a synthetic, deliberately CYCLIC schema in place
of the live introspection calls — so depth-capping, cycle-guarding, keyword filtering,
and the result cap are all exercised without touching the network.
"""
import asyncio
import inspect
import sys
import pathlib
from typing import get_args

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


def test_search_request_return_type_defaults_to_none():
    """`return_type` must have NO concrete default on the one tool that carries it.

    It used to live on seven tools, each with its own default. Now it lives once, and a
    concrete default here would make an omitted return_type indistinguishable from an
    explicit "entry" — so four of the seven services would silently return the wrong kind
    of identifier. None means "the caller did not choose", and queries.build_search_request
    resolves it from the query itself.

    The per-service values that resolution produces are pinned in
    tests/test_query_compose.py::test_default_return_type_matches_what_each_flat_tool_used.
    """
    default = inspect.signature(search.rcsb_search_request).parameters["return_type"].default
    assert default is None, (
        f"rcsb_search_request.return_type defaults to {default!r}; a concrete default hides "
        "the difference between an omitted and an explicit choice"
    )
    print("ok: return_type is resolved from the query, not defaulted in the signature")


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


# --- User-Agent: overridable per deployment, sent by every request helper ------------------ #
def _user_agent_with(value):
    """client._user_agent() with RCSB_MCP_USER_AGENT set to ``value`` (None = unset)."""
    import os

    saved = os.environ.pop("RCSB_MCP_USER_AGENT", None)
    if value is not None:
        os.environ["RCSB_MCP_USER_AGENT"] = value
    try:
        return client._user_agent()
    finally:
        os.environ.pop("RCSB_MCP_USER_AGENT", None)
        if saved is not None:
            os.environ["RCSB_MCP_USER_AGENT"] = saved


def test_user_agent_env_override():
    # "unknown" means the metadata lookup missed (e.g. a misspelt distribution name), which
    # would silently drop the version from every request.
    assert client.PACKAGE_VERSION != "unknown"
    assert f"/{client.PACKAGE_VERSION} " in client.DEFAULT_USER_AGENT
    assert _user_agent_with(None) == client.DEFAULT_USER_AGENT
    assert _user_agent_with("   ") == client.DEFAULT_USER_AGENT
    assert _user_agent_with("  rcsb-mcp-hosted/0.1 (k8s)\n") == "rcsb-mcp-hosted/0.1 (k8s)"
    assert _user_agent_with("rcsb-mcp-hosted/{version}") == f"rcsb-mcp-hosted/{client.PACKAGE_VERSION}"
    # httpx would raise an uncaught UnicodeEncodeError on every request; refuse it up front.
    for bad in ("rcsb-mcp-é", "a\nb", "a\tb"):
        try:
            _user_agent_with(bad)
        except ValueError as e:
            assert "RCSB_MCP_USER_AGENT" in str(e)
        else:
            raise AssertionError(f"{bad!r} should be rejected")
    print("ok: RCSB_MCP_USER_AGENT override")


def test_every_request_helper_sends_user_agent():
    # The header is read from client.USER_AGENT at call time, by all three helpers — a helper
    # that hardcoded its own string would make the deployment's traffic unattributable.
    seen = []

    class _Capture(_FakeClient):
        def __init__(self, **kwargs):
            super().__init__(_FakeResp(200, b"{}"))
            seen.append(kwargs["headers"]["User-Agent"])

        async def post(self, url, json=None):
            return self._resp

    orig_client, orig_ua = client.httpx.AsyncClient, client.USER_AGENT
    client.httpx.AsyncClient = lambda *a, **k: _Capture(**k)
    client.USER_AGENT = "rcsb-mcp-test/9"
    try:
        asyncio.run(client._post_search({}))
        asyncio.run(client._post_graphql("{ x }"))
        asyncio.run(client._get_json("http://x", {}, "Test"))
    finally:
        client.httpx.AsyncClient, client.USER_AGENT = orig_client, orig_ua
    assert seen == ["rcsb-mcp-test/9"] * 3, seen
    print("ok: every request helper sends USER_AGENT")


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
            # `enum` and `nested_group` are the optional keys — carried only where the
            # schema publishes a closed vocabulary, and where the attribute sits inside an
            # rcsb_nested_indexing container. Everything else is always present.
            assert set(e) - {"enum", "nested_group"} == \
                {"attribute", "type", "operators", "description"}, \
                f"{name}: unexpected keys on {e.get('attribute')!r}"
            assert e["type"] in types, f"{name}: bad type on {e['attribute']!r}: {e['type']!r}"
            unknown = set(e["operators"]) - ops
            assert not unknown, f"{name}: unknown operators on {e['attribute']!r}: {sorted(unknown)}"
            assert e["operators"], f"{name}: no operators on {e['attribute']!r}"
            assert e["attribute"] and e["description"], f"{name}: empty field on {e!r}"
            if "enum" in e:
                # An empty or single-item enum would be emitted noise; a duplicate would
                # mean the generator mangled the schema's list.
                assert isinstance(e["enum"], list) and e["enum"], \
                    f"{name}: empty enum on {e['attribute']!r}"
                vals = [str(v) for v in e["enum"]]
                assert len(vals) == len(set(vals)), f"{name}: duplicate enum values on {e['attribute']!r}"
    enums = [e for e in SEARCH_ATTRIBUTES if "enum" in e]
    assert enums, "the structure catalog must carry enums — value validation depends on them"
    print(f"ok: attribute catalogs conform ({len(SEARCH_ATTRIBUTES)} structure, "
          f"{len(CHEMICAL_SEARCH_ATTRIBUTES)} chemical; {len(enums)} with an enum)")


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


def test_list_attributes_multiword_matches_words_not_a_substring():
    # The motivating bug: "nonpolymer comp_id" used to match NOTHING, because the filter was
    # a literal substring and those words are never adjacent. Words match wherever they are.
    r = _list_attrs(query="nonpolymer comp_id")
    assert r["match_mode"] == "exact" and "note" not in r
    assert r["attributes"][0]["attribute"] == \
        "rcsb_nonpolymer_entity_container_identifiers.nonpolymer_comp_id"
    # underscore vs space: the catalog's paths use one, people the other
    space = _list_attrs(query="space group")
    assert space["attributes"][0]["attribute"] == "symmetry.space_group_name_H_M"
    print("ok: list attributes multi-word matches words")


def test_list_attributes_short_keywords_match_words_only():
    # "pH" used to match alpha, phase and pharmacology: 27 attributes, the right one 15th.
    r = _list_attrs(query="pH")
    assert [a["attribute"] for a in r["attributes"]] == ["exptl_crystal_grow.pH"]
    print("ok: short keywords match whole words")


def test_list_attributes_partial_and_empty_say_so():
    # Some words match, not all: shown, ranked by how many matched, and labelled as such.
    r = _list_attrs(query="covalent zzzqqq")
    assert r["match_mode"] == "partial" and r["count"] > 0
    assert "every word" in r["note"] and "covalent zzzqqq" in r["note"]
    # Nothing matches: a note that sends the caller somewhere, not a bare [] that reads as
    # "the PDB has no such attribute" (and once reached the model as ZERO content blocks).
    none = _list_attrs(query="zzzqqq_xxyy")
    assert none["count"] == 0 and none["attributes"] == [] and none["match_mode"] == "none"
    assert "zzzqqq_xxyy" in none["note"], "should quote the query back"
    assert 'schema="chemical"' in none["note"], "structure searches should mention the other catalog"
    # ...and the chemical catalog does not advertise itself
    chem = _list_attrs(query="zzzqqq_xxyy", schema="chemical")
    assert chem["match_mode"] == "none" and "chemical" not in chem["note"]
    # An identifier with no exact match is still looked up word by word: "crystal_ph" used
    # to get a note claiming none of its words matched anything.
    ph = _list_attrs(query="crystal_ph")
    assert ph["match_mode"] == "partial" and ph["attributes"][0]["attribute"] == "exptl_crystal_grow.pH"
    # A path dropped for holding no value says so, and offers its neighbours.
    gone = _list_attrs(query="rcsb_ligand_neighbors.ligand_is_bound")
    assert "holds no value anywhere in the search index" in gone["note"]
    assert gone["attributes"][0]["attribute"].startswith("rcsb_ligand_neighbors.")
    print("ok: partial and empty listings explain themselves")


def test_list_attributes_function_words_and_abbreviations():
    # "temp" in a path answers "temperature" (it was 6th, behind four EM paths)...
    top = [a["attribute"] for a in _list_attrs(query="temperature")["attributes"][:3]]
    assert "diffrn.ambient_temp" in top
    # ...but only for a word the catalog spells out: entity_poly does not answer "polymerase"
    assert _list_attrs(query="polymerase")["match_mode"] == "none"
    # "of" is not evidence: words scattered through one long description are not a match
    assert _list_attrs(query="number of chains")["match_mode"] != "exact"
    print("ok: function words and abbreviations")


def test_list_attributes_caps_a_keyword_query():
    r = _list_attrs(query="entity")
    assert r["count"] == len(r["attributes"]) == search.LIST_ATTRIBUTES_CAP
    assert "best of" in r["note"] and "more specific keyword" in r["note"]
    print("ok: keyword listings are capped")


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
    test_list_attributes_multiword_matches_words_not_a_substring()
    test_list_attributes_short_keywords_match_words_only()
    test_list_attributes_partial_and_empty_say_so()
    test_list_attributes_function_words_and_abbreviations()
    test_list_attributes_caps_a_keyword_query()
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
    test_search_request_return_type_defaults_to_none()
    test_get_json_204_empty()
    test_user_agent_env_override()
    test_every_request_helper_sends_user_agent()
    test_interpro_no_match_graceful()
    print("\nAll server tests passed.")


def test_nested_group_names_a_real_container_and_matches_the_scope_map():
    """`nested_group` is generated by a SECOND, independent walk of the search schema —
    scripts/generate_search_attributes.py — while queries._nested_record_of derives the same
    fact from scripts/generate_attribute_scopes.py. They must agree on every attribute, or
    the note and the catalog are telling agents different things about the same query.

    The value is the container PATH, deliberately, not a boolean: 22 structure attributes and
    4 chemical ones group under something that is NOT their first path segment
    (drugbank_info.drug_products.approved -> drugbank_info.drug_products), so a caller
    deriving the key instead of reading it gets those wrong. That was a real bug here.
    """
    for name, catalog, service in (("structure", SEARCH_ATTRIBUTES, "text"),
                                   ("chemical", CHEMICAL_SEARCH_ATTRIBUTES, "text_chem")):
        for e in catalog:
            assert queries._nested_record_of(e["attribute"], service) == e.get("nested_group"), (
                f"{name}: {e['attribute']} — catalog says {e.get('nested_group')!r}, "
                f"queries says {queries._nested_record_of(e['attribute'], service)!r}"
            )
            group = e.get("nested_group")
            if group is not None:
                assert e["attribute"].startswith(group + "."), (
                    f"{name}: {e['attribute']} is not inside its own nested_group {group!r}"
                )

    flagged = [e for e in SEARCH_ATTRIBUTES if "nested_group" in e]
    assert flagged, (
        "the structure catalog must carry nested_group — it is what tells a caller that the "
        "query shape is choosing same-record vs independent matching for them"
    )
    deep = [e for e in flagged if e["nested_group"] != e["attribute"].split(".")[0]]
    assert deep, (
        "no attribute groups below its first path segment — if a schema refresh really "
        "removed all of them, a boolean flag would now be as good as the path, and this "
        "test is the record of why the path was chosen"
    )


# --- the initialize handshake must identify THIS package, not the SDK ---------------
def test_the_handshake_reports_this_package_version_not_the_sdks():
    """A deployed beta reported serverInfo.version "1.30.0" while the package was 0.18.0.

    The number was the MCP SDK's. FastMCP accepts no `version` argument and forwards none
    to the lowlevel Server it builds, and that server's fallback is:

        server_version=self.version if self.version else pkg_version("mcp")

    So leaving it unset advertises the SDK's own version — a number that identifies the
    wrong software, contradicts pyproject.toml, and drifts upward on its own whenever the
    image rebuilds (the Dockerfile resolves dependencies fresh). A bug report quoting it is
    unactionable.

    Asserted on the InitializationOptions the server actually sends, not on the attribute,
    because the fallback lives in create_initialization_options rather than __init__.
    """
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    from rcsb_mcp import server

    opts = server.mcp._mcp_server.create_initialization_options()
    assert opts.server_name == "rcsb_mcp"

    try:
        expected = pkg_version("rcsb-mcp")
    except PackageNotFoundError:
        expected = "0+unknown"   # source tree, never installed — see server._server_version
    assert opts.server_version == expected, (
        f"handshake reports {opts.server_version!r}, expected this package's "
        f"version {expected!r}"
    )
    # The specific regression: never the SDK's version.
    assert opts.server_version != pkg_version("mcp"), (
        "serverInfo.version equals the mcp SDK version — the explicit version was dropped "
        "and the SDK fallback is being advertised again"
    )
    print(f"ok: handshake reports rcsb_mcp {opts.server_version}")
