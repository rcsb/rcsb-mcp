"""An MCP server for interrogating Protein Data Bank structures.

Spans three RCSB APIs so an LLM can take a question from discovery through detail:
- DISCOVER: search the Protein Data Bank (https://search.rcsb.org) by keyword,
  structural attribute, sequence, chemistry, 3D shape, or motif.
- INSPECT: fetch entry / entity / assembly / ligand metadata and annotations from
  the Data API (https://data.rcsb.org/graphql).
- RELATE: map alignments and positional annotations between sequence reference
  systems (UniProt, NCBI, PDB entity/instance) via the Sequence Coordinates API
  (https://sequence-coordinates.rcsb.org/graphql).

The Search API returns only identifiers, so a search is the first step: batch the
returned ids into the matching Data API tool for metadata, and an entry's component
ids let the agent drill top-down into its entities, assemblies, and ligands.

Run locally (stdio, for Claude Desktop / MCP Inspector):
    python -m rcsb_mcp.server
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

# GraphQL execution lives in rcsb_mcp.graphql (the shared layer above client, which imports
# nothing back from here); _fetch_report_rows below resolves _graphql_field by bare name.
from rcsb_mcp.graphql import _graphql_field  # noqa: E402


# --------------------------------------------------------------------------- #
# HTTP transport security (DNS-rebinding Host/Origin validation)
# --------------------------------------------------------------------------- #
def _transport_security() -> TransportSecuritySettings:
    """Host/Origin validation policy for the streamable-HTTP deployment.

    FastMCP auto-enables DNS-rebinding protection when `host` is a loopback address
    (its default) and no explicit policy is given, allow-listing only
    127.0.0.1/localhost. Behind an ingress that forwards the real Host header
    (e.g. rcsb-mcp.k8s.rcsb.org), that host then fails validation and every
    POST /mcp is rejected with 421 "Invalid Host header" — so no client can connect.

    This server is a public, TLS-terminated, read-only proxy meant to be added to
    arbitrary MCP clients (including browser-hosted agents whose Origin can't be
    enumerated), so validation is DISABLED by default. Set RCSB_MCP_ALLOWED_HOSTS
    (comma-separated) to lock it down to known hosts instead — note that enabling it
    also turns on Origin validation, which rejects browser clients unless their
    origins are listed in RCSB_MCP_ALLOWED_ORIGINS.
    """
    hosts = [h.strip() for h in os.getenv("RCSB_MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    origins = [o.strip() for o in os.getenv("RCSB_MCP_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


# --------------------------------------------------------------------------- #
# Prompt / guidance text, shipped as package data under prompts/ so it stays
# editable without touching code and ships with the wheel.
#
# rcsb_mcp_guide.md is the SINGLE SOURCE for the always-on tool-routing guidance:
# it is passed to FastMCP(instructions=...) AND exposed as the `rcsb_mcp_guide`
# prompt. The duplication matters because `instructions` only reaches the model if
# the CLIENT chooses to inject it -- several (Claude web among them) do not, which
# leaves the ~45 "see the server instructions" cross-references in the tool
# descriptions pointing at text the agent never received. The prompt is the
# client-agnostic fallback: any MCP client can list and invoke it.
# --------------------------------------------------------------------------- #
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


_MCP_GUIDE = _load_prompt("rcsb_mcp_guide.md")


mcp = FastMCP(
    name="rcsb_mcp",
    instructions=_MCP_GUIDE,
    # HTTP deployment runs 2-6 load-balanced replicas with no session affinity, so
    # run stateless (any pod can serve any request — no per-session state to lose)
    # and answer with plain JSON instead of long-lived SSE streams. Both flags are
    # ignored by the stdio transport (local/console use).
    stateless_http=True,
    json_response=True,
    # Accept the real Host header seen behind the ingress (see _transport_security).
    transport_security=_transport_security(),
)

from rcsb_mcp.data import register_data_tools
from rcsb_mcp.report.routes import register_report_routes
from rcsb_mcp.report.tools import register_report_tools
from rcsb_mcp.resolvers import register_resolver_tools
from rcsb_mcp.search import register_search_tools
from rcsb_mcp.seqcoord import register_seqcoord_tools


async def _fetch_report_rows(query: str, root_field: str, ids: list[str]) -> list[dict[str, Any]]:
    """Fetch a report table spec's derivable cells for `ids` in one round trip.

    Generic over the spec (report/tables.py supplies the query and root field), so
    adding a result type needs no change here. Injected into the report tool (via
    register_report_tools) so the report package stays HTTP-free — the concrete
    GraphQL-backed fetcher lives here at the composition root, using `_graphql_field`
    imported from rcsb_mcp.graphql (the shared layer, which imports nothing back).
    """
    nodes = await _graphql_field({"query": query, "variables": {"ids": ids}}, root_field)
    if nodes is None:
        # A 200 whose JSON carries neither `data.entries` nor `errors` (a WAF/CDN block
        # page, a maintenance body, a field rename) must NOT look like "resolved, no such
        # entries" — that would blank every cell in the table. Raise so the caller treats
        # it as a failed chunk and keeps what the agent supplied.
        raise RuntimeError(f"Data API returned no `{root_field}` field")
    return nodes


register_report_tools(mcp, entry_fetcher=_fetch_report_rows)
register_report_routes(mcp)
register_resolver_tools(mcp)
register_search_tools(mcp)
register_seqcoord_tools(mcp)
register_data_tools(mcp)


# --------------------------------------------------------------------------- #
# Server prompts. Two, with different jobs:
#
# * rcsb_search_assistant — the guide FOLLOWED BY the opt-in search/report policy,
#   so one invocation leaves the agent fully briefed. The policy alone is NOT
#   enough: its own rules lean on the guide (resolve a concept with an rcsb_find_*
#   resolver, then search "that annotation" — the attribute paths live only in the
#   guide), and so do the ~45 "see the server instructions" cross-references in the
#   tool descriptions.
# * rcsb_mcp_guide — the `instructions` text alone, for clients that never inject
#   it and sessions that want the routing guidance without the report policy.
#
# Both read package data under prompts/, the single source of truth, so they ship
# with the wheel and stay editable without touching code. The assistant prompt
# COMPOSES the guide at call time from _MCP_GUIDE rather than embedding a copy, so
# the three channels (instructions, guide prompt, assistant prompt) cannot drift.
# --------------------------------------------------------------------------- #

@mcp.prompt(
    name="rcsb_search_assistant",
    title="RCSB PDB search assistant",
    description="Everything needed for a PDB search session: the full tool-routing guide "
    "(search-tool choice, return types, paging, faceting, grouping, ontology resolvers, "
    "field selection) followed by the search/report policy. Invoke this one prompt rather "
    "than pairing it with rcsb_mcp_guide.",
)
def rcsb_search_assistant() -> str:
    """The tool-routing guide, followed by the search requirements and report policy.

    The guide leads. It already opens with the identity and capability summary ("You are
    an assistant for interrogating Protein Data Bank structures ... DISCOVER / INSPECT /
    RELATE"), so the policy half carries no persona preamble of its own — one statement of
    what the assistant is, not two competing ones. Order also puts the routing guidance in
    the position `instructions` would have occupied, which is what the tool descriptions
    were written against.

    Joined with nothing but a blank line: the guide's own `## Server Instructions` heading
    is what the ~45 "see the server instructions" cross-references resolve against, and it
    labels the text in place, so no connecting prose is needed at the seam. That heading
    also reaches the `instructions` channel, which no wording added here ever could.
    """
    policy = _load_prompt("rcsb_search_assistant.md").rstrip("\n")
    return _MCP_GUIDE.rstrip("\n") + "\n\n" + policy


@mcp.prompt(
    name="rcsb_mcp_guide",
    title="RCSB PDB tool guide",
    description="The always-on guidance for these tools: which search tool to use, return "
    "types, paging, faceting, de-duplication/grouping, the ontology resolvers, and field "
    "selection. Identical to the server `instructions` — load it when your client does not "
    "inject those, otherwise the tool descriptions refer to text you never received. "
    "Already included at the end of rcsb_search_assistant; load only one of the two.",
)
def rcsb_mcp_guide() -> str:
    """The `instructions` block, offered as a loadable prompt.

    Same text, second channel. `instructions` is delivered on `initialize` but the
    SPEC leaves injecting it to the client, and several do not — which silently
    breaks the "see the server instructions" cross-references the tool descriptions
    rely on. A prompt is listable and invocable by any MCP client, so this gives the
    user a way to supply that text by hand when the client will not.
    """
    return _MCP_GUIDE


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request):
    """Liveness/readiness probe endpoint — 200 OK when the HTTP server is up."""
    return PlainTextResponse("ok")


def create_app():
    """ASGI app factory for HTTP deployment (the Docker image).

    Serves the MCP over the streamable-HTTP transport at POST /mcp (plus GET /healthz
    for Kubernetes probes). Built only when called, so importing this module for local
    stdio use (main() / the `rcsb-mcp` console script) constructs nothing.
    Run with: uvicorn rcsb_mcp.server:create_app --factory
    """
    app = mcp.streamable_http_app()
    # Browser-based ("web") agents call POST /mcp with fetch(), which triggers a CORS
    # preflight and requires CORS response headers; FastMCP's app adds none for /mcp,
    # so without this a browser blocks the request before it is ever sent. This is a
    # public, unauthenticated, read-only server, so any origin is allowed. Expose
    # Mcp-Session-Id so a browser client can read the session header when present.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Mcp-Session-Id"],
        max_age=86400,
    )
    return app


def main() -> None:
    mcp.run()  # stdio transport by default (local clients / console script)


if __name__ == "__main__":
    main()
