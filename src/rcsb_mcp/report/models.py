"""Pydantic models describing the structured input for a PDB search report.

The model is the *contract*: the agent supplies facts, the Jinja2 template
supplies markup. Nothing in here accepts HTML — all strings are escaped at
render time, which also satisfies the "escape tool-returned text" rule for free.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "Fragment",
    "Cell",
    "ColumnKind",
    "Column",
    "EditorLink",
    "ApiCall",
    "DataUsageItem",
    "ReportRequest",
]


class _Strict(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class Fragment(_Strict):
    """A run of text with an explicit provenance flag.

    This replaces hand-applied ``<span class="non-tool-source">`` wrapping.
    Provenance becomes a boolean the agent sets per fragment; the template
    decides how it is displayed, so the colour coding can never drift or be
    applied inconsistently between the table and the prose sections.
    """

    text: str = Field(..., description="Plain text. Do NOT include HTML tags; they are escaped.")
    model_supplied: bool = Field(
        default=False,
        description=(
            "True if this text is the assistant's own domain knowledge, interpretation or "
            "inference. False if the value came verbatim (or as a direct paraphrase) from an "
            "RCSB MCP tool response."
        ),
    )


# A cell is either plain tool-sourced text, or a mixed run of fragments.
Cell = Union[str, int, float, None, list[Fragment]]


class ColumnKind(str, Enum):
    """How a column's value is rendered."""

    TEXT = "text"
    PDB_ID = "pdb_id"  # -> https://www.rcsb.org/structure/{value}
    LIGAND_ID = "ligand_id"  # -> https://www.rcsb.org/ligand/{value}
    UNIPROT = "uniprot"  # -> https://www.uniprot.org/uniprotkb/{value}
    ORGANISM = "organism"  # italicised
    NUMERIC = "numeric"  # right-aligned; None renders as "NA"


class Column(_Strict):
    """One column of the results table.

    Columns are data, not markup, so the schema stays free to add, drop or
    reorder columns per query while the surrounding document stays fixed.
    """

    key: str = Field(..., description="Key used to look this column up in each row dict.", min_length=1)
    label: str = Field(..., description="Column header text, e.g. 'Resolution (Å)'.", min_length=1)
    kind: ColumnKind = Field(default=ColumnKind.TEXT, description="Rendering behaviour for the cell value.")


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class EditorLink(_Strict):
    """A query-editor link carried un-encoded, to save tokens.

    The tool returns this ``editor`` object instead of a long percent-encoded
    URL; the template rebuilds the exact editor URL at render time by
    JSON-encoding and percent-encoding ``params``. Copy it through verbatim.
    """

    url: str = Field(
        ...,
        description="Editor base URL from the tool's `editor.url`, e.g. 'https://search.rcsb.org/query-editor.html'.",
    )
    params: dict[str, Any] = Field(
        ...,
        description="Un-encoded query params from the tool's `editor.params`; the server percent-encodes them at render.",
    )

    @field_validator("url")
    @classmethod
    def _must_be_rcsb(cls, v: str) -> str:
        if not v.startswith(("https://search.rcsb.org/", "https://data.rcsb.org/", "https://sequence-coordinates.rcsb.org/")):
            raise ValueError(
                "editor.url must be a URL returned verbatim by an rcsb_* tool "
                "(search.rcsb.org, data.rcsb.org or sequence-coordinates.rcsb.org). "
                "Do not construct or edit these URLs by hand."
            )
        return v


class ApiCall(_Strict):
    """One entry in the 'API requests' section."""

    label: str = Field(..., description="Short human-readable label for the call.", min_length=1)
    editor: EditorLink | None = Field(
        default=None,
        description=(
            "The `editor` object returned BY THE TOOL, verbatim. Leave null for "
            "resolver and discovery tools (rcsb_find_*, rcsb_list_pdb_search_attributes, "
            "rcsb_describe_*), which do not return one."
        ),
    )
    tool_name: str | None = Field(default=None, description="MCP tool that was called, e.g. 'rcsb_get_entries'.")


class DataUsageItem(_Strict):
    """One step of the 'Data usage summary' narrative."""

    heading: str = Field(..., description="Short step name, e.g. 'Discovery', 'Filtering & disambiguation'.")
    body: list[Fragment] = Field(..., description="The explanation, split into provenance-tagged fragments.")


# --------------------------------------------------------------------------
# Top-level request
# --------------------------------------------------------------------------


class ReportRequest(_Strict):
    """Complete structured description of a PDB search report."""

    title: str = Field(..., description="Page title describing the search.", min_length=1)
    api_calls: list[ApiCall] = Field(default_factory=list)
    columns: list[Column] = Field(default_factory=list)
    rows: list[dict[str, Cell]] = Field(
        default_factory=list,
        description="One dict per result, keyed by Column.key. Missing keys render as 'NA'.",
    )
    sort_note: str | None = Field(default=None, description="How the table is ordered, e.g. 'Sorted by resolution, best first.'")
    data_usage: list[DataUsageItem] = Field(default_factory=list)
    no_results_note: list[Fragment] = Field(
        default_factory=list,
        description="Shown instead of the table when rows is empty; explain the search limitations here.",
    )

    @model_validator(mode="after")
    def _check_rows_against_columns(self) -> ReportRequest:
        if self.rows and not self.columns:
            raise ValueError("rows were supplied but columns is empty; define columns to render the table.")
        keys = {c.key for c in self.columns}
        for i, row in enumerate(self.rows):
            unknown = set(row) - keys
            if unknown:
                raise ValueError(
                    f"row {i} has keys not declared in columns: {sorted(unknown)}. "
                    f"Declared column keys are {sorted(keys)}."
                )
        return self
