"""MCP tool registration for the report renderer.

Import ``register_report_tools(mcp)`` from your server module, or copy the
decorated function into wherever your existing ``rcsb_*`` tools are defined.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import ReportRequest
from .render import TEMPLATE_VERSION, render_report

__all__ = ["RenderReportInput", "RenderReportResult", "register_report_tools"]


class RenderReportInput(BaseModel):
    """Input for rcsb_render_report."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    report: ReportRequest = Field(..., description="Structured description of the report content.")


class RenderReportResult(BaseModel):
    """Structured result of rcsb_render_report.

    The server is stateless: it renders and returns, storing nothing (any pod can
    serve any request behind the load balancer). ``html`` is the whole document.

    The client owns what happens next, and should lift ``html`` out of the result
    to build the file/download rather than have the model reproduce it. FastMCP
    emits every result twice -- once as a ``content[].text`` block and again as
    ``structuredContent`` -- so a client that keeps this result in the model's
    context must strip ``html`` from BOTH copies, or the document is paid for twice
    on this turn and again on every later turn it stays in history.
    """

    html: str = Field(..., description="The rendered, self-contained HTML document.")
    sha256: str = Field(..., description="Digest of the rendered document, for reproducibility checks.")
    row_count: int = Field(..., description="Number of result rows rendered.")
    template_version: str = Field(..., description="Version of the report template used.")
    bytes: int = Field(..., description="Size of the rendered document, in UTF-8 bytes.")


def register_report_tools(mcp: Any) -> None:
    """Attach the report tools to a FastMCP server instance."""

    @mcp.tool(
        name="rcsb_render_report",
        annotations={
            "title": "Render a PDB search report",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
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
            query: the service, conditions, total_count and any post-filters.
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
            collection: controls the trailing Advanced Search link; IDs are taken
                from the pdb_id/ligand_id column unless you set them explicitly.

        Returns:
            RenderReportResult with the rendered ``html`` plus sha256, row_count,
            bytes and template_version. Deliver the report as a file — see the
            output instructions in the pdb_assistant prompt.
        """
        html = render_report(params.report)
        encoded = html.encode("utf-8")

        return RenderReportResult(
            html=html,
            sha256=hashlib.sha256(encoded).hexdigest(),
            row_count=len(params.report.rows),
            template_version=TEMPLATE_VERSION,
            bytes=len(encoded),
        )
