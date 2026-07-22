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

from .models import Cell, ColumnKind, Fragment, ReportRequest

__all__ = ["TEMPLATE_VERSION", "render_report", "build_collection_url"]

# Bump on any template change so rendered reports stay traceable.
TEMPLATE_VERSION = "1.0.0"

RCSB_STRUCTURE_URL = "https://www.rcsb.org/structure/{}"
RCSB_LIGAND_URL = "https://www.rcsb.org/ligand/{}"
UNIPROT_URL = "https://www.uniprot.org/uniprotkb/{}"
RCSB_SEARCH_URL = "https://www.rcsb.org/search?request="

_ID_ATTRIBUTE_FOR_RETURN_TYPE = {
    "entry": "rcsb_entry_container_identifiers.entry_id",
    "mol_definition": "rcsb_chem_comp_container_identifiers.comp_id",
    "polymer_entity": "rcsb_polymer_entity_container_identifiers.rcsb_id",
    "assembly": "rcsb_assembly_container_identifiers.rcsb_id",
}


# --------------------------------------------------------------------------
# Collection link
# --------------------------------------------------------------------------


def build_collection_url(
    ids: list[str],
    return_type: str = "entry",
    attribute: str | None = None,
) -> str:
    """Build an RCSB.org Advanced Search URL that opens exactly ``ids``.

    Percent-encoding happens here rather than in the model's head, which is
    where hand-built versions of this URL tend to go wrong.
    """
    if not ids:
        raise ValueError("cannot build a collection URL from an empty id list")

    attr = attribute or _ID_ATTRIBUTE_FOR_RETURN_TYPE.get(return_type)
    if attr is None:
        raise ValueError(
            f"no default search attribute known for return_type={return_type!r}; "
            f"pass collection.attribute explicitly. Known: {sorted(_ID_ATTRIBUTE_FOR_RETURN_TYPE)}"
        )

    # One group wrapping one terminal. The RCSB.org query builder needs the group
    # to render the condition, but not the two further nested groups this used to
    # emit -- and every byte here is paid for three times over once percent-encoded
    # (the encoding tokenizes at ~2.2 chars/token against ~4.6 for prose).
    request = {
        "query": {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": attr,
                        "operator": "in",
                        "negation": False,
                        "value": list(ids),
                    },
                }
            ],
        },
        "return_type": return_type,
        "request_options": {
            # Always at least as many rows as ids, so the whole set is on page 1.
            "paginate": {"start": 0, "rows": max(25, len(ids))},
            "results_content_type": ["experimental"],
        },
    }
    payload = json.dumps(request, separators=(",", ":"))
    return RCSB_SEARCH_URL + urllib.parse.quote(payload, safe="")


# --------------------------------------------------------------------------
# Template helpers
# --------------------------------------------------------------------------


def _render_fragments(items: list[Fragment]) -> Markup:
    """Join fragments, wrapping model-supplied ones in the provenance span.

    Adjacent fragments are joined with a single space unless the following one
    starts with punctuation, so the agent does not have to manage whitespace.
    """
    out: list[str] = []
    for frag in items:
        text = escape(frag.text)
        piece = f'<span class="non-tool-source">{text}</span>' if frag.model_supplied else str(text)
        if out and not frag.text[:1] in ",.;:)]}!?":
            out.append(" ")
        out.append(piece)
    return Markup("".join(out))


def _render_cell(value: Cell, kind: str) -> Markup:
    """Render one table cell according to its column kind."""
    if isinstance(value, list):
        return _render_fragments([v if isinstance(v, Fragment) else Fragment(**v) for v in value])

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


def render_report(req: ReportRequest, *, generated_at: datetime | None = None) -> str:
    """Render a ReportRequest to a complete, self-contained HTML document."""
    ids = list(req.collection.ids)
    if not ids and req.collection.enabled:
        id_col = req.identifier_column()
        if id_col is not None:
            ids = [str(row[id_col.key]) for row in req.rows if row.get(id_col.key)]

    collection_url = None
    if req.collection.enabled and ids:
        collection_url = build_collection_url(
            ids,
            return_type=req.collection.return_type,
            attribute=req.collection.attribute,
        )

    stamp = generated_at or datetime.now(timezone.utc)

    return _ENV.get_template("report.html.j2").render(
        req=req,
        fragments=_render_fragments,
        cell=_render_cell,
        collection_url=collection_url,
        collection_count=len(ids),
        template_version=TEMPLATE_VERSION,
        generated_at=stamp.strftime("%Y-%m-%d %H:%M UTC"),
    )
