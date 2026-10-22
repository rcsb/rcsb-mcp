"""A human-readable page for people who open the MCP endpoint in a web browser.

The endpoint URL (https://mcp-beta.rcsb.org/mcp) is what we tell people to paste into an
MCP client, so it gets clicked too. A browser's GET lacks `Accept: text/event-stream`, and
the SDK answers that with a 406 JSON-RPC error ("Not Acceptable: Client must accept
text/event-stream") -- correct per the protocol, but it reads as a broken server. This
serves a short "this is an MCP server, here is how to connect" page instead, to browser
navigations ONLY:

- A GET whose Accept names text/html and not text/event-stream is a browser navigation:
  MCP clients send POST, or a GET asking for text/event-stream, and are passed through
  untouched. curl's default `*/*` names neither, so a bare curl still gets the SDK's 406.
- `Vary: Accept` keeps a cache in front of the pods from handing this page to an MCP
  client, or the 406 to a browser.
- The site root (`/`, a 404 before) serves the same page, for anyone who trims the path.

The page is inert, like the report pages: fixed text, no scripts, and the one reflected
value (the URL the visitor opened) is escaped.
"""

from __future__ import annotations

import html

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_LANDING_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    # Same image origins as the report page (logo on cdn, favicon on www), nothing else.
    "Content-Security-Policy": (
        "default-src 'none'; img-src https://cdn.rcsb.org https://www.rcsb.org; "
        "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    ),
    "Vary": "Accept",
    "Cache-Control": "no-cache",
}

_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="https://www.rcsb.org/favicon.ico" sizes="any">
<title>RCSB PDB MCP server</title>
<style>
 :root { --rcsb-blue: #12507b; --rcsb-rule: #cfd8dd; }
 body { font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
        margin: 2rem auto; max-width: 46rem; padding: 0 1rem; color: #1c1c1c; line-height: 1.55; }
 .masthead { display: flex; align-items: center; gap: .9rem;
             border-bottom: 3px solid var(--rcsb-blue); padding-bottom: .4rem; margin-bottom: 1.2rem; }
 .masthead h1 { font-size: 1.5rem; margin: 0; }
 #rcsblogo { height: 2.5rem; width: auto; flex: none; display: block; }
 h2 { font-size: 1.1rem; margin-top: 1.8rem; color: var(--rcsb-blue); }
 code, pre { background: #eef2f5; border-radius: 3px; font-size: .88em; }
 code { padding: .05rem .25rem; }
 pre { padding: .7rem .9rem; overflow-x: auto; }
 .endpoint { background: #f0f4f7; border-left: 4px solid var(--rcsb-blue); padding: .7rem .9rem;
             font-size: 1.05rem; word-break: break-all; }
 footer { margin-top: 2.5rem; padding-top: .8rem; border-top: 1px solid var(--rcsb-rule);
          font-size: .82rem; color: #667; }
</style>
</head>
<body>
<header class="masthead">
  <a href="https://www.rcsb.org"><img id="rcsblogo" src="https://cdn.rcsb.org/rcsb-pdb/v2/common/images/rcsb_logo.png" alt="RCSB PDB"></a>
  <h1>RCSB PDB MCP server <small>(beta)</small></h1>
</header>

<p>This address is a <a href="https://modelcontextprotocol.io">Model Context Protocol</a>
(MCP) server. It lets AI assistants search and explore Protein Data Bank structures through
the RCSB Search, Data and Sequence Coordinates APIs. It's meant for AI clients, not web
browsers, so there's nothing more to see here. To use it, add this URL to your AI client:</p>

<p class="endpoint"><code>{endpoint}</code></p>

<p>No install, API key or account is needed.</p>

<h2>Connect a client</h2>
<p><b>Claude</b> (web or desktop): Settings &rarr; Connectors &rarr; Add custom connector,
then paste the URL above.</p>
<p><b>Claude Code</b>:</p>
<pre>claude mcp add --transport http rcsb-mcp {endpoint}</pre>
<p><b>Other clients that take a URL</b> (Cursor, VS Code, Zed, <code>.mcp.json</code>, &hellip;):</p>
<pre>{
  "mcpServers": {
    "rcsb-mcp": { "type": "http", "url": "{endpoint}" }
  }
}</pre>
<p>More clients, local installation and the full tool list are in the
<a href="https://github.com/rcsb/rcsb-mcp#connect-an-agent">rcsb-mcp README</a>.</p>

<footer>
  rcsb-mcp {version} &middot; Beta: the tools may change without notice. &middot;
  <a href="https://github.com/rcsb/rcsb-mcp">Source and issues on GitHub</a> &middot;
  <a href="https://www.rcsb.org">RCSB PDB</a>
</footer>
</body>
</html>
"""


def _endpoint_url(request: Request, mcp_path: str) -> str:
    """The MCP URL to show, built from the address the visitor actually opened.

    The pods sit behind a TLS-terminating ingress, so the request reaches uvicorn as http;
    trust X-Forwarded-Proto for the scheme when it is a plain http/https value.
    """
    scheme = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if scheme not in ("http", "https"):
        scheme = request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}{mcp_path}"


def landing_response(request: Request, mcp_path: str, version: str) -> HTMLResponse:
    # str.replace, not str.format: the page's CSS and JSON are full of braces.
    page = _LANDING_HTML.replace("{endpoint}", html.escape(_endpoint_url(request, mcp_path)))
    page = page.replace("{version}", html.escape(version))
    return HTMLResponse(page, headers=_LANDING_HEADERS)


def is_browser_navigation(headers: Headers) -> bool:
    """True for a browser page load: it asks for HTML and not for an MCP event stream."""
    accept = headers.get("accept", "").lower()
    return "text/html" in accept and "text/event-stream" not in accept


class BrowserLandingMiddleware:
    """Answer a browser's GET of the MCP path with the landing page; pass all else through.

    Pure ASGI rather than Starlette's BaseHTTPMiddleware, which buffers the wrapped
    response and so would interfere with the transport's SSE streams.
    """

    def __init__(self, app: ASGIApp, mcp_path: str, version: str) -> None:
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/"
        self.version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in ("GET", "HEAD")
            and (scope["path"].rstrip("/") or "/") == self.mcp_path
            and is_browser_navigation(Headers(scope=scope))
        ):
            response = landing_response(Request(scope), self.mcp_path, self.version)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
