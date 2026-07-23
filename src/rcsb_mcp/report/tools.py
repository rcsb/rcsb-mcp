"""MCP tool registration for the report renderer.

Import ``register_report_tools(mcp)`` from your server module, or copy the
decorated function into wherever your existing ``rcsb_*`` tools are defined.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import link
from .models import ReportRequest
from .render import TEMPLATE_VERSION, render_report

__all__ = ["RenderReportInput", "RenderReportResult", "register_report_tools"]

# Public origin that serves the report render endpoint (GET /r?d=...). Set it in the
# deployment (e.g. https://rcsb-mcp.rcsb.org) and the tool hands back a self-contained
# link instead of the markup, so the agent never has to reproduce the document. Left
# unset -- local stdio dev with no reachable endpoint -- the tool falls back to
# returning `html`, and the client writes the file the old way.
_BASE_ENV = os.environ.get("RCSB_MCP_REPORT_BASE_URL", "http://localhost:8080").strip()
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

    Returns EITHER ``url`` or ``html``, never both. ``url`` is a self-contained link
    that renders the report on demand from the data packed into it — the server
    stores nothing, so any replica serves any link. It is the deliverable: hand it to
    the user, do not fetch or reproduce it. ``html`` is the fallback for when no
    render endpoint is reachable (or the report is too large to pack into a URL).
    """

    url: str | None = Field(
        default=None,
        description=(
            "Self-contained link to the rendered report. When set, THIS is the deliverable — "
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
    row_count: int = Field(..., description="Number of result rows rendered.")
    template_version: str = Field(..., description="Version of the report template used.")


def register_report_tools(mcp: Any) -> None:
    """Attach the report tools to a FastMCP server instance."""

    @mcp.tool(
        name="rcsb_render_report",
        annotations={
            "title": "Render a PDB search report",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def rcsb_render_report(params: RenderReportInput) -> RenderReportResult:
        """Render a structure-search report as a styled, self-contained HTML page.

        Call this LAST, after the searches and rcsb_get_* calls that produce the
        values shown in the report. Supply facts only — the page's layout, CSS,
        section order, provenance colouring, escaping and the final RCSB.org
        Advanced Search link are all produced by a fixed server-side template, so
        every report looks identical. Do not write HTML yourself, and do not
        rewrite what this tool returns.

        Key fields of ``report``:
            title: page heading describing the search.
            summary / interpretation: paragraphs, each a list of provenance-tagged
                fragments ``{"text": ..., "model_supplied": bool}``. Set
                ``model_supplied`` true for your own domain knowledge, inference or
                interpretation; false for values that came from a tool response.
            api_calls: one per Search/Data/Sequence-Coordinates call, using the
                ``query_editor_url`` / ``graphiql_url`` the tool returned VERBATIM.
                Resolver and discovery tools have no editor link — pass label and
                tool_name only.
            columns: the table schema — one entry per column, in display order.
                Set ``kind`` to "pdb_id" / "ligand_id" / "uniprot" to get links,
                "organism" for italics, "numeric" for right alignment.
            rows: one dict per result keyed by column key. A cell may be a plain
                value, or a list of fragments for mixed provenance. Missing or null
                values render as "NA".
            data_usage: ordered narrative of how each call shaped the final set.

        Returns:
            RenderReportResult with EITHER a `url` or `html` (never both), plus
            row_count and template_version. Prefer `url` — it is a self-contained
            link that renders the report on demand; deliver it to the user as-is.
            `html` is only returned as a fallback; write it to a `.html` file. See
            the output instructions in the pdb_assistant prompt.
        """
        report = params.report
        report_json = report.model_dump_json(exclude_defaults=True)

        # Render up front: it is cheap, it surfaces a malformed report to the caller
        # (rather than emitting a link that only fails later at the endpoint), and it
        # is the fallback body. We WITHHOLD it only when we hand back a link instead.
        html: str | None = render_report(report)

        url: str | None = None
        if REPORT_BASE_URL is not None and len(report_json) <= link.MAX_DECOMPRESSED:
            # Both gates must match the /r endpoint's accept criteria so we never emit
            # a link it would reject: it caps the DECOMPRESSED payload (checked above),
            # and browsers/ingress cap the URL length (checked here).
            candidate = f"{REPORT_BASE_URL}/r?d={link.encode_report(report_json)}"
            if len(candidate) <= MAX_URL_BYTES:
                url = candidate
                html = None  # the link renders the document on demand instead

        return RenderReportResult(
            url=url,
            html=html,
            row_count=len(report.rows),
            template_version=TEMPLATE_VERSION,
        )
