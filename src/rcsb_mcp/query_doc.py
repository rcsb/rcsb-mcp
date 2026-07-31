"""Query documents: a Search API query node plus a digest that detects tampering.

In the composer design a search is assembled across several tool calls — one or more
``rcsb_query_*`` builders, optionally ``rcsb_query_composer`` to join them, then
``rcsb_search_request`` to execute. The query node therefore travels out through the
model and back in again at every step, which puts copy-verbatim on the critical path
of every search. A mangled node can still be *valid JSON that runs a different query*
and returns plausible results — a wrong answer with no error anywhere.

A query document closes that: builders return ``{"query": <node>, "digest": <12 hex>}``
and every consumer recomputes the digest before using the node. Any semantic change
fails loudly instead of executing quietly.

**Why not an opaque token.** Packing the node into base64 gives the same guarantee, but
base64 tokenizes at ~1.5 chars/token against JSON's ~4, so an opaque handle costs about
2.9x the tokens of the node it replaces (measured across the baseline cases: 138 vs 48
per appearance) — roughly +180 tokens per search, against a refactor that exists to save
tokens. The digest costs ~1.2x. Keeping the node readable also lets the agent explain
and revise the query it is about to run, and preserves the `editor` URL story.

**What the digest is and is not.** It detects accidental alteration — a dropped node, a
transposed value, a truncated copy. It is NOT a signature: it is unkeyed and anyone can
compute one. Its second job is quieter but just as useful: a model cannot compute
blake2b in its head, so it cannot hand-forge a document, which keeps the builders the
only way into a query without making queries opaque. Everything a document carries is
re-validated before it reaches the Search API.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

__all__ = [
    "sign", "verify", "digest_of", "canonical", "validate_node",
    "QueryDocError", "DIGEST_CHARS", "MAX_DEPTH", "MAX_NODES",
]

# 12 hex chars = 48 bits. Against accidental corruption that is a false-accept rate of
# ~1 in 2.8e14; against a forger it is irrelevant, and deliberately so (see module docs).
DIGEST_CHARS = 12

# Bounds on a composed query. The Search API has no published nesting limit, but an
# unbounded composer is a context and latency hazard: each round trip can wrap the
# previous result in another group, so a loop builds an arbitrarily deep tree. These are
# far above any real query -- a hard biological question rarely exceeds three levels.
MAX_DEPTH = 6
MAX_NODES = 64

_NODE_TYPES = {"terminal", "group"}


class QueryDocError(ValueError):
    """A query document is malformed, altered, or not a valid Search query node."""


# --------------------------------------------------------------------------- #
# Canonical form + digest
# --------------------------------------------------------------------------- #
def canonical(node: Any) -> str:
    """Serialise a node so that only SEMANTIC differences change the bytes.

    Three normalisations, each removing a class of false rejection where the model
    reproduced the node faithfully but the transport did not preserve its spelling:

    * ``sort_keys`` — JSON objects are unordered, so key order must not matter.
    * ``separators`` — whitespace must not matter.
    * integral floats -> int — a model that copies ``2.0`` back as ``2`` has changed
      nothing the Search API can observe, and must not be told it corrupted the query.

    ``ensure_ascii=False`` keeps non-ASCII values (organism and ligand names) as
    themselves rather than escapes, so the form is stable and compact either way.
    """
    return json.dumps(
        _normalise(node), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _normalise(value: Any) -> Any:
    if isinstance(value, bool):  # bool before int -- bool IS an int in Python
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def digest_of(node: Any) -> str:
    """The digest of ``node``'s canonical form."""
    return hashlib.blake2b(
        canonical(node).encode("utf-8"), digest_size=DIGEST_CHARS // 2
    ).hexdigest()


# --------------------------------------------------------------------------- #
# Sign / verify
# --------------------------------------------------------------------------- #
def sign(node: dict[str, Any]) -> dict[str, Any]:
    """Wrap a validated query node as the document a query tool returns."""
    validate_node(node)
    return {"query": node, "digest": digest_of(node)}


