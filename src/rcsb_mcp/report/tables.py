"""One table spec per :class:`ResultType` — the whole presentation layer.

The agent sends identifiers and reasoning; everything about how those become a
table lives here. A spec says which columns exist, how to fetch the cells that
are derivable from the identifier, and how to map an API node onto those cells.

Adding a result type is one enum value plus one entry in :data:`SPECS`. The
search API returns four types (entry, polymer_entity, assembly, mol_definition);
ENTRY and LIGAND cover the two that matter, so at most two more could ever be
added — and each arrives reviewed, with a known query and tests, rather than as
an open-ended generic table the agent invents at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import Column, ColumnKind, ResultType

__all__ = ["TableSpec", "SPECS", "ENTRY_SPEC", "LIGAND_SPEC", "ID_KEY", "EVIDENCE_KEY"]

# Row keys the builder owns. Not agent-facing — the agent never names a column.
ID_KEY = "id"
EVIDENCE_KEY = "evidence"


def _cell(value: Any) -> Any:
    """Coerce an API value to something the ``Cell`` union accepts.

    Rows are validated when the document is built, so a value outside
    ``str | int | float | None`` would raise. Anything unexpected becomes None
    and renders as "NA" — never a crash on data we do not control.
    """
    if isinstance(value, bool):
        return None  # pydantic would coerce it to int and render a bare "1"
    if value is None or isinstance(value, (str, int, float)):
        return value
    return None


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


def _joined(values: list[Any]) -> Any:
    """One value stays scalar (so numeric columns stay numeric); several are joined."""
    if not values:
        return None
    if len(values) == 1:
        return _cell(values[0])
    return "; ".join(str(v) for v in values)


# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------

ENTRY_QUERY = """query ReportRows($ids: [String!]!) {
  entries(entry_ids: $ids) {
    rcsb_id
    struct { title }
    exptl { method }
    rcsb_entry_info { resolution_combined structure_determination_methodology }
    polymer_entities { rcsb_entity_source_organism { ncbi_scientific_name scientific_name } }
  }
}"""


def entry_values(entry: dict[str, Any]) -> dict[str, Any]:
    """Map one Data-API entry node onto its derivable cells.

    Defensive throughout: every container may be absent, null, or the wrong
    shape (an NMR entry has no resolution; a computed model has no `exptl`).
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
    # and X-RAY=1.65 — the reverse. The best (lowest) value claims nothing about which
    # method produced it.
    raw_res = info.get("resolution_combined")
    resolutions = [
        r for r in (raw_res or []) if isinstance(r, (int, float)) and not isinstance(r, bool)
    ] if isinstance(raw_res, list) else []

    # Organism is a property of each polymer ENTITY, not of the entry: a complex can
    # carry several (antibody+antigen, host+pathogen). Show every distinct one, and
    # fall back to scientific_name — 193D and 1MJ0 carry only that, and keying on
    # ncbi_scientific_name alone rendered them NA.
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


# --------------------------------------------------------------------------
# ligand (chemical component)
# --------------------------------------------------------------------------

LIGAND_QUERY = """query ReportRows($ids: [String!]!) {
  chem_comps(comp_ids: $ids) {
    rcsb_id
    chem_comp { name type formula_weight }
  }
}"""


def ligand_values(comp: dict[str, Any]) -> dict[str, Any]:
    """Map one Data-API chem_comp node onto its derivable cells.

    ``type`` earns its column: chemical searches routinely return modified
    residues and ions alongside genuine small molecules (MSE is
    "L-peptide linking", ZN is an ion), and it is what separates them.
    """
    cc = comp.get("chem_comp")
    cc = cc if isinstance(cc, dict) else {}
    return {
        "name": _cell(cc.get("name")),
        "type": _cell(cc.get("type")),
        "weight": _cell(cc.get("formula_weight")),
    }


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TableSpec:
    """Everything that turns identifiers + evidence into a rendered table."""

    columns: list[Column]
    query: str
    map_values: Callable[[dict[str, Any]], dict[str, Any]]
    root_field: str  # GraphQL root field holding the nodes

    @property
    def filled_keys(self) -> tuple[str, ...]:
        """Column keys the server fills (everything but the id and the evidence)."""
        return tuple(c.key for c in self.columns if c.key not in (ID_KEY, EVIDENCE_KEY))


ENTRY_SPEC = TableSpec(
    columns=[
        Column(key=ID_KEY, label="PDB ID", kind=ColumnKind.PDB_ID),
        Column(key="title", label="Title"),
        Column(key="organism", label="Organism", kind=ColumnKind.ORGANISM),
        Column(key="method", label="Method"),
        Column(key="resolution", label="Resolution (Å)", kind=ColumnKind.NUMERIC),
        Column(key=EVIDENCE_KEY, label="Evidence"),
    ],
    query=ENTRY_QUERY,
    map_values=entry_values,
    root_field="entries",
)

LIGAND_SPEC = TableSpec(
    columns=[
        Column(key=ID_KEY, label="Ligand ID", kind=ColumnKind.LIGAND_ID),
        Column(key="name", label="Name"),
        Column(key="type", label="Type"),
        Column(key="weight", label="Weight (Da)", kind=ColumnKind.NUMERIC),
        Column(key=EVIDENCE_KEY, label="Evidence"),
    ],
    query=LIGAND_QUERY,
    map_values=ligand_values,
    root_field="chem_comps",
)

SPECS: dict[ResultType, TableSpec] = {
    ResultType.ENTRY: ENTRY_SPEC,
    ResultType.LIGAND: LIGAND_SPEC,
}
