"""Shared transport for the RCSB HTTP/GraphQL APIs, plus the editor-link builders.

This is the network floor the tools stand on: the endpoint URLs, one place that
turns a non-2xx response into an actionable message, and the three request shapes
(Search POST, GraphQL POST, plain JSON GET) every tool group reuses. Plus the two
``editor`` descriptor builders that a report uses to show the exact query behind a
call.

It deliberately imports NOTHING from :mod:`rcsb_mcp.server` (or any tool module):
the dependency runs one way — tool modules import this, never the reverse — so tool
definitions can move into their own packages without a circular import. Anything
here that is schema- or domain-specific does NOT belong here; keep it to transport.
"""

from __future__ import annotations

from typing import Any

import httpx

# --- Endpoints ------------------------------------------------------------------
SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
DATA_GRAPHQL_URL = "https://data.rcsb.org/graphql"
SEQCOORD_GRAPHQL_URL = "https://sequence-coordinates.rcsb.org/graphql"
# Interactive editors — links surfaced in tool responses so a report can show the
# exact query behind each API call (built server-side for correct URL-encoding).
SEARCH_EDITOR_URL = "https://search.rcsb.org/query-editor.html"
DATA_GRAPHIQL_URL = "https://data.rcsb.org/graphiql/index.html"
SEQCOORD_GRAPHIQL_URL = "https://sequence-coordinates.rcsb.org/graphiql/index.html"

USER_AGENT = "rcsb-mcp/0.1 (https://github.com/rcsb/rcsb-mcp)"
TIMEOUT = httpx.Timeout(30.0)


# --- HTTP ----------------------------------------------------------------------
def _check_response(resp: httpx.Response, service: str) -> None:
    """Raise a clear, actionable error for a non-2xx response.

    Replaces httpx's terse ``raise_for_status``: maps the status codes these
    public APIs actually return to messages that tell the agent what to do next
    (e.g. a 400 from a bad attribute path, a 429 rate limit). Returns silently
    for any 2xx (callers handle 204 before calling this).
    """
    if resp.is_success:
        return
    code = resp.status_code
    if code == 400:
        # The body usually explains the rejection (bad attribute, operator, or
        # value type); surface a trimmed copy plus how to fix a search query.
        detail = " ".join((resp.text or "").split())
        msg = f"{service} rejected the request (HTTP 400)."
        if detail:
            msg += f" Details: {detail[:300]}"
        if "search" in service.lower():
            msg += (" Verify the attribute path and operator with "
                    "rcsb_list_pdb_search_attributes and that the value type matches.")
        raise ValueError(msg)
    if code in (401, 403):
        raise RuntimeError(f"{service} denied the request (HTTP {code}).")
    if code == 404:
        raise RuntimeError(f"{service} resource not found (HTTP 404).")
    if code == 429:
        raise RuntimeError(
            f"{service} rate limit exceeded (HTTP 429). Wait a few seconds and retry."
        )
    if code >= 500:
        raise RuntimeError(f"{service} is unavailable (HTTP {code}); try again shortly.")
    raise RuntimeError(f"{service} request failed (HTTP {code}).")


async def _post_search(body: dict[str, Any]) -> dict[str, Any]:
    """POST a query to the Search API. Returns a normalized result dict."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.post(SEARCH_URL, json=body)
    except httpx.TimeoutException:
        raise RuntimeError("RCSB Search API timed out; try again or narrow the query.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"RCSB Search API connection error ({type(exc).__name__}).") from None
    # The API returns 204 No Content when nothing matches.
    if resp.status_code == 204:
        return {"total_count": 0, "result_set": []}
    _check_response(resp, "RCSB Search API")
    return resp.json()


async def _post_graphql(
    query: str, variables: dict[str, Any] | None = None, url: str = DATA_GRAPHQL_URL
) -> dict[str, Any]:
    """POST a GraphQL query to an RCSB GraphQL endpoint. Returns the raw {data, errors} payload.

    These endpoints reply 200 even for query/validation errors, surfacing them in
    an ``errors`` array, so callers must inspect that rather than HTTP status.
    """
    body = {"query": query, "variables": variables or {}}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            resp = await client.post(url, json=body)
    except httpx.TimeoutException:
        raise RuntimeError("RCSB GraphQL API timed out; try again or simplify the query.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"RCSB GraphQL API connection error ({type(exc).__name__}).") from None
    _check_response(resp, "RCSB GraphQL API")
    return resp.json()


async def _get_json(url: str, params: dict[str, Any], service: str) -> dict[str, Any]:
    """GET a JSON resource (shared headers/timeout) with friendly errors.

    Used by the ontology resolvers (rcsb_find_* tools) that call EBI and UniProt web services.
    Some of these (e.g. EBI InterPro) answer a no-match query with 204 No Content / an empty
    body rather than an empty JSON list; return {} for that so callers see "no results" (and
    emit their fall-back note) instead of a JSONDecodeError.
    """
    try:
        async with httpx.AsyncClient(
            timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        ) as client:
            resp = await client.get(url, params=params)
    except httpx.TimeoutException:
        raise RuntimeError(f"{service} timed out; try again shortly.") from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"{service} connection error ({type(exc).__name__}).") from None
    _check_response(resp, service)
    if resp.status_code == 204 or not resp.content:
        return {}
    return resp.json()


# --- Editor-link descriptors ---------------------------------------------------
def _search_editor(body: dict[str, Any]) -> dict[str, Any]:
    """Editor descriptor opening this Search API query body in the RCSB query editor.

    Carried un-encoded as {url, params}; rcsb_render_report percent-encodes
    params into the actual URL. Halves the token cost of embedding the link.
    """
    return {"url": SEARCH_EDITOR_URL, "params": {"json": body}}


def _graphiql_editor(base: str, body: dict[str, Any]) -> dict[str, Any]:
    """Editor descriptor opening this GraphQL query (+ variables) in a GraphiQL editor.

    Carried un-encoded as {url, params}; params has `query` and, when present,
    `variables`. rcsb_render_report percent-encodes them into the actual URL.
    """
    params: dict[str, Any] = {"query": body["query"]}
    variables = body.get("variables")
    if variables:
        params["variables"] = variables
    return {"url": base, "params": params}