def verify(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Return the node from a query document, or raise if it was altered.

    Errors here are read by an agent mid-chain, so each one names the recovery: rebuild
    via the tool, do not edit or invent the document.
    """
    if not isinstance(doc, Mapping):
        raise QueryDocError(
            f"expected a query document {{query, digest}} as returned by an rcsb_query_* "
            f"tool, got {_describe(doc)}"
        )
    missing = [k for k in ("query", "digest") if k not in doc]
    if missing:
        raise QueryDocError(
            f"query document is missing {', '.join(missing)}. Pass back the whole object "
            "an rcsb_query_* tool returned, not just part of it."
        )
    node, digest = doc["query"], doc["digest"]
    if not isinstance(digest, str):
        raise QueryDocError(f"digest must be a string, got {_describe(digest)}")

    validate_node(node)
    expected = digest_of(node)
    if digest != expected:
        raise QueryDocError(
            "this query was modified after it was built (digest does not match). The "
            "query and its digest must be passed through together, exactly as returned. "
            "To change the query, call the rcsb_query_* tool again with the new values "
            "rather than editing the document."
        )
    return node


# --------------------------------------------------------------------------- #
# Structural validation against the Search API's query grammar
# --------------------------------------------------------------------------- #
def validate_node(node: Any, *, _depth: int = 1, _budget: list[int] | None = None) -> None:
    """Check that ``node`` is a well-formed Search API query node.

    Structure only: that a group has nodes and an operator, that a terminal names a
    service and parameters, and that the tree stays inside MAX_DEPTH/MAX_NODES. Whether
    an ATTRIBUTE PATH is real is a separate question answered against the catalog by
    search._validate_query_attributes, which has the "did you mean" machinery.
    """
    budget = [MAX_NODES] if _budget is None else _budget
    if _depth > MAX_DEPTH:
        raise QueryDocError(
            f"query nests more than {MAX_DEPTH} levels deep. Flatten it: conditions that "
            "share one AND/OR belong in a single rcsb_query_attribute call."
        )
    budget[0] -= 1
    if budget[0] < 0:
        raise QueryDocError(
            f"query has more than {MAX_NODES} nodes. Narrow it, or use the `in` operator "
            "for a list of alternatives on one attribute instead of many OR'd conditions."
        )

    if not isinstance(node, dict):
        raise QueryDocError(f"query node must be an object, got {_describe(node)}")
    if "request_options" in node or "return_type" in node:
        raise QueryDocError(
            "this is a whole search request, not a query node. Result-shaping parameters "
            "(return_type, limit, sort, facets, grouping) belong on rcsb_search_request."
        )
    kind = node.get("type")
    if kind not in _NODE_TYPES:
        raise QueryDocError(
            f"query node needs type {sorted(_NODE_TYPES)}, got {_describe(node.get('type'))}"
        )

    if kind == "terminal":
        if not node.get("service"):
            raise QueryDocError("terminal node is missing `service`")
        if not isinstance(node.get("parameters"), dict):
            raise QueryDocError(
                f"terminal node needs an object `parameters`, got "
                f"{_describe(node.get('parameters'))}"
            )
        return

    if node.get("logical_operator") not in ("and", "or"):
        raise QueryDocError(
            f'group node needs logical_operator "and" or "or", got '
            f"{_describe(node.get('logical_operator'))}"
        )
    children = node.get("nodes")
    if not isinstance(children, list) or not children:
        raise QueryDocError(
            f"group node needs a non-empty `nodes` list, got {_describe(children)}"
        )
    for child in children:
        validate_node(child, _depth=_depth + 1, _budget=budget)


def _describe(value: Any) -> str:
    """A short, safe rendering of bad input for an error message."""
    if value is None:
        return "nothing"
    if isinstance(value, str):
        return repr(value if len(value) <= 40 else value[:37] + "...")
    if isinstance(value, Mapping):
        keys = sorted(str(k) for k in value)[:5]
        return f"an object with keys {keys}" + ("..." if len(value) > 5 else "")
    if isinstance(value, list):
        return f"a list of {len(value)}"
    return type(value).__name__
