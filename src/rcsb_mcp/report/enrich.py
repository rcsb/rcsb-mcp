"""Server-side fill of the fixed result columns from the PDB IDs the agent supplies.

The results table has a fixed schema, and four of its columns — Title, Organism,
Method, Resolution — are fully determined by the entry id. Having the agent retype
them into the tool call costs ~1,000 output tokens on a 20-row report AND puts every
value one transcription slip away from being wrong. So the agent supplies only the
PDB ID and the Evidence, and the server fetches the rest from the Data API.

That makes these cells *definitionally* tool-sourced: they match the API, which is
what the report's provenance colouring has always claimed but previously had to take
on trust.

Multi-valued fields show EVERY distinct value rather than silently picking one: an
entry can have several source organisms (antibody+antigen, host+pathogen) and several
experimental methods (joint X-ray/neutron refinement, e.g. 10YN and 5E5J).

Enrichment is best-effort and must NEVER cost a finished report. Everything after the
id list is built — the fetch, the mapping, and the validating row assignment — runs
inside the guard, so junk from the API degrades cells to "NA" instead of raising out
of ``rcsb_render_report``. Ids are fetched in chunks so one bad chunk degrades only
its own rows.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .models import ColumnKind, ReportRequest

__all__ = [
    "ENTRY_FIELDS_QUERY",
    "SERVER_FILLED_KEYS",
    "entry_values",
    "id_column_key",
    "fill_from_entries",
]

_log = logging.getLogger(__name__)

# One round trip per chunk for all four columns: polymer_entities nests inside
# entries, so the per-entity organism comes back with the entry-level scalars.
# structure_determination_methodology is the fallback method for computed structure
# models (AlphaFold etc.), whose `exptl` is null.
ENTRY_FIELDS_QUERY = """query ReportRows($ids: [String!]!) {
  entries(entry_ids: $ids) {
    rcsb_id
    struct { title }
    exptl { method }
    rcsb_entry_info { resolution_combined structure_determination_methodology }
    polymer_entities { rcsb_entity_source_organism { ncbi_scientific_name scientific_name } }
  }
}"""

# Column keys the SERVER owns. Matched by key because the results schema is fixed
# (see the pdb_assistant prompt); a table that doesn't use these keys is left alone.
SERVER_FILLED_KEYS = ("title", "organism", "method", "resolution")

# Conventional key for the entry-id column, used when the agent forgot `kind: pdb_id`.
_ID_KEY = "pdb_id"

# Ids per Data-API request. Bounds the upstream request (row count is agent-controlled)
# and gives partial degradation: one failing chunk blanks only its own rows.
_CHUNK = 50

EntryFetcher = Callable[[list[str]], Awaitable[list[dict[str, Any]]]]


def _cell(value: Any) -> Any:
    """Coerce an API value to something the ``Cell`` union accepts.

    ``req.rows`` is a validating assignment (validate_assignment=True), so a value
    outside ``str | int | float | None`` would raise ValidationError and cost the
    report. Anything unexpected becomes None and renders as "NA".
    """
    if isinstance(value, bool):
        return None  # pydantic would coerce it to int and render a bare "1"
    if value is None or isinstance(value, (str, int, float)):
        return value
    return None


def _joined(values: list[Any]) -> Any:
    """One value stays scalar (so numeric columns stay numeric); several are joined.

    Keeps the common single-valued case rendering exactly as before while honouring
    the "show every distinct value" rule for the multi-valued minority.
    """
    if not values:
        return None
    if len(values) == 1:
        return _cell(values[0])
    return "; ".join(str(v) for v in values)


def _distinct(items: Any, extract: Callable[[Any], Any]) -> list[Any]:
    """Order-preserving distinct extraction over a possibly-junk API list."""
    out: list[Any] = []
    if not isinstance(items, list):
        return out
    for item in items:
        value = extract(item) if isinstance(item, dict) else None
        if value is not None and value != "" and value not in out:
            out.append(value)
    return out


def entry_values(entry: dict[str, Any]) -> dict[str, Any]:
    """Map one Data-API entry node to its four server-filled cell values.

    Defensive throughout: every container may be absent, null, or the wrong shape
    (an NMR entry has no resolution; a computed model has no `exptl`), and a null
    list member must never raise — this runs on data we do not control.
    """
    struct = entry.get("struct")
    info = entry.get("rcsb_entry_info")
    struct = struct if isinstance(struct, dict) else {}
    info = info if isinstance(info, dict) else {}

    methods = _distinct(entry.get("exptl"), lambda e: e.get("method"))
    if not methods:
        # Computed structure models (AlphaFold etc.) carry no exptl.
        csm = info.get("structure_determination_methodology")
        if csm:
            methods = [csm]

    # Resolution stays a SINGLE value even for joint refinements. `resolution_combined`
    # is ordered by the `refine` block, NOT by `exptl`, so rendering both lists joined
    # side by side asserts a positional pairing that is simply wrong: 10YN reports
    # exptl [X-RAY, NEUTRON] and resolutions [2.4, 1.65] while refine says NEUTRON=2.4
    # and X-RAY=1.65 — the reverse. Showing the best (lowest) value claims nothing
    # about which method produced it.
    resolutions = [
        r for r in (info.get("resolution_combined") or [])
        if isinstance(r, (int, float)) and not isinstance(r, bool)
    ] if isinstance(info.get("resolution_combined"), list) else []

    # Organism is a property of each polymer ENTITY, not of the entry: a complex can
    # carry several (antibody+antigen, host+pathogen). Show every distinct one.
    # Fall back to scientific_name: entries like 193D and 1MJ0 carry only that, and
    # keying on ncbi_scientific_name alone silently rendered them NA.
    organisms: list[str] = []
    entities = entry.get("polymer_entities")
    for entity in entities if isinstance(entities, list) else []:
        if not isinstance(entity, dict):
            continue
        for name in _distinct(entity.get("rcsb_entity_source_organism"),
                              lambda s: s.get("ncbi_scientific_name") or s.get("scientific_name")):
            if name not in organisms:
                organisms.append(name)

    return {
        "title": _cell(struct.get("title")),
        "organism": _joined(organisms),
        "method": _joined(methods),
        "resolution": min(resolutions) if resolutions else None,
    }


def id_column_key(req: ReportRequest) -> str | None:
    """Key of the entry-id column, or None if this table isn't keyed by PDB entry.

    Prefers the declared ``kind``, falling back to the conventional ``pdb_id`` key so
    a forgotten ``kind`` doesn't silently blank four columns for the whole table.
    Ligand (LIGAND_ID) tables have no entry-level method or resolution and are left
    exactly as the agent supplied them.
    """
    # Checked FIRST: a table that mentions a ligand at all is a ligand table, even if
    # it also carries an entry id column. There `title` means the chemical component
    # name, so entry-level fill would clobber it.
    if any(c.kind is ColumnKind.LIGAND_ID for c in req.columns):
        return None
    for column in req.columns:
        if column.kind is ColumnKind.PDB_ID:
            return column.key
    if _ID_KEY in {c.key for c in req.columns}:
        return _ID_KEY
    return None


def _row_id(value: Any) -> str | None:
    """Normalised entry id from a cell, or None if it isn't a usable id.

    Accepts an int because all-digit PDB ids (e.g. 1914) are real and a model may
    emit them unquoted; skipping those would blank four cells for that row.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None


