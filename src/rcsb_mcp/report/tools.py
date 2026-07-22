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

# Where rendered reports are written when output_mode includes "file".
# In Docker, mount a volume here so the host can read the output.
REPORT_OUTPUT_DIR = Path(os.environ.get("RCSB_MCP_REPORT_DIR", "/tmp/rcsb-mcp-reports"))

# Optional public base URL for served reports, e.g. "https://internal.example.org/reports".
REPORT_BASE_URL = os.environ.get("RCSB_MCP_REPORT_BASE_URL")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str, max_len: int = 60) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:max_len] or "report"


class RenderReportInput(BaseModel):
    """Input for rcsb_render_report."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    report: ReportRequest = Field(..., description="Structured description of the report content.")
    output_mode: Literal["html", "file", "both"] = Field(
        default="both",
        description=(
            "'html' returns the markup inline (the client must render it); 'file' writes the "
            "document to disk and returns only its path/URL; 'both' does each. Prefer 'file' or "
            "'both' — re-emitting the returned HTML through the model reintroduces the drift this "
            "tool exists to prevent."
        ),
    )
    filename: str | None = Field(
        default=None,
        description="Optional output filename stem. Defaults to a slug of the report title plus a timestamp.",
    )


class RenderReportResult(BaseModel):
    """Structured result of rcsb_render_report."""

    path: str | None = Field(default=None, description="Absolute path of the written file, if any.")
    url: str | None = Field(default=None, description="Public URL of the report, if RCSB_MCP_REPORT_BASE_URL is set.")
    html: str | None = Field(default=None, description="The rendered document, if output_mode included html.")
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
            "readOnlyHint": False,  # writes a file when output_mode includes "file"
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
            RenderReportResult with the file path and/or html, plus sha256,
            row_count, bytes and template_version.
        """
        html = render_report(params.report)
        digest = hashlib.sha256(html.encode("utf-8")).hexdigest()

        path: Path | None = None
        url: str | None = None
        if params.output_mode in ("file", "both"):
            REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            stem = params.filename or (
                f"{_slug(params.report.title)}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
            )
            path = REPORT_OUTPUT_DIR / f"{Path(stem).name}.html"
            path.write_text(html, encoding="utf-8")
            if REPORT_BASE_URL:
                url = f"{REPORT_BASE_URL.rstrip('/')}/{path.name}"

        return RenderReportResult(
            path=str(path) if path else None,
            url=url,
            html=html if params.output_mode in ("html", "both") else None,
            sha256=digest,
            row_count=len(params.report.rows),
            template_version=TEMPLATE_VERSION,
            bytes=len(html.encode("utf-8")),
        )
