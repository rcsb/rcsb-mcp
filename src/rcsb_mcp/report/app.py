"""MCP App (SEP-1865) surface for the report: a ``ui://`` resource the host renders.

Why this exists
---------------
``rcsb_render_report`` hands back a short link, which costs the model ~25 tokens and
is the deliverable for every client. But a link is something the user has to click,
and the report then opens outside the conversation.

The MCP Apps extension (``io.modelcontextprotocol/ui``, SEP-1865, Final) adds a second
channel: a tool may point at a predeclared ``ui://`` HTML resource, and the HOST fetches
that resource over ``resources/read`` -- a client<->server call the model is not part of --
and renders it in a sandboxed iframe inline in the conversation.

The design decision here: **the app is a loader, not a second renderer.** It reads the
URL the tool already returned out of the tool result, fetches it, and transplants the
markup. ``report/render.py`` stays the only thing that turns a document into HTML, so
there is no port to keep in sync. (A JS re-implementation was prototyped and rejected:
Python ``str(2.0)`` is ``"2.0"`` and JavaScript ``String(2.0)`` is ``"2"``, so a
resolution silently lost its precision. Language-level formatting differences like that
diverge without anything noticing.)

The CSS is likewise single-sourced: it is extracted verbatim from
``templates/report.html.j2`` at import, never copied into this file. Only the dark-mode
token layer is additive, because the server-rendered page targets a white page while an
app is composited into whatever theme the host reports.

What is NOT solved here
-----------------------
The spec says "Servers SHOULD check client capabilities before registering UI-enabled
tools", but ``mcp`` 1.28.1 has no ``extensions`` field on ``ClientCapabilities`` and
FastMCP registers tools once at import rather than per session, so there is nothing to
check against. ``RCSB_MCP_ENABLE_REPORT_APP`` is the honest stand-in: off by default,
flipped on per deployment. Replace it with real negotiation once the SDK models it.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any
from urllib.parse import urlsplit

from .render import TEMPLATE_VERSION

__all__ = [
    "APP_MIME_TYPE",
    "APP_RESOURCE_PREFIX",
    "APP_RESOURCE_URI",
    "UI_APP_ENABLED",
    "app_connect_origins",
    "register_report_app",
    "render_app_html",
    "resource_ui_meta",
    "tool_ui_meta",
]

# The ``ui://`` scheme is what marks a resource as an MCP App; the path is ours to choose.
# The ui:// URI is CONTENT-ADDRESSED: `ui://rcsb-mcp/report-<hash>.html`, the hash taken
# over the app HTML (see APP_RESOURCE_URI at the bottom of this module).
#
# Why: claude.ai caches the app by URI, across fresh chats. Measured 2026-10-06 -- after a
# deploy that changed the app, Claude ran rcsb_render_report and never called
# resources/read, so it rendered the PREVIOUS app from cache. A fixed URI means a fix never
# reaches anyone who has seen the app before. A hash makes every change a URI Claude has
# not seen.
#
# Hash the HTML ONLY, never the CSP metadata: in production connectDomains differs between
# west and east (`{coast}`), so hashing it would give each cluster a different URI, and
# with GSLB the tool listing and the resources/read can land on different clusters.
#
# The `.html` suffix matches both official examples (ext-apps qr-server's
# `ui://qr-server/view.html`). It is kept, but it is NOT known to matter: the first render
# came right after renaming `report` -> `report.html`, which also busted Claude's cache of a
# broken app, and the two explanations cannot be told apart from what was logged.
APP_RESOURCE_PREFIX = "ui://rcsb-mcp/report"
# Fixed by the extension: the only content type SEP-1865 defines.
APP_MIME_TYPE = "text/html;profile=mcp-app"
# Protocol version of the handshake this app speaks (see the spec's ui/initialize).
UI_PROTOCOL_VERSION = "2026-01-26"

# Off by default -- see "What is NOT solved here" above. A public server should not start
# advertising a UI channel to every client on the strength of an env var nobody set.
UI_APP_ENABLED = os.environ.get("RCSB_MCP_ENABLE_REPORT_APP", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Origins the report page itself pulls static assets from. Kept identical to the
# `img-src` list in routes.py::_REPORT_HEADERS -- the same two RCSB origins, for the
# same reason (the masthead logo on the cdn, the favicon on www).
_ASSET_ORIGINS = ("https://cdn.rcsb.org", "https://www.rcsb.org")


def _origin(url: str | None) -> str | None:
    """Reduce a configured base URL to a bare scheme://host[:port] for a CSP list."""
    if not url:
        return None
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def app_connect_origins() -> list[str]:
    """Origins the app must be allowed to ``fetch()``, derived from the link config.

    Both bases matter and they are usually DIFFERENT hosts (see ``_link_base`` in
    tools.py): the short link is minted against the cluster-pinned origin so the
    redis holding its id is the one that answers, and it 302s to the public origin,
    which is self-contained. A fetch follows that redirect, so the app needs both --
    listing only one silently fails at whichever hop was left out.
    """
    from . import tools as report_tools  # late: tools imports render, which imports us not at all

    origins: list[str] = []
    for candidate in (report_tools.REPORT_BASE_URL, report_tools._link_base()):
        origin = _origin(candidate)
        if origin and origin not in origins:
            origins.append(origin)
    return origins


