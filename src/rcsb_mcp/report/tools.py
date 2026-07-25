"""MCP tool registration for the report renderer.

Import ``register_report_tools(mcp)`` from your server module, or copy the
decorated function into wherever your existing ``rcsb_*`` tools are defined.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import enrich, link
from .models import ReportRequest
from .render import TEMPLATE_VERSION, render_report
from .store import REPORT_STORE

__all__ = ["RenderReportInput", "RenderReportResult", "register_report_tools"]

# Public origin that serves the report render endpoint (GET /r?d=...). Set it in the
# deployment (e.g. https://rcsb-mcp.rcsb.org) and the tool hands back a link instead of
# the markup, so the agent never has to reproduce the document. It MUST default to empty
# (not localhost): unset then means REPORT_BASE_URL is None and the tool falls back to
# `html` — the safe behavior for stdio dev and any deployment that hasn't set a real,
# remote-reachable origin. A non-empty default would emit dead http://localhost links to
# remote users. The dev server sets this explicitly (scripts/dev-server.sh).
_BASE_ENV = os.environ.get("RCSB_MCP_REPORT_BASE_URL", "").strip()
REPORT_BASE_URL = _BASE_ENV.rstrip("/") or None

# Above this the packed link is too long to be a safe URL (browsers and the ingress
# cap the request line), so we fall back to returning `html`. Compressed reports are
# ~1 KB even at 50 rows, so only a pathological report ever trips this.
MAX_URL_BYTES = 8_000


class RenderReportInput(BaseModel):
    """Input for rcsb_render_report."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    report: ReportRequest = Field(..., description="Structured description of the report content.")


class RenderReportResult(BaseModel):
    """Structured result of rcsb_render_report.

    Returns EITHER ``url`` or ``html``, never both. ``url`` is a short link to the
    rendered report; opening it redirects to a self-contained URL that renders the
    report on demand, so the page the user lands on needs nothing stored server-side.
    It is the deliverable: hand it to the user, do not fetch or reproduce it.
    ``html`` is the fallback for when no render endpoint is reachable (or the report
    is too large to pack into a URL).
    """

    url: str | None = Field(
        default=None,
        description=(
            "Short link to the rendered report. When set, THIS is the deliverable — "
            "give it to the user as a clickable link. Do not open it, fetch it, or reproduce "
            "anything from it."
        ),
    )
    html: str | None = Field(
        default=None,
        description=(
            "Fallback rendering, returned ONLY when a link could not be built. Write it verbatim "
            "to a `.html` file and deliver that."
        ),
    )
    template_version: str = Field(..., description="Version of the report template used.")


def _report_link_mode() -> str:
    """One-line description of what rcsb_render_report will actually hand back.

    Which of the three modes is active depends on env read at import, so it is
    invisible until a report is rendered. Logging it at startup turns "why did I
    get html / a long URL / a dead /r/<id>?" into something you can read off the
    server's first lines instead of bisecting the config.
    """
    if REPORT_BASE_URL is None:
        return "OFF — returning html (set RCSB_MCP_REPORT_BASE_URL to emit links)"
    if not REPORT_STORE.shared:
        return "LONG /r?d= — self-contained (set RCSB_MCP_REPORT_SHARED_STORE=true, single process only, or RCSB_MCP_REDIS_URL, for short links)"
    return "SHORT /r/<id> — resolvable ONLY by a process sharing this store"


