"""Deterministic HTML reports for rcsb-mcp search results.

The agent supplies facts as a :class:`ReportRequest`; the Jinja2 template owns
every byte of markup. Import the models and :func:`render_report` from here.
"""

from __future__ import annotations

from .link import LinkError, decode_report, encode_report
from .models import (
    ApiCall,
    Cell,
    Column,
    ColumnKind,
    DataUsageItem,
    Fragment,
    ReportRequest,
)
from .render import TEMPLATE_VERSION, render_report

__all__ = [
    "ApiCall",
    "Cell",
    "Column",
    "ColumnKind",
    "DataUsageItem",
    "Fragment",
    "LinkError",
    "ReportRequest",
    "TEMPLATE_VERSION",
    "decode_report",
    "encode_report",
    "render_report",
]
