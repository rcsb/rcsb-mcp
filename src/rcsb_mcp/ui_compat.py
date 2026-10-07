"""Declare the MCP Apps extension on mcp 1.x. DELETE after the mcp 2.x migration.

``ServerCapabilities`` in mcp 1.x has no ``extensions`` field -- it arrives in protocol
revision 2026-07-28 -- but the model is ``extra="allow"``, so the declaration serialises
onto the wire anyway. Claude advertises ``io.modelcontextprotocol/ui`` in its initialize
request even at 2025-11-25, so answering in kind costs nothing.

**This is a cheap shot, not a known fix.** The MCP Apps spec (2026-01-26 and the current
draft) says negotiation is one-directional: the client advertises, and the server simply
registers tools carrying ``_meta.ui.resourceUri``. There is no documented server-side
declaration channel at 2025-11-25, and no host is known to read this. Keep it because it is
free and might be read; do not treat it as the thing that makes the app render.

**What was tried and REMOVED:** a ``server/discover`` responder. It is the wrong move.
That method belongs to 2026-07-28, a revision which deletes ``initialize`` entirely, so
answering it with a ``DiscoverResult`` tells the client "I am modern" and invites stateless
requests this SDK cannot serve. The spec names ``-32602`` as a typical legacy-server reply
and requires the client to fall back to ``initialize`` -- which Claude does. The error was
correct behaviour, and a ``DiscoverResult`` advertising only ``2025-11-25`` is a shape the
spec defines no client behaviour for. mcp 2.x implements the method properly; until then,
erroring is right.
"""

from __future__ import annotations

from typing import Any

__all__ = ["UI_EXTENSION_ID", "declare_ui_extension"]

UI_EXTENSION_ID = "io.modelcontextprotocol/ui"


def declare_ui_extension(mcp: Any) -> None:
    """Add ``capabilities.extensions`` to every initialize result.

    ``create_initialization_options`` is called per request, so wrapping the bound method
    is enough -- the same seam ``server.py`` already uses to set ``version``.
    """
    server = mcp._mcp_server
    original = server.create_initialization_options

    def with_ui_extension(*args: Any, **kwargs: Any):
        options = original(*args, **kwargs)
        options.capabilities.extensions = {UI_EXTENSION_ID: {}}
        return options

    server.create_initialization_options = with_ui_extension  # type: ignore[method-assign]
