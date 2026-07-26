"""Shared tool-definition helpers — the bits every tool group needs to declare a tool.

Distinct from :mod:`rcsb_mcp.client` (network transport): this holds the pieces that
describe a tool to MCP, not the pieces that make an HTTP call. Kept here so a tool
package can ``register_<x>_tools(mcp)`` without importing :mod:`rcsb_mcp.server` — the
dependency runs one way, tool modules import this, never the reverse, so no cycles.

Only genuinely cross-cutting tool-definition bits belong here (used by 2+ tool groups).
A helper specific to one domain stays with that domain's package.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

# Every tool in this server is a read-only query against public RCSB/EBI web
# APIs: it never mutates state, repeated calls are safe (idempotent), and it
# reaches external services (open world). Shared by all @mcp.tool decorators.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)
