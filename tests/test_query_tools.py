"""The nine layered search tools, driven through the real MCP call path.

These go through `mcp.call_tool`, not the Python functions, because that is where the
JSON round trip happens: a query document leaves as JSON, comes back as JSON, and is
re-parsed into a pydantic model. Calling the functions directly would skip exactly the
step the digest exists to protect.

No network: `_post_search` is patched. What is asserted is the request body that WOULD
have been sent, plus the errors an agent sees when it misuses the chain.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp import search  # noqa: E402

SEQ = "MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSHGSAQVKGHGKKVADALTNAVAHVDDMPNAL"
HUMAN = {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
         "operator": "exact_match", "value": "Homo sapiens"}
MOUSE = {"attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
         "operator": "exact_match", "value": "Mus musculus"}
HIRES = {"attribute": "rcsb_entry_info.resolution_combined", "operator": "less", "value": 2.0}


@pytest.fixture
def mcp():
    server = FastMCP("test")
    search.register_search_tools(server)
    return server


@pytest.fixture
def sent(monkeypatch):
    """Capture the body that would have been POSTed to the Search API."""
    captured: list[dict] = []

    async def fake_post(body):
        captured.append(body)
        return {"total_count": 2, "result_set": [
            {"identifier": "4HHB", "score": 1.0}, {"identifier": "1A3N", "score": 0.9}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    return captured


def call(mcp, name, args):
    _content, result = asyncio.run(mcp.call_tool(name, args))
    return result


# --------------------------------------------------------------------------- #
# Each builder produces a document the request tool accepts
# --------------------------------------------------------------------------- #
BUILDERS = [
    ("rcsb_query_fulltext", {"query": "CRISPR Cas9"}, "full_text"),
    ("rcsb_query_attribute", {"attributes": [HIRES]}, "text"),
    ("rcsb_query_sequence", {"sequence": SEQ}, "sequence"),
    ("rcsb_query_chemical", {"value": "C9H8O4", "query_type": "formula"}, "chemical"),
    ("rcsb_query_structure", {"entry_id": "4HHB", "assembly_id": "1"}, "structure"),
    ("rcsb_query_seqmotif", {"pattern": "CXCXXL", "pattern_type": "simple"}, "seqmotif"),
    ("rcsb_query_strucmotif", {"entry_id": "2MNR", "residue_ids": [
        {"label_asym_id": "A", "label_seq_id": 162},
        {"label_asym_id": "A", "label_seq_id": 193}]}, "strucmotif"),
]


@pytest.mark.parametrize("tool, args, service", BUILDERS, ids=[b[0] for b in BUILDERS])
def test_builder_returns_a_document_the_request_tool_runs(mcp, sent, tool, args, service):
    doc = call(mcp, tool, args)
    assert set(doc) == {"query", "digest"}
    assert doc["query"]["service"] == service

    out = call(mcp, "rcsb_search_request", {"query": doc})
    assert sent[-1]["query"] == doc["query"]
    assert out["hits"] == [{"id": "4HHB", "score": 1.0}, {"id": "1A3N", "score": 0.9}]


@pytest.mark.parametrize("tool, args, expected", [
    ("rcsb_query_fulltext", {"query": "kinase"}, "entry"),
    ("rcsb_query_sequence", {"sequence": SEQ}, "polymer_entity"),
    ("rcsb_query_chemical", {"value": "C9H8O4", "query_type": "formula"}, "mol_definition"),
    ("rcsb_query_structure", {"entry_id": "4HHB", "asym_id": "A"}, "polymer_instance"),
    ("rcsb_query_structure", {"entry_id": "4HHB", "assembly_id": "1"}, "assembly"),
], ids=["fulltext", "sequence", "chemical", "structure-chain", "structure-assembly"])
def test_return_type_defaults_to_what_the_query_implies(mcp, sent, tool, args, expected):
    """An omitted return_type must not silently become "entry" for every service."""
    doc = call(mcp, tool, args)
    call(mcp, "rcsb_search_request", {"query": doc})
    assert sent[-1]["return_type"] == expected


# --------------------------------------------------------------------------- #
# Composition — the capability the flat tools never had
# --------------------------------------------------------------------------- #
def test_nested_boolean_groups(mcp, sent):
    """(human OR mouse) AND resolution < 2 A — inexpressible before the composer."""
    either = call(mcp, "rcsb_query_attribute",
                  {"attributes": [HUMAN, MOUSE], "logical_operator": "or"})
    res = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    both = call(mcp, "rcsb_query_composer",
                {"queries": [either, res], "logical_operator": "and"})
    call(mcp, "rcsb_search_request", {"query": both})

    q = sent[-1]["query"]
    assert q["logical_operator"] == "and"
    assert q["nodes"][0]["logical_operator"] == "or", "the OR group must stay nested"
    assert len(q["nodes"][0]["nodes"]) == 2
    assert q["nodes"][1]["parameters"]["attribute"] == "rcsb_entry_info.resolution_combined"


def test_cross_service_composition(mcp, sent):
    """A sequence match AND a shape match — two services in one query."""
    seq = call(mcp, "rcsb_query_sequence", {"sequence": SEQ})
    shape = call(mcp, "rcsb_query_structure", {"entry_id": "4HHB", "assembly_id": "1"})
    both = call(mcp, "rcsb_query_composer", {"queries": [seq, shape]})
    call(mcp, "rcsb_search_request", {"query": both})

    services = {n["service"] for n in sent[-1]["query"]["nodes"]}
    assert services == {"sequence", "structure"}
    # No single ranking applies to a mixed query, so none is imposed.
    assert "scoring_strategy" not in sent[-1]["request_options"]
    assert sent[-1]["return_type"] == "entry"


def test_composition_can_be_iterated(mcp, sent):
    """Feeding a composed document back in is how deeper nesting is built."""
    a = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    b = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    first = call(mcp, "rcsb_query_composer", {"queries": [a, b], "logical_operator": "or"})
    c = call(mcp, "rcsb_query_fulltext", {"query": "kinase"})
    second = call(mcp, "rcsb_query_composer", {"queries": [first, c], "logical_operator": "and"})
    call(mcp, "rcsb_search_request", {"query": second})

    q = sent[-1]["query"]
    assert q["logical_operator"] == "and"
    assert q["nodes"][0]["logical_operator"] == "or"


def test_same_operator_composition_stays_flat(mcp, sent):
    a = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    b = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    both = call(mcp, "rcsb_query_composer", {"queries": [a, b], "logical_operator": "and"})
    call(mcp, "rcsb_search_request", {"query": both})
    assert all(n["type"] == "terminal" for n in sent[-1]["query"]["nodes"])


# --------------------------------------------------------------------------- #
# The digest, across the real JSON round trip
# --------------------------------------------------------------------------- #
def test_an_edited_query_is_refused(mcp, sent):
    """The failure the whole design exists to prevent: a silently different search."""
    doc = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    doc["query"]["parameters"]["value"] = 3.0  # a plausible, valid, WRONG edit

    with pytest.raises(Exception, match="modified after it was built"):
        call(mcp, "rcsb_search_request", {"query": doc})
    assert not sent, "nothing may reach the Search API"


def test_a_hand_written_query_is_refused(mcp, sent):
    """Builders stay the only way in, without making queries opaque."""
    fake = {"query": {"type": "terminal", "service": "text",
                      "parameters": {"attribute": "exptl.method",
                                     "operator": "exact_match", "value": "X-RAY DIFFRACTION"}},
            "digest": "0" * 12}
    with pytest.raises(Exception, match="modified after it was built"):
        call(mcp, "rcsb_search_request", {"query": fake})
    assert not sent


def test_the_composer_verifies_its_inputs(mcp, sent):
    a = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    b = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    b["query"]["parameters"]["value"] = 9.9
    with pytest.raises(Exception, match="modified after it was built"):
        call(mcp, "rcsb_query_composer", {"queries": [a, b]})


def test_a_faithful_round_trip_through_json_still_verifies(mcp, sent):
    """Key re-ordering and float re-spelling happen in transit; neither may fail."""
    import json

    doc = call(mcp, "rcsb_query_attribute", {"attributes": [HIRES]})
    reordered = json.loads(json.dumps(doc, sort_keys=True))
    call(mcp, "rcsb_search_request", {"query": reordered})
    assert sent[-1]["query"]["parameters"]["value"] == 2.0


# --------------------------------------------------------------------------- #
# The envelope
# --------------------------------------------------------------------------- #
def test_envelope_parameters_reach_the_request_body(mcp, sent):
    doc = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    call(mcp, "rcsb_search_request", {
        "query": doc, "return_type": "polymer_entity", "limit": 50, "offset": 100,
        "include_computed_models": True, "group_by": "seqid_95",
        "group_by_ranking": "resolution",
        "sort_by": "rcsb_accession_info.initial_release_date", "sort_direction": "desc"})
    body = sent[-1]
    opts = body["request_options"]
    assert body["return_type"] == "polymer_entity"
    assert opts["paginate"] == {"start": 100, "rows": 50}
    assert opts["results_content_type"] == ["experimental", "computational"]
    assert opts["group_by"]["similarity_cutoff"] == 95
    assert opts["group_by_return_type"] == "representatives"
    assert opts["sort"] == [{"sort_by": "rcsb_accession_info.initial_release_date",
                             "direction": "desc"}]


def test_facets_return_a_breakdown_instead_of_hits(mcp, monkeypatch):
    async def fake_post(body):
        return {"total_count": 7, "facets": [
            {"name": "by_method", "buckets": [{"label": "X-RAY DIFFRACTION", "population": 7}]}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    server = FastMCP("test")
    search.register_search_tools(server)
    doc = call(server, "rcsb_query_attribute", {"attributes": [HUMAN]})
    out = call(server, "rcsb_search_request", {"query": doc, "facets": [
        {"name": "by_method", "aggregation_type": "terms", "attribute": "exptl.method"}]})
    assert "hits" not in out
    assert out["facets"][0]["buckets"][0]["population"] == 7


def test_all_hits_is_refused_above_the_cap(mcp, monkeypatch):
    async def fake_post(body):
        return {"total_count": search.ALL_HITS_MAX + 1, "result_set": []}

    monkeypatch.setattr(search, "_post_search", fake_post)
    server = FastMCP("test")
    search.register_search_tools(server)
    doc = call(server, "rcsb_query_attribute", {"attributes": [HUMAN]})
    with pytest.raises(Exception, match="above the"):
        call(server, "rcsb_search_request", {"query": doc, "all_hits": True})


def test_all_hits_rejects_an_offset(mcp, sent):
    doc = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    with pytest.raises(Exception, match="can't be combined with offset"):
        call(mcp, "rcsb_search_request", {"query": doc, "all_hits": True, "offset": 10})


# --------------------------------------------------------------------------- #
# Attribute-path validation, split across the two layers it belongs to
# --------------------------------------------------------------------------- #
def test_a_guessed_attribute_path_fails_at_build_time(mcp, sent):
    """Fast, local, with a "did you mean" — before anything is composed or sent."""
    with pytest.raises(Exception, match="do not guess"):
        call(mcp, "rcsb_query_attribute",
             {"attributes": [{"attribute": "rcsb_ec_lineage.id",
                              "operator": "exact_match", "value": "1.1.1.1"}]})
    assert not sent


def test_a_guessed_sort_path_fails_at_request_time(mcp, sent):
    """sort_by is not known until the envelope is applied, so it validates there."""
    doc = call(mcp, "rcsb_query_attribute", {"attributes": [HUMAN]})
    with pytest.raises(Exception, match="not a searchable structure attribute"):
        call(mcp, "rcsb_search_request", {"query": doc, "sort_by": "made.up.path"})
    assert not sent


def test_chemical_attribute_queries_validate_against_the_chemical_catalog(mcp, sent):
    doc = call(mcp, "rcsb_query_attribute", {
        "attributes": [{"attribute": "chem_comp.formula_weight",
                        "operator": "greater", "value": 300}],
        "chemical_attributes": True})
    assert doc["query"]["service"] == "text_chem"
    call(mcp, "rcsb_search_request", {"query": doc, "return_type": "mol_definition"})
    assert sent[-1]["query"]["service"] == "text_chem"


def test_a_wrong_operator_for_the_type_is_rejected(mcp, sent):
    with pytest.raises(Exception, match="is not valid for attribute"):
        call(mcp, "rcsb_query_attribute", {"attributes": [
            {"attribute": "rcsb_entry_info.resolution_combined",
             "operator": "contains_phrase", "value": "2.0"}]})
    assert not sent


# --------------------------------------------------------------------------- #
# Schema surface
# --------------------------------------------------------------------------- #
def test_the_envelope_lives_only_on_the_request_tool(mcp):
    """The point of the split: no rcsb_query_* tool carries result-shaping parameters."""
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    envelope = {"return_type", "limit", "offset", "all_hits", "include_computed_models",
                "facets", "sort_by", "sort_direction", "group_by", "group_by_ranking"}
    assert envelope <= set(tools["rcsb_search_request"].inputSchema["properties"])
    for name, tool in tools.items():
        if not name.startswith("rcsb_query_"):
            continue
        leaked = envelope & set(tool.inputSchema.get("properties", {}))
        assert not leaked, f"{name} still carries envelope parameters {sorted(leaked)}"


def test_the_response_says_what_came_back_and_where_to_take_it(mcp, sent):
    """return_type is the one search choice with no local failure signal.

    A wrong return_type still succeeds and still returns plausible identifiers, just of
    the wrong KIND — the mistake only surfaces later, when a rcsb_get_* tool rejects
    them. Naming the kind and the tool in the response catches it at the point of use,
    and costs nothing on the always-on tool surface.
    """
    doc = call(mcp, "rcsb_query_sequence", {"sequence": SEQ})
    out = call(mcp, "rcsb_search_request", {"query": doc})
    assert out["result_type"] == "polymer_entity"
    assert out["fetch_with"] == "rcsb_get_polymer_entities"

    converted = call(mcp, "rcsb_search_request", {"query": doc, "return_type": "entry"})
    assert converted["result_type"] == "entry"
    assert converted["fetch_with"] == "rcsb_get_entries"


def test_every_return_type_names_a_real_fetch_tool(mcp):
    """The mapping crosses modules by string, so a rename must fail here, not in the wild."""
    from rcsb_mcp import server
    from rcsb_mcp.search import RETURN_TYPE_FETCH_TOOL, ReturnType
    from typing import get_args

    registered = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert set(RETURN_TYPE_FETCH_TOOL) == set(get_args(ReturnType)), (
        "every return_type an agent can ask for needs a fetch tool named for it"
    )
    missing = set(RETURN_TYPE_FETCH_TOOL.values()) - registered
    assert not missing, f"response points at tools that do not exist: {sorted(missing)}"


def test_facet_responses_carry_no_fetch_pointer(mcp, monkeypatch):
    """A facet response has no identifiers, so there is nothing to fetch."""
    async def fake_post(body):
        return {"total_count": 3, "facets": [{"name": "m", "buckets": []}]}

    monkeypatch.setattr(search, "_post_search", fake_post)
    server = FastMCP("test")
    search.register_search_tools(server)
    doc = call(server, "rcsb_query_attribute", {"attributes": [HUMAN]})
    out = call(server, "rcsb_search_request", {"query": doc, "facets": [
        {"name": "m", "aggregation_type": "terms", "attribute": "exptl.method"}]})
    assert "fetch_with" not in out and "result_type" not in out


def test_attributes_are_only_on_the_attribute_tool(mcp):
    """The other half of the saving: AttributeFilter is defined once, not seven times."""
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    carriers = [n for n, t in tools.items()
                if "attributes" in t.inputSchema.get("properties", {})]
    assert carriers == ["rcsb_query_attribute"]