def register_report_tools(mcp: Any, entry_fetcher: enrich.EntryFetcher | None = None) -> None:
    """Attach the report tools to a FastMCP server instance.

    ``entry_fetcher`` is injected by the server (it owns the HTTP client) so the
    report package keeps no network dependency of its own and stays testable
    offline. Left None, the tool renders exactly what the agent supplied.
    """
    logging.getLogger(__name__).warning(
        "rcsb-mcp report links: %s | base_url=%s | store=%s(shared=%s)",
        _report_link_mode(),
        REPORT_BASE_URL or "<unset>",
        type(REPORT_STORE).__name__,
        REPORT_STORE.shared,
    )

    @mcp.tool(
        name="rcsb_render_report",
        annotations={
            "title": "Render a PDB search report",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            # True since the tool fills Title/Organism/Method/Resolution from the
            # Data API: it now reaches an external service like every other rcsb_* tool.
            "openWorldHint": True,
        },
    )
    async def rcsb_render_report(params: RenderReportInput) -> RenderReportResult:
        """Render a structure-search report as a styled, self-contained HTML page.

        Call this LAST, after the searches and rcsb_get_* calls that produce the
        values shown in the report. Supply facts only: the page is rendered from a
        fixed server-side template, so do not write HTML yourself and do not
        rewrite what this tool returns.

        Key fields of ``report``:
            title: page heading describing the search.
            api_calls: one per Search/Data/Sequence-Coordinates call, using the
                ``editor`` object the tool returned VERBATIM. Resolver and
                discovery tools have no editor link — pass label and tool_name only.
            result_type: what your ids ARE — "entry" for PDB entry ids (4HHB, the
                default) or "ligand" for chemical component ids (ATP). It must match
                the ids you send: a mismatch resolves nothing, and every derived
                value comes back empty.
            results: the identifiers you are reporting, in the order you want them
                ranked, each ``{"id": ..., "evidence": [...]}``.
            data_usage: ordered narrative of how each call shaped the final set;
                each item's body is a list of provenance-tagged fragments
                ``{"text": ..., "model_supplied": bool}`` — model_supplied true for
                your own inference, false for tool-returned values.

        Returns:
            RenderReportResult with EITHER a `url` or `html` (never both), plus
            template_version. Prefer `url` — it is a self-contained
            link that renders the report on demand; deliver it to the user as-is.
            `html` is only returned as a fallback; write it to a `.html` file. See
            the output instructions in the pdb_assistant prompt.
        """
        # Resolve the agent's identifiers into the full table BEFORE packing, so the
        # link carries every value and /r renders with no network call (see
        # report/enrich.py). Best-effort: fill problems degrade cells to "NA".
        document = await enrich.build_document(params.report, entry_fetcher)
        report_json = document.model_dump_json(exclude_defaults=True)

        # Render up front: it is cheap, it surfaces a malformed report to the caller
        # (rather than emitting a link that only fails later at the endpoint), and it
        # is the fallback body. We WITHHOLD it only when we hand back a link instead.
        html: str | None = render_report(document)

        url: str | None = None
        # Gate on the DECOMPRESSED byte length (what the /r endpoint bounds), not the
        # str length — a multibyte report has more bytes than characters.
        if REPORT_BASE_URL is not None and len(report_json.encode("utf-8")) <= link.MAX_DECOMPRESSED:
            # The redirect target — and the fat-URL fallback — is /r?d=<token>. Gate on
            # ITS length (not the short link's): browsers/ingress cap the request line.
            # Both gates match the /r endpoint's accept criteria, so we never hand back a
            # link it would reject.
            token = link.encode_report(report_json)
            fat_url = f"{REPORT_BASE_URL}/r?d={token}"
            if len(fat_url) <= MAX_URL_BYTES:
                # Mint the short /r/<id> link (cheap for the model to emit) ONLY against a
                # store shared across replicas — else the id would 410 on another pod. A
                # process-local store, or a shared write that fails, yields the fat URL,
                # which needs no store and always renders. Offload the (possibly blocking,
                # e.g. Redis-socket) write so it can't stall the event loop.
                url_id = await asyncio.to_thread(REPORT_STORE.put, token) if REPORT_STORE.shared else None
                url = f"{REPORT_BASE_URL}/r/{url_id}" if url_id else fat_url
                html = None  # the link renders the document on demand instead

        return RenderReportResult(
            url=url,
            html=html,
            template_version=TEMPLATE_VERSION,
        )
