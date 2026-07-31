"""The superseded rcsb_search_* names: dispatchable, but never advertised.

The rcsb_query_* layer renamed every search tool. A client that fetched its tool list
before that rename still holds the old names and will keep calling them until it
refreshes — so the names must keep working, without costing anything on the token
surface that every fresh client pays for.

The tests that matter here go over the WIRE, through a real client session, not through
`server.mcp.list_tools()`. Those two can disagree: FastMCP binds `self.list_tools` inside
`__init__`, so a filter applied any later way than an override would change what a direct
caller sees while the protocol handler kept serving the full list. That divergence is
invisible to a test that only calls the method — and it is exactly the bug this design
is one refactor away from.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import search, server  # noqa: E402
from rcsb_mcp.tooling import RcsbFastMCP  # noqa: E402

LEGACY = [fn.__name__ for fn in search._LEGACY_SEARCH_TOOLS]


def _via_wire(coro_factory):
    """Run a coroutine against a real client session connected to the real server."""

    async def run():
        async with create_connected_server_and_client_session(server.mcp) as client:
            return await coro_factory(client)

    return asyncio.run(run())


# --------------------------------------------------------------------------- #
# Over the wire
# --------------------------------------------------------------------------- #
def test_the_wire_protocol_does_not_advertise_the_legacy_names():
    """tools/list is what a client pays for and routes by; the old names must not be in it."""
    listed = {t.name for t in _via_wire(lambda c: c.list_tools()).tools}
    leaked = sorted(set(LEGACY) & listed)
    assert not leaked, f"tools/list still advertises superseded names: {leaked}"
    assert "rcsb_search_request" in listed and "rcsb_query_attribute" in listed


def test_the_wire_listing_matches_the_direct_call():
    """The divergence this design must not have.

    If these ever disagree, every other test in the suite is measuring a different tool
    set than clients receive.
    """
    wire = sorted(t.name for t in _via_wire(lambda c: c.list_tools()).tools)
    direct = sorted(t.name for t in asyncio.run(server.mcp.list_tools()))
    assert wire == direct


@pytest.mark.parametrize("name", LEGACY)
def test_a_stale_client_can_still_call_a_legacy_name(name, monkeypatch):
    """Registered-but-hidden means dispatch works even though discovery does not."""
    async def fake_post(body):
        return {"total_count": 1, "result_set": [{"identifier": "4HHB", "score": 1.0}]}

    monkeypatch.setattr(search, "_post_search", fake_post)

    args = {
        "rcsb_search_fulltext": {"query": "hemoglobin"},
        "rcsb_search_by_attribute": {"attributes": [
            {"attribute": "exptl.method", "operator": "exact_match",
             "value": "X-RAY DIFFRACTION"}]},
        "rcsb_search_by_sequence": {"sequence": "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTT"},
        "rcsb_search_by_chemical": {"value": "C9H8O4", "query_type": "formula"},
        "rcsb_search_by_structure": {"entry_id": "4HHB", "assembly_id": "1"},
        "rcsb_search_by_seqmotif": {"pattern": "CXCXXL", "pattern_type": "simple"},
        "rcsb_search_strucmotif": {"entry_id": "2MNR", "residue_ids": [
            {"label_asym_id": "A", "label_seq_id": 162},
            {"label_asym_id": "A", "label_seq_id": 193}]},
    }[name]

    result = _via_wire(lambda c: c.call_tool(name, args))
    assert not result.isError, f"{name} failed for a stale client: {result.content}"
    payload = json.loads(result.content[0].text)
    assert payload["hits"] == [{"id": "4HHB", "score": 1.0}]


def test_an_unknown_name_is_still_an_error():
    """Hiding must not turn the server into one that answers anything."""
    result = _via_wire(lambda c: c.call_tool("rcsb_search_by_telepathy", {}))
    assert result.isError


# --------------------------------------------------------------------------- #
# Cost
# --------------------------------------------------------------------------- #
def test_hidden_tools_cost_nothing_on_the_token_surface():
    """The whole point: a deprecated name a client never receives is never paid for."""
    listed = _via_wire(lambda c: c.list_tools()).tools
    surface = json.dumps([
        {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
        for t in listed
    ])
    for name in LEGACY:
        assert f'"{name}"' not in surface, f"{name} reaches the client after all"
    # And their descriptions — the expensive part — are nowhere in what ships.
    assert "rcsb_search_by_attribute" not in surface


# --------------------------------------------------------------------------- #
# The mechanism
# --------------------------------------------------------------------------- #
def test_hiding_an_unregistered_tool_is_an_error():
    """A typo'd name would otherwise hide nothing, silently."""
    mcp = RcsbFastMCP(name="t")
    with pytest.raises(ValueError, match="not registered"):
        mcp.hide_tool("rcsb_search_by_nothing")


def test_a_plain_fastmcp_server_registers_no_legacy_names():
    """Unit tests build a plain FastMCP; it must advertise exactly what a fresh client sees.

    Registering the legacy names there without being able to hide them would make every
    schema/inventory assertion in the suite measure a tool set no client receives.
    """
    plain = FastMCP("test")
    search.register_search_tools(plain)
    names = {t.name for t in asyncio.run(plain.list_tools())}
    assert not (set(LEGACY) & names)
    assert "rcsb_search_request" in names


def test_the_legacy_roster_is_exactly_the_superseded_tools():
    """A new tool must not drift into the hidden set — hidden means nobody can find it."""
    assert set(LEGACY) == {
        "rcsb_search_fulltext", "rcsb_search_by_attribute", "rcsb_search_by_sequence",
        "rcsb_search_by_chemical", "rcsb_search_by_structure", "rcsb_search_by_seqmotif",
        "rcsb_search_strucmotif",
    }
    assert server.mcp.hidden_tools == set(LEGACY)


def test_a_legacy_name_and_its_replacement_build_the_same_query(monkeypatch):
    """The alias is the old implementation, not a re-derivation — so it cannot drift.

    Both paths now route through queries.build_search_request; this pins that they still
    agree on a case exercising the envelope, so a stale client gets the same search a
    current one would.
    """
    sent: list[dict] = []

    async def fake_post(body):
        sent.append(body)
        return {"total_count": 1, "result_set": [{"identifier": "4HHB", "score": 1.0}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    attrs = [{"attribute": "rcsb_entry_info.resolution_combined",
              "operator": "less", "value": 2.0}]

    _via_wire(lambda c: c.call_tool("rcsb_search_by_attribute", {
        "attributes": attrs, "return_type": "polymer_entity", "limit": 25,
        "group_by": "seqid_95", "group_by_ranking": "resolution"}))

    doc = _via_wire(lambda c: c.call_tool("rcsb_query_attribute", {"attributes": attrs}))
    _via_wire(lambda c: c.call_tool("rcsb_search_request", {
        "query": json.loads(doc.content[0].text), "return_type": "polymer_entity",
        "limit": 25, "group_by": "seqid_95", "group_by_ranking": "resolution"}))

    assert len(sent) == 2
    assert json.dumps(sent[0], sort_keys=True) == json.dumps(sent[1], sort_keys=True)