def tool_ui_meta() -> dict[str, Any] | None:
    """``_meta`` for ``rcsb_render_report``: the pointer at the app resource.

    ``visibility`` is left at its default (``["model", "app"]``) on purpose -- the tool
    must stay in the model's tool list, because the short link is the deliverable on
    every client that cannot render an app.
    """
    if not UI_APP_ENABLED:
        return None
    # Both keys: the nested one is the spec, the flat "ui/resourceUri" is the legacy
    # alias the official ext-apps example still emits for older hosts.
    return {
        "ui": {"resourceUri": APP_RESOURCE_URI},
        "ui/resourceUri": APP_RESOURCE_URI,
    }


def resource_ui_meta() -> dict[str, Any]:
    """``_meta`` for the ``ui://`` resource: the sandbox policy the host must apply.

    Without a ``csp`` the host applies ``default-src 'none'; script-src 'self'``, which
    would block both the fetch of the report and the masthead image.
    """
    return {
        "ui": {
            "csp": {
                "connectDomains": app_connect_origins(),
                "resourceDomains": list(_ASSET_ORIGINS),
            },
            # The report is a document with its own masthead rule; a host border around
            # it reads as a frame around a frame.
            "prefersBorder": False,
        }
    }


# --------------------------------------------------------------------------
# Styling: extracted from the template, never copied
# --------------------------------------------------------------------------

_FALLBACK_CSS = (
    "body{font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;"
    "line-height:1.5}table{border-collapse:collapse;width:100%;font-size:.83rem}"
    "th,td{border:1px solid #cfd8dd;padding:.45rem .55rem;text-align:left}"
)


def _template_css() -> str:
    """Pull the report stylesheet out of the Jinja template verbatim.

    Read rather than duplicated so a change to the template's look reaches the app
    with no second edit. Falls back to a plain table style if the extraction ever
    stops matching -- an unstyled report beats a server that will not import.
    """
    try:
        from importlib.resources import files

        source = (files("rcsb_mcp.report") / "templates" / "report.html.j2").read_text("utf-8")
        match = re.search(r"<style>(.*?)</style>", source, re.S)
        return match.group(1).strip() if match else _FALLBACK_CSS
    except Exception:  # pragma: no cover - defensive: never block server import
        return _FALLBACK_CSS


# The server-rendered page assumes a white browser page. An app is composited into
# whatever theme the host reports via hostContext.theme, so the dark half is added
# here -- additively, overriding the rules that carry literal colours, because the
# template sets some of them directly rather than through its tokens.
_DARK_CSS = """
:root[data-theme="dark"] {
  color-scheme: dark;
  --rcsb-blue: #1a4a6e;
  --rcsb-rule: #2b3a45;
  --rcsb-zebra: #161e25;
  --model-source: #e0a059;
}
:root[data-theme="dark"] body { background: #11171c; color: #e4eaef; }
:root[data-theme="dark"] h2 { color: #7cb8e0; }
:root[data-theme="dark"] a { color: #7cb8e0; }
:root[data-theme="dark"] th { color: #f2f8fc; }
:root[data-theme="dark"] code { background: #1d262e; }
:root[data-theme="dark"] .muted { color: #8d9aa6; }
:root[data-theme="dark"] .legend,
:root[data-theme="dark"] .empty { background: #241c10; }
:root[data-theme="dark"] .params { background: #15202a; }
:root[data-theme="dark"] footer { color: #8d9aa6; }
:root[data-theme="dark"] p[style] { color: #8d9aa6 !important; }
"""