async def fill_from_entries(req: ReportRequest, fetcher: EntryFetcher) -> None:
    """Fill the server-owned columns of ``req.rows`` in place. Never raises.

    Only columns the agent actually DECLARED are filled, so this can never introduce
    a row key that isn't in ``columns`` (which the model would reject).
    """
    targets = [c.key for c in req.columns if c.key in SERVER_FILLED_KEYS]
    id_key = id_column_key(req)
    if id_key is None:
        if targets:
            # The agent declared server-filled columns but we can't find an id column
            # to fill them from, so the table would render NA with no other signal.
            _log.warning(
                "report declares server-filled column(s) %s but no entry-id column was "
                "found (need kind='pdb_id' or key='pdb_id'); those cells will render NA.",
                ", ".join(targets),
            )
        return
    if not targets:
        return

    ids: list[str] = []
    for row in req.rows:
        uid = _row_id(row.get(id_key))
        if uid and uid not in ids:  # normalised, so casing/whitespace can't duplicate
            ids.append(uid)
    if not ids:
        return

    # `resolved` tracks ids whose chunk actually came back, so a row in a FAILED chunk
    # keeps whatever the agent sent instead of being wrongly blanked.
    by_id: dict[str, dict[str, Any]] = {}
    resolved: set[str] = set()
    for start in range(0, len(ids), _CHUNK):
        chunk = ids[start : start + _CHUNK]
        try:
            entries = await fetcher(chunk)
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                uid = _row_id(entry.get("rcsb_id"))
                if uid:
                    by_id[uid] = entry_values(entry)
            resolved.update(chunk)
        except Exception as exc:  # noqa: BLE001 — enrichment is best-effort by design
            _log.warning(
                "report enrichment failed for %d id(s) (%s); their %s cell(s) fall back "
                "to whatever the agent supplied, rendering as NA where absent.",
                len(chunk), exc, ", ".join(targets),
            )

    if not resolved:
        return

    try:
        rows = []
        for row in req.rows:
            uid = _row_id(row.get(id_key))
            if uid in resolved:
                # Server value wins: the API is the source of truth for these columns.
                # An id the API didn't return yields None -> "NA", rather than leaving
                # agent-written text sitting in a cell the report calls tool-sourced.
                fetched = by_id.get(uid) or {}
                row = {**row, **{k: fetched.get(k) for k in targets}}
            rows.append(row)
        req.rows = rows  # validating assignment; guarded so it can never cost the report
    except Exception as exc:  # noqa: BLE001
        _log.warning("report enrichment could not be applied (%s); rows left as supplied.", exc)
