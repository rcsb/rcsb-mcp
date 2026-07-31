"""Searching every object: "which tool has this field?", not "describe this object".

Describing ONE object presupposed its own answer — you had to name the object, which is the
same as naming the tool, which is what the agent was trying to find out. Guessing wrong
returned an empty result indistinguishable from "no such field".

Searching them all is affordable (the type cache is shared, so the first search warms it and
the rest are instant) but the raw output is not usable: `formula_weight` matches 27 paths
across 9 objects. Two things make it usable, and both are tested here because both are easy
to get subtly wrong:

  * DEDUP — one field reached by many routes is one field.
  * RANKING — `query` also matches DESCRIPTIONS, which are CIF dictionary paragraphs, so
    "abstract" matches chem_comp.formula. Exact name matches have to come first.

No network: the walk runs against a synthetic schema.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp.graphql import SEARCH_ALL_RESULT_CAP, _field_identity, _match_rank  # noqa: E402


def _scalar(name, desc=""):
    return {"name": name, "description": desc, "type": {"kind": "SCALAR", "name": "String"}}


def _obj(name, type_name):
    return {"name": name, "description": "", "type": {"kind": "OBJECT", "name": type_name}}


# Two objects that BOTH reach RcsbPolymerEntity.formula_weight — entries by one more hop —
# plus a top-level field on a linked object, which is the case a path-shape rule splits.
_SCHEMA = {
    "CoreEntry": [
        _obj("rcsb_entry_info", "RcsbEntryInfo"),
        _obj("polymer_entities", "CorePolymerEntity"),
        _obj("pubmed", "CorePubmed"),
    ],
    "RcsbEntryInfo": [_scalar("molecular_weight", "total weight of the entry")],
    "CorePolymerEntity": [_obj("rcsb_polymer_entity", "RcsbPolymerEntity")],
    "RcsbPolymerEntity": [_scalar("formula_weight", "weight of the polymer")],
    # `title` is TOP-LEVEL (depth 0) and matches "formula" only through its description,
    # while the real `formula` field is a level down. Sorting by depth alone therefore puts
    # the wrong one first — which is what makes the ranking tests below actually test ranking
    # rather than agreeing with depth by luck.
    "CorePubmed": [_scalar("rcsb_pubmed_abstract_text", "the paper abstract"),
                   _scalar("title", "a paper, sometimes about a chemical formula")],
    "CoreChemComp": [_obj("chem_comp", "ChemComp")],
    "ChemComp": [_scalar("formula_weight", "weight of the component"),
                 _scalar("formula", "the formula, abstracted from the atom list")],
}
_ROOTS = {"entries": "CoreEntry", "polymer_entities": "CorePolymerEntity",
          "chem_comps": "CoreChemComp", "pubmed": "CorePubmed"}
_OBJECTS = {"entries": "entries", "polymer_entities": "polymer_entities",
            "chem_comps": "chem_comps", "pubmed": "pubmed"}


@pytest.fixture
def search(monkeypatch):
    from rcsb_mcp import graphql

    async def fake_type_fields(type_name, url=None):
        return _SCHEMA.get(type_name, [])

    async def fake_root_types(url=None):
        return _ROOTS

    monkeypatch.setattr(graphql, "_type_fields", fake_type_fields)
    monkeypatch.setattr(graphql, "_root_field_types", fake_root_types)
    return lambda q, depth=3: asyncio.run(
        graphql.search_all_objects(_OBJECTS, "x", q, depth))


# --------------------------------------------------------------------------- #
# Dedup: one field, reported once, attributed to its most direct owner
# --------------------------------------------------------------------------- #
def test_a_field_reachable_by_two_routes_is_reported_once(search):
    fields, _ = search("formula_weight")
    polymer = [f for f in fields if f["path"].endswith("rcsb_polymer_entity.formula_weight")]
    assert len(polymer) == 1, f"same field reported {len(polymer)} times: {polymer}"


def test_the_shortest_route_wins(search):
    """`polymer_entities` owns it; `entries` only links to it one hop further out."""
    fields, _ = search("formula_weight")
    row = next(f for f in fields if f["path"].endswith("rcsb_polymer_entity.formula_weight"))
    assert row["object_key"] == "polymer_entities"
    assert row["path"] == "rcsb_polymer_entity.formula_weight"


def test_a_linked_objects_top_level_field_is_not_double_reported(search):
    """The case a path-shape rule gets wrong.

    `rcsb_pubmed_abstract_text` is top-level on `pubmed` and `pubmed.rcsb_pubmed_abstract_text`
    from `entries`. Judging identity by path segments splits those in two; the declaring
    GraphQL type does not.
    """
    fields, _ = search("abstract_text")
    hits = [f for f in fields if f["path"].endswith("rcsb_pubmed_abstract_text")]
    assert len(hits) == 1, f"reported {len(hits)} times: {[h['path'] for h in hits]}"
    assert hits[0]["object_key"] == "pubmed"


def test_fields_that_merely_share_a_name_stay_separate(search):
    """The opposite error: `ChemComp.formula_weight` and `RcsbPolymerEntity.formula_weight`
    are different fields and must both survive."""
    fields, _ = search("formula_weight")
    owners = {f["object_key"] for f in fields}
    assert {"chem_comps", "polymer_entities"} <= owners, owners


def test_identity_is_the_declaring_type_not_the_path():
    """Pinned directly: same type + name is one field however it was reached."""
    a = {"_parent_type": "RcsbPolymerEntity", "path": "rcsb_polymer_entity.formula_weight"}
    b = {"_parent_type": "RcsbPolymerEntity",
         "path": "polymer_entities.rcsb_polymer_entity.formula_weight"}
    c = {"_parent_type": "ChemComp", "path": "chem_comp.formula_weight"}
    assert _field_identity(a) == _field_identity(b)
    assert _field_identity(a) != _field_identity(c)


# --------------------------------------------------------------------------- #
# Ranking: why it matched matters more than where it lives
# --------------------------------------------------------------------------- #
def test_an_exact_field_name_outranks_a_description_match(search):
    """`abstract` matches ChemComp.formula only through its description prose."""
    fields, _ = search("abstract")
    paths = [f["path"] for f in fields]
    assert paths[0].endswith("rcsb_pubmed_abstract_text"), paths
    assert any(p.endswith("chem_comp.formula") for p in paths), \
        "description matches should still be reachable, just ranked below"
    assert paths.index("rcsb_pubmed_abstract_text") < \
        next(i for i, p in enumerate(paths) if p.endswith("chem_comp.formula"))


@pytest.mark.parametrize("path, keyword, rank", [
    ("chem_comp.formula_weight", "formula_weight", 0),   # exact field name
    ("chem_comp.formula_weight", "formula", 1),          # part of the field name
    ("chem_comp.formula_weight", "chem_comp", 2),        # elsewhere in the path
    ("chem_comp.formula", "abstract", 3),                # description only
])
def test_match_rank_orders_by_why_it_matched(path, keyword, rank):
    assert _match_rank(path, keyword) == rank


def test_results_are_sorted_by_rank_then_depth(search):
    fields, _ = search("formula")
    ranks = [_match_rank(f["path"], "formula") for f in fields]
    assert ranks == sorted(ranks), f"not ordered by match quality: {ranks}"


def test_rank_beats_depth_when_they_disagree(search):
    """The test that makes the others mean something.

    `pubmed.title` is top-level and matches "formula" only in its description; the real
    `formula` field sits a level down. Ordering by depth alone puts the description match
    first, so this fails for any implementation that does not genuinely rank.
    """
    fields, _ = search("formula")
    paths = [f["path"] for f in fields]
    assert paths[0] == "chem_comp.formula", (
        f"a description-only match at depth 0 outranked the exact field name: {paths}"
    )
    assert "title" in paths, "the description match must still be reachable, just later"
    assert paths.index("chem_comp.formula") < paths.index("title")


# --------------------------------------------------------------------------- #
# Shape and bounds
# --------------------------------------------------------------------------- #
def test_every_field_names_the_object_that_owns_it(search):
    fields, _ = search("formula_weight")
    assert all(f["object_key"] in _OBJECTS for f in fields)


def test_the_internal_identity_key_never_reaches_the_caller(search):
    """`_parent_type` exists only to compute identity; shipping it would cost tokens."""
    fields, _ = search("formula_weight")
    assert not any("_parent_type" in f for f in fields)


def test_only_scalars_are_returned(search):
    """An object node is not something you can put in `fields=` on its own."""
    fields, _ = search("formula_weight")
    assert all(f["kind"] == "scalar" for f in fields)


def test_the_result_set_is_capped_and_says_so(search, monkeypatch):
    from rcsb_mcp import graphql

    monkeypatch.setattr(graphql, "SEARCH_ALL_RESULT_CAP", 2)
    fields, truncated = search("formula")
    assert len(fields) == 2 and truncated


def test_a_normal_search_is_not_reported_as_truncated(search):
    fields, truncated = search("formula_weight")
    assert not truncated and len(fields) < SEARCH_ALL_RESULT_CAP


# --------------------------------------------------------------------------- #
# The tool's own gates
# --------------------------------------------------------------------------- #
def _describe(monkeypatch, **kw):
    from rcsb_mcp import data, graphql

    async def fake_type_fields(type_name, url=None):
        return _SCHEMA.get(type_name, [])

    async def fake_root_types(url=None):
        return _ROOTS

    monkeypatch.setattr(graphql, "_type_fields", fake_type_fields)
    monkeypatch.setattr(graphql, "_root_field_types", fake_root_types)
    return asyncio.run(data.rcsb_describe_data_object(**kw))


def test_searching_everything_without_a_keyword_is_refused(monkeypatch):
    """It would return the whole Data API schema; the error says what to pass instead."""
    with pytest.raises(ValueError, match="needs a `query`"):
        _describe(monkeypatch)


def test_into_without_an_object_key_is_refused(monkeypatch):
    """`into` scopes a walk inside one object, so it cannot apply to all of them."""
    with pytest.raises(ValueError, match="needs an object_key"):
        _describe(monkeypatch, query="formula_weight", into="chem_comp")


def test_the_search_response_names_the_tool_to_call(monkeypatch):
    """The whole point: the answer is directly actionable without a second guess."""
    r = _describe(monkeypatch, query="formula_weight")
    assert r["object_key"] is None and r["searched"] == "all objects"
    tools = {f["tool"] for f in r["fields"]}
    assert "rcsb_get_chem_comps" in tools and "rcsb_get_polymer_entities" in tools
    assert all(t.startswith("rcsb_get_") for t in tools)
    assert not any("object_key" in f for f in r["fields"]), "replaced by `tool`"


def test_naming_an_object_still_scopes_to_it(monkeypatch):
    """The existing behaviour must be untouched — no `tool` key, no cross-object rows."""
    r = _describe(monkeypatch, object_key="chem_comps", query="formula_weight")
    assert r["object_key"] == "chem_comps"
    assert [f["path"] for f in r["fields"]] == ["chem_comp.formula_weight"]
    assert not any("tool" in f for f in r["fields"])