# Chrome belonging to the app itself (status line, error state), not to the report.
_APP_CSS = """
/* Reserve the scrollbar's gutter whether or not a scrollbar is showing. Without it the
   view's width depends on whether it momentarily overflows mid-resize, the table rewraps
   at the narrower width, the content gets taller, the reported height changes, and the
   host and the view chase each other (measured: 2342 -> 2381 -> 2342 px). With a stable
   gutter the content height depends only on the width the HOST chose. */
html { scrollbar-gutter: stable; }
body { margin: 0 auto; max-width: 1400px; padding: 1rem; }
#status { font-size: .9rem; color: #667; padding: .6rem 0; }
#status[data-state="error"] { color: #b4231f; }
:root[data-theme="dark"] #status { color: #8d9aa6; }
:root[data-theme="dark"] #status[data-state="error"] { color: #ef8079; }
#fallback-link { font-size: .9rem; }
/* The server template sizes its table for a full browser tab. An app is given a
   pane, often a narrow one, so the table gets a scroll container here rather than
   losing its right-hand columns off the edge. Wrapped at transplant time, so the
   server-rendered markup stays untouched. */
#report .tablewrap { overflow-x: auto; }
"""

# The app's postMessage client. Hand-rolled rather than bundling
# @modelcontextprotocol/ext-apps: that is a Node build, and this server ships no
# JS toolchain. The spec sanctions it -- "You can implement the postMessage protocol
# directly if you prefer to avoid dependencies".
_APP_JS = r"""
(function () {
  /*__DIAG__*/
  var statusEl = document.getElementById("status");
  var reportEl = document.getElementById("report");
  var nextId = 1;
  var pending = {};
  var settled = false;

  function post(msg) { window.parent.postMessage(msg, "*"); }

  function request(method, params) {
    var id = nextId++;
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      post({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
    });
  }

  function say(text, state) {
    statusEl.textContent = text;
    if (state) { statusEl.setAttribute("data-state", state); }
    else { statusEl.removeAttribute("data-state"); }
    statusEl.hidden = false;
  }

  function fail(text, url) {
    if (settled) { return; }
    say(text, "error");
    if (url) {
      var p = document.createElement("p");
      p.id = "fallback-link";
      var a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener";
      a.textContent = "Open the report in a new tab";
      p.appendChild(a);
      reportEl.appendChild(p);
      reportEl.hidden = false;
    }
  }

  // Transplant the server-rendered body. The fetched document's own <style> is
  // dropped: this page already carries the same stylesheet (extracted from the
  // template) plus the dark layer, and an injected <style> may not survive the
  // host's CSP.
  function show(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var body = doc.body;
    if (!body || !body.children.length) { return false; }
    reportEl.replaceChildren();
    Array.prototype.forEach.call(body.children, function (node) {
      if (node.tagName !== "STYLE" && node.tagName !== "SCRIPT") {
        reportEl.appendChild(document.importNode(node, true));
      }
    });
    Array.prototype.forEach.call(reportEl.querySelectorAll("table"), function (table) {
      var wrap = document.createElement("div");
      wrap.className = "tablewrap";
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
    reportEl.hidden = false;
    statusEl.hidden = true;
    settled = true;
    queueSize();
    [1500, 4000].forEach(function (ms) {
      setTimeout(function () {
        diag("after-show-" + ms, { iframeH: window.innerHeight, iframeW: window.innerWidth,
          contentH: Math.ceil(document.documentElement.getBoundingClientRect().height) });
      }, ms);
    });
    return true;
  }

  function applyTheme(ctx) {
    var theme = ctx && ctx.theme;
    if (theme === "dark" || theme === "light") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  }

  // The tool returns EITHER url or html (never both) -- handle both, so the app
  // works on the fat-URL and no-endpoint paths too.
  function onToolResult(result) {
    if (settled || !result) { return; }
    var data = result.structuredContent || {};
    if (typeof data.html === "string" && data.html) {
      if (show(data.html)) { return; }
    }
    var url = typeof data.url === "string" ? data.url : null;
    if (!url) {
      // Last resort: the short link may only be present as content text.
      var texts = (result.content || []).filter(function (c) { return c.type === "text"; });
      var found = texts.map(function (c) { return /https?:\/\/\S+\/r[/?]\S+/.exec(c.text || ""); })
                       .filter(Boolean)[0];
      url = found ? found[0] : null;
    }
    if (!url) { fail("This result carried no report to display."); return; }
    diagSetOrigin(url);
    say("Loading the report…");
    fetch(url, { mode: "cors", redirect: "follow" })
      .then(function (res) {
        if (!res.ok) { throw new Error("HTTP " + res.status); }
        return res.text();
      })
      .then(function (html) {
        if (!show(html)) { throw new Error("the response was not a report page"); }
      })
      .catch(function (err) {
        fail("The report could not be loaded (" + (err && err.message || err) + ").", url);
      });
  }

  window.addEventListener("message", function (event) {
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") { return; }
    diag("recv", { method: msg.method || null, id: msg.id == null ? null : msg.id,
                   error: msg.error ? (msg.error.message || true) : null });
    if (msg.id != null && pending[msg.id]) {
      var slot = pending[msg.id];
      delete pending[msg.id];
      if (msg.error) { slot.reject(new Error(msg.error.message || "host error")); }
      else { slot.resolve(msg.result); }
      return;
    }
    if (msg.method === "ui/notifications/tool-result") { onToolResult(msg.params); }
  });

  // ---- Sizing -------------------------------------------------------------
  // The host sizes the iframe; the view only reports. With flexible dimensions the host
  // MUST resize to what the view reports via ui/notifications/size-changed -- without it
  // the report sits in the host's default-height pane and scrolls inside it.
  //
  // Measure the <html> box, NOT documentElement.scrollHeight: scrollHeight never reports
  // less than the viewport, so a view that started tall could never shrink. Debounce with
  // setTimeout, not requestAnimationFrame -- a host may throttle rAF in an iframe it is
  // still holding hidden, and then no size would ever be sent.
  var lastW = 0, lastH = 0, sizeTimer = null;
  function reportSize() {
    sizeTimer = null;
    var rect = document.documentElement.getBoundingClientRect();
    var w = Math.ceil(rect.width), h = Math.ceil(rect.height);
    if (w === lastW && h === lastH) { return; }  // only real changes: no resize loops
    lastW = w; lastH = h;
    diag("size-sent", { width: w, height: h, iframeH: window.innerHeight });
    post({ jsonrpc: "2.0", method: "ui/notifications/size-changed",
           params: { width: w, height: h } });
  }
  function queueSize() {
    if (sizeTimer !== null) { return; }
    sizeTimer = setTimeout(reportSize, 50);
  }
  function watchSize() {
    // Fires on the logo loading, the table arriving, a theme switch -- anything that
    // changes the content height. The <html> box is auto-height, so the iframe growing
    // does not change it: no feedback loop.
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(queueSize).observe(document.documentElement);
    }
    queueSize();
  }

  var announced = false;
  function announceReady(hostContext) {
    if (announced) { return; }
    announced = true;
    diag("hostContext", hostContext ? {
      keys: Object.keys(hostContext),
      containerDimensions: hostContext.containerDimensions || null,
      displayMode: hostContext.displayMode || null,
      availableDisplayModes: hostContext.availableDisplayModes || null,
      platform: hostContext.platform || null, theme: hostContext.theme || null
    } : null);
    applyTheme(hostContext);
    post({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} });
    // After `initialized`: a host only starts listening for size changes once the view
    // has announced itself.
    watchSize();
  }

  var APP_INFO = { name: "rcsb-mcp report", version: "__TEMPLATE_VERSION__" };
  var APP_CAPS = { availableDisplayModes: ["inline", "fullscreen"] };

  request("ui/initialize", {
    protocolVersion: "__PROTOCOL_VERSION__",
    // Both shapes on purpose. The normative text says top-level appInfo/appCapabilities;
    // the spec's own example in the same document shows clientInfo/capabilities
    // (ext-apps#634). Sending both costs nothing and avoids betting on one reading.
    appInfo: APP_INFO,
    appCapabilities: APP_CAPS,
    clientInfo: APP_INFO,
    capabilities: { appCapabilities: APP_CAPS }
  }).then(function (result) {
    announceReady(result && result.hostContext);
  }).catch(function () {
    // A rejected ui/initialize MUST NOT leave the view silent. A host that never receives
    // `initialized` keeps the iframe reserved-but-hidden forever -- a permanent deadlock
    // that looks exactly like "the app was ignored". Announce anyway; the tool-result
    // handler still does the real work, and theme just falls back to light.
    announceReady(null);
  });
  // Last resort for a host that never replies at all.
  setTimeout(function () { announceReady(null); }, 2000);
})();
"""


