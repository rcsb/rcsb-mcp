"""Build a rendered :class:`ReportDocument` from what the agent supplied.

The agent sends identifiers plus reasoning; this module selects the table spec
for ``result_type`` (see report/tables.py), fetches the cells derivable from
those identifiers in one batched round trip per chunk, and assembles the rows.

Two properties matter here.

**Self-contained.** The document — not the request — is what gets packed into a
report link, so every fetched value is baked in and ``/r`` renders with no
network call and nothing stored. A public endpoint must never re-fetch.

**Best-effort.** Filling must never cost a finished report. Everything after the
id list is built runs inside the guard, so junk from the API degrades cells to
"NA" instead of raising out of ``rcsb_render_report``. Ids are fetched in chunks
so one bad chunk degrades only its own rows.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .models import ReportDocument, ReportRequest
from .tables import EVIDENCE_KEY, ID_KEY, SPECS, TableSpec

__all__ = ["build_document", "EntryFetcher", "CHUNK"]

_log = logging.getLogger(__name__)

# Ids per request. Bounds the upstream call (result count is agent-controlled) and
# gives partial degradation: one failing chunk blanks only its own rows.
CHUNK = 50

# (query, ids) -> the GraphQL root field's nodes. Injected by the server, which
# owns the HTTP client, so this package keeps no network dependency.
EntryFetcher = Callable[[str, str, list[str]], Awaitable[list[dict[str, Any]]]]


def _norm(value: Any) -> str | None:
    """Normalised identifier, or None if unusable.

    Accepts an int because all-digit PDB ids (e.g. 1914) are real and a model may
    emit them unquoted; skipping those would blank the row's derivable cells.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None


async def _fetch_values(
    spec: TableSpec, ids: list[str], fetcher: EntryFetcher
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Fetch derivable cells for ``ids``. Returns (values by id, ids actually resolved).

    ``resolved`` is what makes partial failure safe: a row whose chunk never came
    back keeps rendering "NA" rather than being reported as "no such identifier".
    """
    values: dict[str, dict[str, Any]] = {}
    resolved: set[str] = set()
    for start in range(0, len(ids), CHUNK):
        chunk = ids[start : start + CHUNK]
        try:
            nodes = await fetcher(spec.query, spec.root_field, chunk)
            for node in nodes or []:
                if not isinstance(node, dict):
                    continue
                uid = _norm(node.get("rcsb_id"))
                if uid:
                    values[uid] = spec.map_values(node)
            resolved.update(chunk)
        except Exception as exc:  # noqa: BLE001 — filling is best-effort by design
            _log.warning(
                "report table fill failed for %d id(s) (%s); their %s cell(s) render as NA.",
                len(chunk), exc, ", ".join(spec.filled_keys),
            )
    return values, resolved


async def build_document(
    req: ReportRequest, fetcher: EntryFetcher | None = None
) -> ReportDocument:
    """Assemble the rendered document. Never raises on fill problems.

    With no fetcher (offline / tests) the table still renders: the id and evidence
    columns are agent-supplied, and the derivable cells show "NA".
    """
    spec = SPECS[req.result_type]

    ids: list[str] = []
    for result in req.results:
        uid = _norm(result.id)
        if uid and uid not in ids:  # normalised, so casing/whitespace can't duplicate
            ids.append(uid)

    values: dict[str, dict[str, Any]] = {}
    resolved: set[str] = set()
    if fetcher is not None and ids:
        values, resolved = await _fetch_values(spec, ids, fetcher)

    rows: list[dict[str, Any]] = []
    for result in req.results:
        uid = _norm(result.id)
        row: dict[str, Any] = {ID_KEY: result.id, EVIDENCE_KEY: result.evidence}
        if uid in resolved:
            # The API is the source of truth. An id it did not return yields None ->
            # "NA", never a value the report would wrongly present as tool-sourced.
            filled = values.get(uid) or {}
            row.update({k: filled.get(k) for k in spec.filled_keys})
        rows.append(row)

    return ReportDocument(
        title=req.title,
        api_calls=req.api_calls,
        columns=list(spec.columns),
        rows=rows,
        sort_note=req.sort_note,
        data_usage=req.data_usage,
        no_results_note=req.no_results_note,
    )
