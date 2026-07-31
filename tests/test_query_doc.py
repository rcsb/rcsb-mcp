"""Query documents must round-trip, tolerate re-spelling, and reject real alteration.

Two properties carry the design and are the tests to keep if any others are dropped:

* `test_altering_a_value_is_always_caught` -- no semantic change to a query slips
  through. Raw JSON with no digest fails this by construction: a flipped digit in a
  resolution cutoff is still valid JSON and still a valid query, so it executes and
  returns plausible but WRONG results.
* `test_faithful_copies_are_never_rejected` -- key order, whitespace and 2.0-vs-2 must
  not fail. A guard that cries wolf on a correct copy would be worse than none, because
  the agent's only recovery is to rebuild and try again.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp.query_doc import (  # noqa: E402
    DIGEST_CHARS,
    MAX_DEPTH,
    MAX_NODES,
    QueryDocError,
    canonical,
    digest_of,
    sign,
    validate_node,
    verify,
)

TERMINAL = {
    "type": "terminal", "service": "text",
    "parameters": {"attribute": "rcsb_entry_info.resolution_combined",
                   "operator": "less", "value": 2.0},
}
METHOD = {
    "type": "terminal", "service": "text",
    "parameters": {"attribute": "exptl.method", "operator": "exact_match",
                   "value": "X-RAY DIFFRACTION"},
}
GROUP = {"type": "group", "logical_operator": "and", "nodes": [TERMINAL, METHOD]}
# What the composer exists for and the flat tools could not express.
NESTED = {"type": "group", "logical_operator": "and", "nodes": [
    GROUP, {"type": "group", "logical_operator": "or", "nodes": [TERMINAL, METHOD]}]}


# --- round trip ------------------------------------------------------------
@pytest.mark.parametrize("node", [TERMINAL, GROUP, NESTED], ids=["terminal", "group", "nested"])
def test_sign_then_verify_returns_the_node(node):
    assert verify(sign(node)) == node


def test_document_shape_is_query_plus_digest():
    doc = sign(TERMINAL)
    assert set(doc) == {"query", "digest"}
    assert doc["query"] == TERMINAL
    assert len(doc["digest"]) == DIGEST_CHARS
    assert all(c in "0123456789abcdef" for c in doc["digest"])


# --- the two load-bearing properties ---------------------------------------
def test_altering_a_value_is_always_caught():
    """Every mutation of a signed node must be rejected, at any depth."""
    doc = sign(NESTED)
    mutations = [
        ("cutoff nudged", lambda n: _set(n, ["nodes", 0, "nodes", 0, "parameters", "value"], 3.0)),
        ("operator flipped", lambda n: _set(n, ["nodes", 0, "nodes", 0, "parameters", "operator"], "greater")),
        ("attribute swapped", lambda n: _set(n, ["nodes", 0, "nodes", 1, "parameters", "attribute"], "exptl.crystal_grow.pH")),
        ("value transposed", lambda n: _set(n, ["nodes", 1, "nodes", 1, "parameters", "value"], "ELECTRON MICROSCOPY")),
        ("and -> or at the root", lambda n: _set(n, ["logical_operator"], "or")),
        ("nested and -> or", lambda n: _set(n, ["nodes", 0, "logical_operator"], "or")),
        ("a condition dropped", lambda n: n["nodes"][0]["nodes"].pop()),
        ("a condition duplicated", lambda n: n["nodes"][0]["nodes"].append(dict(METHOD))),
        ("negation added", lambda n: _set(n, ["nodes", 0, "nodes", 0, "parameters", "negation"], True)),
        ("sibling order swapped", lambda n: n["nodes"][0]["nodes"].reverse()),
    ]
    for label, mutate in mutations:
        node = json.loads(json.dumps(NESTED))
        mutate(node)
        assert node != NESTED, f"test bug: {label!r} did not change the node"
        with pytest.raises(QueryDocError, match="modified after it was built"):
            verify({"query": node, "digest": doc["digest"]})


def test_faithful_copies_are_never_rejected():
    """Re-spelling that the Search API cannot observe must still verify."""
    doc = sign(GROUP)
    same_meaning = [
        ("key order", json.loads(json.dumps(GROUP))),
        ("reordered keys", {"nodes": GROUP["nodes"], "logical_operator": "and", "type": "group"}),
        ("2.0 written as 2", _with(GROUP, ["nodes", 0, "parameters", "value"], 2)),
    ]
    for label, node in same_meaning:
        assert verify({"query": node, "digest": doc["digest"]}) == node, label


def test_digest_survives_a_json_round_trip():
    """The document crosses the wire as JSON; the digest must survive that."""
    doc = json.loads(json.dumps(sign(NESTED)))
    assert verify(doc) == NESTED


def test_random_digit_flips_in_the_digest_are_caught():
    doc = sign(GROUP)
    random.seed(3)
    for _ in range(500):
        i = random.randrange(DIGEST_CHARS)
        c = random.choice([x for x in "0123456789abcdef" if x != doc["digest"][i]])
        bad = doc["digest"][:i] + c + doc["digest"][i + 1:]
        with pytest.raises(QueryDocError, match="modified after it was built"):
            verify({"query": GROUP, "digest": bad})


def test_a_model_cannot_reuse_a_digest_across_queries():
    """The one thing that would silently defeat the guard: a stale digest that fits."""
    a, b = sign(TERMINAL), sign(METHOD)
    assert a["digest"] != b["digest"]
    with pytest.raises(QueryDocError, match="modified after it was built"):
        verify({"query": TERMINAL, "digest": b["digest"]})


# --- malformed documents ---------------------------------------------------
@pytest.mark.parametrize(
    "doc, needle",
    [
        (None, "expected a query document"),
        ("q1:abc", "expected a query document"),
        ({"query": TERMINAL}, "missing digest"),
        ({"digest": "0" * DIGEST_CHARS}, "missing query"),
        ({}, "missing query, digest"),
        ({"query": TERMINAL, "digest": 12345}, "digest must be a string"),
    ],
)
def test_rejects_malformed_documents(doc, needle):
    with pytest.raises(QueryDocError, match=needle):
        verify(doc)


# --- structural validation -------------------------------------------------
@pytest.mark.parametrize(
    "node, needle",
    [
        ("terminal", "must be an object"),
        ({}, "needs type"),
        ({"type": "request"}, "needs type"),
        ({"type": "terminal"}, "missing `service`"),
        ({"type": "terminal", "service": "text"}, "object `parameters`"),
        ({"type": "terminal", "service": "text", "parameters": []}, "object `parameters`"),
        ({"type": "group", "nodes": [TERMINAL]}, "logical_operator"),
        ({"type": "group", "logical_operator": "xor", "nodes": [TERMINAL]}, "logical_operator"),
        ({"type": "group", "logical_operator": "and"}, "non-empty `nodes`"),
        ({"type": "group", "logical_operator": "and", "nodes": []}, "non-empty `nodes`"),
    ],
)
def test_validate_node_rejects_malformed_nodes(node, needle):
    with pytest.raises(QueryDocError, match=needle):
        validate_node(node)


def test_a_whole_search_body_is_rejected_and_says_where_config_goes():
    """A likely agent slip: handing the request body back as the query."""
    body = {"type": "terminal", "service": "text", "parameters": {},
            "return_type": "entry", "request_options": {}}
    with pytest.raises(QueryDocError, match="rcsb_search_request"):
        validate_node(body)


def test_depth_is_bounded():
    node = dict(TERMINAL)
    for _ in range(MAX_DEPTH):
        node = {"type": "group", "logical_operator": "and", "nodes": [node]}
    with pytest.raises(QueryDocError, match="nests more than"):
        validate_node(node)


def test_depth_just_inside_the_limit_is_accepted():
    node = dict(TERMINAL)
    for _ in range(MAX_DEPTH - 1):
        node = {"type": "group", "logical_operator": "and", "nodes": [node]}
    validate_node(node)  # must not raise


def test_node_count_is_bounded():
    wide = {"type": "group", "logical_operator": "or",
            "nodes": [dict(TERMINAL) for _ in range(MAX_NODES)]}
    with pytest.raises(QueryDocError, match="more than"):
        validate_node(wide)


def test_node_budget_counts_the_whole_tree_not_one_level():
    """A wide-and-shallow tree and a deep-and-narrow one share the same budget."""
    half = MAX_NODES // 2
    two_groups = {"type": "group", "logical_operator": "and", "nodes": [
        {"type": "group", "logical_operator": "or", "nodes": [dict(TERMINAL) for _ in range(half)]},
        {"type": "group", "logical_operator": "or", "nodes": [dict(TERMINAL) for _ in range(half)]},
    ]}
    with pytest.raises(QueryDocError, match="more than"):
        validate_node(two_groups)


def test_sign_refuses_to_certify_a_malformed_node():
    """A digest over rubbish would launder it; signing validates first."""
    with pytest.raises(QueryDocError, match="needs type"):
        sign({"nodes": []})


# --- canonical form --------------------------------------------------------
def test_canonical_form_is_stable_and_compact():
    assert canonical(TERMINAL) == canonical(json.loads(json.dumps(TERMINAL)))
    assert " " not in canonical(TERMINAL).replace("X-RAY DIFFRACTION", "")


def test_canonical_keeps_booleans_out_of_the_integer_normalisation():
    """bool is an int in Python; True must not canonicalise as 1."""
    a = {"type": "terminal", "service": "text",
         "parameters": {"attribute": "a", "operator": "exact_match", "negation": True}}
    b = {"type": "terminal", "service": "text",
         "parameters": {"attribute": "a", "operator": "exact_match", "negation": 1}}
    assert digest_of(a) != digest_of(b)


def test_canonical_keeps_non_ascii_values_intact():
    node = {"type": "terminal", "service": "text",
            "parameters": {"attribute": "struct.title", "operator": "contains_phrase",
                           "value": "β-lactamase"}}
    assert "β-lactamase" in canonical(node)
    assert verify(sign(node)) == node


# --- helpers ---------------------------------------------------------------
def _set(node, path, value):
    cur = node
    for key in path[:-1]:
        cur = cur[key]
    cur[path[-1]] = value


def _with(node, path, value):
    copy = json.loads(json.dumps(node))
    _set(copy, path, value)
    return copy