# --------------------------------------------------------------------------
# Beacon: the only way to see inside the pane
# --------------------------------------------------------------------------
# The view cannot be inspected inside claude.ai -- the model cannot see it, and the server
# otherwise never hears from it. This is how the 2026-10-06 rendering and sizing problems
# were actually diagnosed: with RCSB_MCP_REPORT_APP_BEACON on, the app POSTs what the host
# told it (containerDimensions, display modes), every message it received, each size it
# requested and the iframe's ACTUAL size to /diag/beacon, which logs them.
#
# OFF by default, and then nothing ships: the JS hooks compile to no-op stubs and the route
# is not registered -- guarded by test. The endpoint origin comes from the report link in
# the tool result, so the HTML stays cluster-independent; events before that are buffered.
REPORT_APP_BEACON_ENABLED = os.environ.get("RCSB_MCP_REPORT_APP_BEACON", "").strip().lower() in {
    "1",
    "true",
    "yes",
}
BEACON_PATH = "/diag/beacon"
_beacon_log = logging.getLogger("rcsb_mcp.report.app.beacon")

_DIAG_STUBS = "function diag() {}\n  function diagSetOrigin() {}"
_DIAG_BEACON_JS = r"""var diagBuf = [], diagUrl = null;
  function diagSend(recs) {
    try {
      fetch(diagUrl, { method: "POST", mode: "cors", keepalive: true,
        headers: { "Content-Type": "text/plain" }, body: JSON.stringify(recs) })
        .catch(function () {});
    } catch (e) {}
  }
  function diag(evt, data) {
    var rec = { t: Date.now(), evt: evt, data: data };
    if (diagUrl) { diagSend([rec]); } else { diagBuf.push(rec); }
  }
  function diagSetOrigin(url) {
    if (diagUrl || !url) { return; }
    try { diagUrl = new URL(url).origin + "__BEACON_PATH__"; } catch (e) { return; }
    var buffered = diagBuf; diagBuf = [];
    if (buffered.length) { diagSend(buffered); }
  }"""
