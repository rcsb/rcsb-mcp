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

from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import PlainTextResponse

# GraphQL execution lives in rcsb_mcp.graphql (the shared layer above client, which imports
# nothing back from here); _fetch_report_rows below resolves _graphql_field by bare name.
from rcsb_mcp.graphql import _graphql_field  # noqa: E402

# RcsbFastMCP subclasses FastMCP to allow dispatch-only (unlisted) tools; imported up here
# because the server instance below is built from it. tooling imports nothing back.
from rcsb_mcp.tooling import RcsbFastMCP  # noqa: E402


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
# Prompt text, shipped as package data under prompts/ so it stays editable without
# touching code and ships with the wheel.
#
# Nothing here is load-bearing any more. Guidance a tool NEEDS lives on that tool's
# description, which always arrives via tools/list; a prompt arrives only if the client
# asks for it, and `instructions` may be injected whole, truncated (Claude Code cuts at
# 2048 chars) or dropped entirely (Claude web) with no way for the server to tell which.
# Every arrangement that put shared rules in one of those channels and pointed at it from
# tool descriptions produced the same failure: a promise this server could not keep.
#
# What is left here is genuinely optional — a search/report POLICY a user opts into, not
# facts a tool call depends on.
# --------------------------------------------------------------------------- #
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")



mcp = RcsbFastMCP(
    name="rcsb_mcp",
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
from rcsb_mcp.tooling import compact_tool_schemas


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

# LAST, once every tool is registered: drop the pydantic-generated schema keywords
# that cost tokens in every request and say nothing (see tooling.SCHEMA_NOISE).
compact_tool_schemas(mcp)


# --------------------------------------------------------------------------- #
# Server prompt: rcsb_search_assistant — the opt-in search/report policy.
#
# There was a second prompt, rcsb_mcp_guide, holding the shared tool-routing guidance
# that tool descriptions pointed at ("see the ... note in the rcsb_mcp_guide prompt").
# That arrangement is gone: a prompt is delivered only if the CLIENT asks for it, so a
# description pointing at one is a promise this server cannot keep -- the same failure
# as the `instructions` channel it replaced. Every rule those pointers targeted now
# lives on a tool description, which always arrives via tools/list:
#   faceting, grouping, return types, paging  -> rcsb_search_request
#   `fields=` verification rules              -> rcsb_describe_data_object / _seqcoord_
#   resolver attribute paths + lineage rules  -> each rcsb_find_* tool
# prompts/rcsb_mcp_guide.md is kept on disk, unserved, as a source to rescue prose from.
# --------------------------------------------------------------------------- #

@mcp.prompt(
    name="rcsb_search_assistant",
    title="RCSB PDB search assistant",
    description="The opt-in policy for a PDB search session: how thoroughly to search, how "
    "to judge and attribute hits, and when to render a report. Tool routing is NOT here — "
    "each tool's own description carries what it needs, so this prompt is optional.",
)
def rcsb_search_assistant() -> str:
    """The search requirements and report policy, on its own.

    It used to be the tool-routing guide followed by this policy, because the policy leaned
    on the guide for attribute paths and the tool descriptions cross-referenced it. Both
    dependencies are gone — the paths moved onto the rcsb_find_* and rcsb_query_* tools —
    so this returns the policy alone rather than a composition, and a client that never
    loads it still gets a correctly-routed session.
    """
    return _load_prompt("rcsb_search_assistant.md")


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
