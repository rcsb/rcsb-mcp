"""The walk depth follows browsing-vs-searching, because one default cannot serve both.

A keyword match at depth 1 can only match a TOP-LEVEL field name, and almost nothing an
agent looks for is top-level — `formula_weight` lives at `chem_comp.formula_weight`,
`pdbx_description` at `polymer_entities.rcsb_polymer_entity.pdbx_description`. So a
depth-1 search reported "no such field" for fields that plainly exist:

    describe("chem_comps", query="formula_weight")            -> 0    (right object!)
    describe("chem_comps", query="formula_weight", depth=2)   -> 2

That empty result is indistinguishable from naming the wrong object, so two different
mistakes rendered identically and neither was recoverable from the response.

Browsing is the opposite case and the old default was right for it: listing one level is
exactly what "show me this object's fields, I'll drill in" wants, and flattening three
levels would bury it. Hence a default per mode rather than a single number — and hence
the browse half is tested as hard as the search half, since raising the default globally
would fix one and break the other.

No network: the walk runs against a synthetic schema.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp.graphql import (  # noqa: E402
    BROWSE_DEFAULT_DEPTH,
    SEARCH_DEFAULT_DEPTH,
    resolve_max_depth,
)


# --------------------------------------------------------------------------- #
# The resolution rule
# --------------------------------------------------------------------------- #
def test_browsing_lists_one_level():
    assert resolve_max_depth(None, None) == BROWSE_DEFAULT_DEPTH == 1


def test_searching_goes_deep_enough_to_find_a_nested_field():
    assert resolve_max_depth(None, "formula_weight") == SEARCH_DEFAULT_DEPTH


def test_the_search_default_reaches_the_third_level():
    """2 is not enough: `pdbx_description` sits at depth 3 and returns 0 at depth 2.

    Pinned as a number because it is a measured floor, not a preference — dropping it to 2
    silently reinstates the empty-result bug for the most common lookup there is.
    """
    assert SEARCH_DEFAULT_DEPTH >= 3


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_query_is_not_a_search(blank):
    """`query=""` filters nothing, so it is a browse; treating it as a search would
    flatten three levels and bury the one the caller wanted."""
    assert resolve_max_depth(None, blank) == BROWSE_DEFAULT_DEPTH


@pytest.mark.parametrize("explicit", [1, 2, 4, 6])
def test_an_explicit_depth_always_wins(explicit):
    assert resolve_max_depth(explicit, None) == explicit
    assert resolve_max_depth(explicit, "resolution") == explicit


# --------------------------------------------------------------------------- #
# End to end, against a synthetic schema (no network)
# --------------------------------------------------------------------------- #
# entries -> struct.title, and entries -> polymer_entities -> rcsb_polymer_entity.pdbx_description
_SCHEMA = {
    "CoreEntry": [
        {"name": "rcsb_id", "description": "", "type": {"kind": "SCALAR", "name": "String"}},
        {"name": "struct", "description": "", "type": {"kind": "OBJECT", "name": "Struct"}},
        {"name": "polymer_entities", "description": "",
         "type": {"kind": "LIST", "name": None,
                  "ofType": {"kind": "OBJECT", "name": "CorePolymerEntity"}}},
    ],
    "Struct": [{"name": "title", "description": "the title",
                "type": {"kind": "SCALAR", "name": "String"}}],
    "CorePolymerEntity": [
        {"name": "rcsb_polymer_entity", "description": "",
         "type": {"kind": "OBJECT", "name": "RcsbPolymerEntity"}}],
    "RcsbPolymerEntity": [{"name": "pdbx_description", "description": "molecule description",
                           "type": {"kind": "SCALAR", "name": "String"}}],
}


@pytest.fixture
def describe(monkeypatch):
    """rcsb_describe_data_object with the live schema swapped for the synthetic one."""
    import asyncio

    from rcsb_mcp import data, graphql

    async def fake_type_fields(type_name, url=None):
        return _SCHEMA.get(type_name, [])

    async def fake_root_types(url=None):
        return {"entries": "CoreEntry"}

    monkeypatch.setattr(graphql, "_type_fields", fake_type_fields)
    monkeypatch.setattr(graphql, "_root_field_types", fake_root_types)
    return lambda **kw: asyncio.run(data.rcsb_describe_data_object("entries", **kw))


def test_a_search_finds_a_field_three_levels_down(describe):
    """The regression: this returned nothing, which read as "no such field"."""
    r = describe(query="pdbx_description")
    assert [f["path"] for f in r["fields"]] == \
        ["polymer_entities.rcsb_polymer_entity.pdbx_description"]
    assert r["max_depth"] == SEARCH_DEFAULT_DEPTH


def test_the_same_search_at_depth_one_still_finds_nothing(describe):
    """Pins WHY the default had to change: the old behaviour is still one argument away."""
    assert describe(query="pdbx_description", max_depth=1)["field_count"] == 0


def test_browsing_still_lists_exactly_one_level(describe):
    """The half that would break if the default were simply raised for everyone."""
    r = describe()
    assert {f["path"] for f in r["fields"]} == {"rcsb_id", "struct", "polymer_entities"}
    assert not any("." in f["path"] for f in r["fields"]), "browsing must not flatten"
    assert r["max_depth"] == BROWSE_DEFAULT_DEPTH


def test_the_response_reports_the_depth_actually_walked(describe):
    """`max_depth` in the response is what ran, not what was passed — otherwise a caller
    who omitted it cannot tell how deep the answer came from."""
    assert describe(query="title")["max_depth"] == SEARCH_DEFAULT_DEPTH
    assert describe()["max_depth"] == BROWSE_DEFAULT_DEPTH
    assert describe(query="title", max_depth=2)["max_depth"] == 2


def test_into_still_scopes_the_walk(describe):
    """Scoping must keep working: `into` + a search should not re-flatten from the root."""
    r = describe(into="struct", query="title")
    assert [f["path"] for f in r["fields"]] == ["struct.title"]


# --------------------------------------------------------------------------- #
# Both describe tools share the rule
# --------------------------------------------------------------------------- #
def test_both_describe_tools_resolve_depth_the_same_way():
    """seqcoord had the identical trap; a fix on one only would leave the other broken."""
    import inspect

    from rcsb_mcp import data, seqcoord

    for fn in (data.rcsb_describe_data_object, seqcoord.rcsb_describe_seqcoord_object):
        assert inspect.signature(fn).parameters["max_depth"].default is None, (
            f"{fn.__name__} pins a concrete max_depth default, so it cannot vary by mode"
        )
        assert "resolve_max_depth" in inspect.getsource(fn), (
            f"{fn.__name__} does not use the shared rule"
        )