_DIAG_BEACON = _DIAG_BEACON_JS.replace("__BEACON_PATH__", BEACON_PATH)


def _diag_js() -> str:
    return _DIAG_BEACON if REPORT_APP_BEACON_ENABLED else _DIAG_STUBS


async def _receive_beacon(request: Any) -> Any:
    from starlette.responses import Response

    body = (await request.body())[:8000]
    _beacon_log.warning("report-app beacon %s", body.decode("utf-8", "replace"))
    return Response(status_code=204)


def render_app_html() -> str:
    """Build the single self-contained HTML document served as the ``ui://`` resource."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta name="generator" content="rcsb-mcp report app {TEMPLATE_VERSION}">\n'
        "<title>RCSB PDB report</title>\n<style>\n"
        f"{_template_css()}\n{_DARK_CSS}\n{_APP_CSS}\n"
        "</style>\n</head>\n<body>\n"
        '<div id="status">Connecting…</div>\n'
        '<div id="report" hidden></div>\n'
        "<script>\n"
        + _APP_JS.replace("__PROTOCOL_VERSION__", UI_PROTOCOL_VERSION)
        .replace("__TEMPLATE_VERSION__", TEMPLATE_VERSION)
        .replace("/*__DIAG__*/", _diag_js())
        + "\n</script>\n</body>\n</html>\n"
    )


def register_report_app(mcp: Any) -> None:
    """Attach the ``ui://`` report app resource, when the UI channel is enabled.

    A no-op unless ``RCSB_MCP_ENABLE_REPORT_APP`` is set, so a deployment that has
    not opted in advertises no app resource at all.
    """
    if not UI_APP_ENABLED:
        return

    @mcp.resource(
        APP_RESOURCE_URI,
        name="rcsb_report_app",
        title="RCSB PDB report",
        description="Renders an rcsb_render_report result inline in the conversation.",
        mime_type=APP_MIME_TYPE,
        meta=resource_ui_meta(),
    )
    def report_app() -> str:
        return render_app_html()

    # A chat that cached tools/list before a deploy still points at the PREVIOUS hashed
    # URI. Serve the current app for any version rather than failing that read: newer is
    # always fine, and a failed read leaves the user with no report at all.
    @mcp.resource(
        APP_RESOURCE_PREFIX + "-{version}.html",
        name="rcsb_report_app_any_version",
        mime_type=APP_MIME_TYPE,
        meta=resource_ui_meta(),
    )
    def report_app_any_version(version: str) -> str:
        return render_app_html()

    if REPORT_APP_BEACON_ENABLED:
        mcp.custom_route(BEACON_PATH, methods=["POST"])(_receive_beacon)


def _content_uri(html: str) -> str:
    """`ui://rcsb-mcp/report-<12 hex of sha256(html)>.html` -- see APP_RESOURCE_PREFIX."""
    return f"{APP_RESOURCE_PREFIX}-{hashlib.sha256(html.encode('utf-8')).hexdigest()[:12]}.html"


# Computed once, at import: every replica of one image (and both clusters) agree on it.
APP_RESOURCE_URI = _content_uri(render_app_html())
