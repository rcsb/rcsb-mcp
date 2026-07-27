"""Deterministic HTML rendering for rcsb-mcp search reports.

The whole point of this module: given the same ReportRequest, produce
byte-identical HTML apart from the timestamp. The agent never emits markup.
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from .models import Cell, ColumnKind, EditorLink, Evidence, ReportDocument

__all__ = ["TEMPLATE_VERSION", "render_report"]

# Bump on any template change so rendered reports stay traceable.
TEMPLATE_VERSION = "1.4.0"

RCSB_STRUCTURE_URL = "https://www.rcsb.org/structure/{}"
RCSB_LIGAND_URL = "https://www.rcsb.org/ligand/{}"
UNIPROT_URL = "https://www.uniprot.org/uniprotkb/{}"


# --------------------------------------------------------------------------
# Template helpers
# --------------------------------------------------------------------------


def _render_evidence(ev: Evidence) -> Markup:
    """Render an Evidence cell: tool-sourced ``grounds`` then, if present, the
    assistant's ``interpretation`` in the provenance colour.

    This is the ONLY place the two-colour, provenance-aware text survives — the
    split is a schema boundary, so the interpretation half can never be emitted
    as tool-coloured text.
    """
    grounds = escape(ev.grounds)
    if ev.interpretation:
        return Markup(f'{grounds} <span class="non-tool-source">{escape(ev.interpretation)}</span>')
    return Markup(str(grounds))


def _render_cell(value: Cell, kind: str) -> Markup:
    """Render one table cell according to its column kind."""
    if isinstance(value, Evidence):
        return _render_evidence(value)

    if value is None or (isinstance(value, str) and not value.strip()):
        return Markup("NA")

    if kind == ColumnKind.PDB_ID.value:
        vid = escape(str(value))
        return Markup(f'<a href="{RCSB_STRUCTURE_URL.format(vid)}" target="_blank" rel="noopener">{vid}</a>')

    if kind == ColumnKind.LIGAND_ID.value:
        vid = escape(str(value))
        return Markup(f'<a href="{RCSB_LIGAND_URL.format(vid)}" target="_blank" rel="noopener">{vid}</a>')

    if kind == ColumnKind.UNIPROT.value:
        vid = escape(str(value))
        return Markup(f'<a href="{UNIPROT_URL.format(vid)}" target="_blank" rel="noopener">{vid}</a>')

    if kind == ColumnKind.ORGANISM.value:
        return Markup(f"<i>{escape(str(value))}</i>")

    return Markup(str(escape(str(value))))


def _to_json(value: Any) -> str:
    """Compact JSON for showing search condition values."""
    if isinstance(value, str):
        return value
    return json.dumps(value, separators=(", ", ": "))


def _editor_href(editor: EditorLink) -> str:
    """Rebuild the percent-encoded editor URL from an un-encoded EditorLink.

    Byte-for-byte identical to the URL the tool used to embed directly: each
    param value is compact-JSON-encoded unless it is already a string, then
    percent-encoded with no safe characters. Autoescape turns the raw ``&``
    between params into ``&amp;`` in the rendered href, as before.

    ``None``-valued params are dropped (mirroring the tools, which only emit a
    param when it is present), and empty params yield the bare base URL with no
    dangling ``?`` -- both only reachable if an agent hand-builds the object
    rather than copying the tool's ``editor`` verbatim.
    """
    parts = [
        f"{key}=" + urllib.parse.quote(
            value if isinstance(value, str) else json.dumps(value, separators=(",", ":")),
            safe="",
        )
        for key, value in editor.params.items()
        if value is not None
    ]
    return editor.url + ("?" + "&".join(parts) if parts else "")


def _build_env() -> Environment:
    env = Environment(
        loader=PackageLoader("rcsb_mcp.report", "templates"),
        autoescape=select_autoescape(default_for_string=True, default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["to_json"] = _to_json
    return env


_ENV = _build_env()


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def render_report(doc: ReportDocument, *, generated_at: datetime | None = None) -> str:
    """Render a resolved ReportDocument to a complete, self-contained HTML page."""
    stamp = generated_at or datetime.now(timezone.utc)

    return _ENV.get_template("report.html.j2").render(
        req=doc,
        cell=_render_cell,
        editor_href=_editor_href,
        template_version=TEMPLATE_VERSION,
        generated_at=stamp.strftime("%Y-%m-%d %H:%M UTC"),
    )
