"""HTTP endpoints that serve rendered reports: GET /r and GET /r/<url_id>.

The report subsystem's web surface, kept with the rest of the report package (models,
render, link codec, store) instead of in the server module. A FastMCP server attaches
them with register_report_routes(mcp); this module imports nothing from rcsb_mcp.server.
"""

from __future__ import annotations

import asyncio

from pydantic import ValidationError
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from . import link as report_link
from .models import ReportDocument
from .render import render_report
from .store import REPORT_STORE, URL_ID_RE

# The report render page is inert: fixed template, all values escaped, no scripts,
# no external resources. Lock that down so a crafted link can only ever produce an
# escaped report, and keep it out of search indexes since anyone can mint a link.
_REPORT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    # img-src is the RCSB CDN and nothing else: the template's masthead logo lives there
    # (inlining a 33 KB PNG would bloat every page and every `html` fallback). Keep it to
    # that exact origin -- not 'self', not '*' -- so the page still cannot be made to fetch
    # anything an attacker controls. Coupled to the template; see
    # tests/test_report_link.py::test_csp_allows_the_masthead_logo_origin.
    "Content-Security-Policy": (
        "default-src 'none'; img-src https://cdn.rcsb.org; style-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'none'"
    ),
    # Content-addressed by `d`, so the same link always renders the same page.
    "Cache-Control": "public, max-age=3600, immutable",
}
# Applied to the 400s too, so an error page is as inert as the report page.
_REPORT_ERROR_HEADERS = {"X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow"}
# An unknown short id might be a transient store miss (blip, or a link minted on
# another replica), so never let a browser or CDN cache the "expired" answer.
_EXPIRED_HEADERS = {**_REPORT_ERROR_HEADERS, "Cache-Control": "no-store"}

# Inert, self-contained "this link expired" page for an unknown short report id.
_EXPIRED_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Report link expired</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
max-width:34rem;margin:4rem auto;padding:0 1rem;color:#1c1c1c;line-height:1.5}
h1{font-size:1.3rem;color:#12507b;border-bottom:3px solid #12507b;padding-bottom:.4rem}</style>
</head><body>
<h1>This report link has expired</h1>
<p>Short report links are temporary. This one is no longer available &mdash; it may have
expired, or it was opened on a server that no longer holds it.</p>
<p>Re-run your query to generate a fresh report.</p>
</body></html>
"""


async def redirect_report_link(request):
    """Resolve a short report id to its self-contained URL and 302 there.

    The id maps (in a short-TTL, ideally shared store) to the packed report token;
    we redirect to ``/r?d=<token>`` — the durable, self-contained URL that renders
    with nothing stored. An unknown id — expired, evicted, or minted on another
    replica without a shared store — returns 410 with a friendly "expired" page.
    """
    url_id = request.path_params["url_id"]
    if not URL_ID_RE.match(url_id):
        return HTMLResponse(_EXPIRED_HTML, status_code=410, headers=_EXPIRED_HEADERS)
    # Offload the (possibly blocking, e.g. Redis-socket) read so a store stall can't
    # freeze the event loop and take the pod's liveness probe down with it.
    token = await asyncio.to_thread(REPORT_STORE.get, url_id)
    if not token:
        return HTMLResponse(_EXPIRED_HTML, status_code=410, headers=_EXPIRED_HEADERS)
    # Relative target: it inherits the caller's scheme/host, so the redirect works
    # behind any ingress without this endpoint knowing its own public origin.
    return RedirectResponse(f"/r?d={token}", status_code=302, headers=_REPORT_ERROR_HEADERS)


async def render_report_link(request):
    """Render a report packed into the ``d`` query param — stateless, nothing stored.

    ``d`` is the gzip+base64url of a ReportDocument (see report/link.py) — already
    resolved, so rendering needs no network call. Decoding is
    size-guarded against oversized and bomb inputs; the payload is validated against
    the schema; the template escapes every value. Anything malformed — bad token,
    wrong schema, or a value that render can't resolve — is a 400, never a 500.
    """
    token = request.query_params.get("d", "")
    try:
        report_json = report_link.decode_report(token)
        document = ReportDocument.model_validate_json(report_json)
        html = render_report(document)
    except report_link.LinkError as exc:
        # LinkError messages are static (from report/link.py), safe to surface.
        return PlainTextResponse(f"Invalid report link: {exc}\n", status_code=400,
                                 headers=_REPORT_ERROR_HEADERS)
    except (ValidationError, ValueError):
        # Schema mismatch, or a value render can't resolve. Static message — never
        # reflect attacker-controlled detail.
        return PlainTextResponse("Invalid report link: could not render this report\n",
                                 status_code=400, headers=_REPORT_ERROR_HEADERS)
    return HTMLResponse(html, headers=_REPORT_HEADERS)


def register_report_routes(mcp) -> None:
    """Attach the report HTTP endpoints to a FastMCP server (like register_report_tools)."""
    mcp.custom_route("/r/{url_id}", methods=["GET"])(redirect_report_link)
    mcp.custom_route("/r", methods=["GET"])(render_report_link)
