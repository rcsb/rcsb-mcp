"""Deterministic HTML reports for rcsb-mcp search results.

The agent supplies facts as a :class:`ReportRequest`; the Jinja2 template owns
every byte of markup. Import the models and :func:`render_report` from here.
"""

from __future__ import annotations

from .link import LinkError, decode_report, encode_report
from .models import (
    ApiCall,
    AttributeCondition,
    Block,
    Cell,
    CollectionLink,
    Column,
    ColumnKind,
    DataUsageItem,
    Fragment,
    QuerySummary,
    ReportRequest,
)
from .render import TEMPLATE_VERSION, build_collection_url, render_report

__all__ = [
    "ApiCall",
    "AttributeCondition",
    "Block",
    "Cell",
    "CollectionLink",
    "Column",
    "ColumnKind",
    "DataUsageItem",
    "Fragment",
    "LinkError",
    "QuerySummary",
    "ReportRequest",
    "TEMPLATE_VERSION",
    "build_collection_url",
    "decode_report",
    "encode_report",
    "render_report",
]
