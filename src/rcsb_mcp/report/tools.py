"""MCP tool registration for the report renderer.

Import ``register_report_tools(mcp)`` from your server module, or copy the
decorated function into wherever your existing ``rcsb_*`` tools are defined.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ReportRequest
from .render import TEMPLATE_VERSION, render_report

__all__ = ["RenderReportInput", "RenderReportResult", "register_report_tools"]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 60) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:max_len] or "report"


class RenderReportInput(BaseModel):
    """Input for rcsb_render_report."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    report: ReportRequest = Field(..., description="Structured description of the report content.")


class RenderReportResult(BaseModel):
    """Structured result of rcsb_render_report."""

    html: str | None = Field(default=None, description="The rendered document.")
    sha256: str = Field(..., description="Digest of the rendered document, for reproducibility checks.")
    row_count: int = Field(..., description="Number of result rows rendered.")
    template_version: str = Field(..., description="Version of the report template used.")
    bytes: int = Field(..., description="Size of the rendered document.")


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
            columns: the table schema; add, drop or reorder these per query. Set
                ``kind`` to "pdb_id" / "ligand_id" / "uniprot" to get links,
                "organism" for italics, "numeric" for right alignment.
            rows: one dict per result keyed by column key. A cell may be a plain
                value, or a list of fragments for mixed provenance. Missing or null
                values render as "NA".
            data_usage: ordered narrative of how each call shaped the final set.
            collection: controls the trailing Advanced Search link; IDs are taken
                from the pdb_id/ligand_id column unless you set them explicitly.

        Returns:
            RenderReportResult with the html, plus sha256,
            row_count, bytes and template_version.
        """
        html = render_report(params.report)
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()

        return RenderReportResult(
            html=html,
            sha256=digest,
            row_count=len(params.report.rows),
            template_version=TEMPLATE_VERSION,
            bytes=len(html.encode("utf-8")),
        )
