"""The MCP App (SEP-1865) surface: the ``ui://`` resource and the tool's ``_meta.ui``.

Two things these guard that are easy to get silently wrong:

* With the feature off, the tool listing must be EXACTLY what it was before. A public
  server should not start advertising a UI channel because a module grew an import.
* ``connectDomains`` must carry BOTH origins. The short link is minted against the
  cluster-pinned host and 302s to the public one, so a fetch touches both; listing
  only one leaves the app failing at whichever hop was omitted -- and it fails as an
  opaque CSP block, not as an error anyone can read.
"""

from __future__ import annotations

import re

import pytest

from rcsb_mcp.report import app as report_app
from rcsb_mcp.report import tools as report_tools
from rcsb_mcp.report.routes import _REPORT_HEADERS


@pytest.fixture
def ui_enabled(monkeypatch):
    monkeypatch.setattr(report_app, "UI_APP_ENABLED", True)


@pytest.fixture
def two_bases(monkeypatch):
    """The production shape: a public base plus a DIFFERENT cluster-pinned one."""
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://mcp.example.org")
    monkeypatch.setattr(report_tools, "REPORT_LINK_BASE_URL", "https://mcp.{coast}.k8s.example.org")
    monkeypatch.setattr(report_tools, "COAST", "west")


# --------------------------------------------------------------------------
# Off by default
# --------------------------------------------------------------------------


def test_the_tool_carries_no_ui_meta_while_the_feature_is_off(monkeypatch):
    monkeypatch.setattr(report_app, "UI_APP_ENABLED", False)
    assert report_app.tool_ui_meta() is None


def test_no_resource_is_registered_while_the_feature_is_off(monkeypatch):
    monkeypatch.setattr(report_app, "UI_APP_ENABLED", False)
    registered = []

    class _Mcp:
        def resource(self, *a, **kw):
            registered.append((a, kw))
            return lambda fn: fn

    report_app.register_report_app(_Mcp())
    assert registered == []


def test_the_resource_is_registered_once_the_feature_is_on(ui_enabled, two_bases):
    registered = []

    class _Mcp:
        def resource(self, uri, **kw):
            registered.append((uri, kw))
            return lambda fn: fn

    report_app.register_report_app(_Mcp())
    uris = [uri for uri, _ in registered]
    assert uris == [report_app.APP_RESOURCE_URI, report_app.APP_RESOURCE_PREFIX + "-{version}.html"]
    for uri, kw in registered:
        assert uri.startswith("ui://")  # the scheme is what marks it as an app
        assert kw["mime_type"] == "text/html;profile=mcp-app"


# --------------------------------------------------------------------------
# The pointer
# --------------------------------------------------------------------------


def test_the_tool_points_at_the_app_resource(ui_enabled):
    meta = report_app.tool_ui_meta()
    assert meta["ui"]["resourceUri"] == report_app.APP_RESOURCE_URI
    assert report_app.APP_RESOURCE_URI.startswith("ui://")


def test_the_tool_also_carries_the_legacy_flat_key(ui_enabled):
    """`ui/resourceUri` beside the nested `ui.resourceUri`.

    The official ext-apps example still emits both; a host that only reads the flat
    alias would otherwise see no app at all.
    """
    assert report_app.tool_ui_meta()["ui/resourceUri"] == report_app.APP_RESOURCE_URI


def test_the_tool_stays_visible_to_the_model(ui_enabled):
    """`visibility` must not be narrowed to ["app"].

    The short link is the deliverable on every client that cannot render an app, so
    dropping "model" would take the tool out of the agent's list and strand them.
    """
    assert "visibility" not in report_app.tool_ui_meta()["ui"]


# --------------------------------------------------------------------------
# CSP
# --------------------------------------------------------------------------


def test_connect_domains_carry_both_the_public_and_the_pinned_origin(two_bases):
    origins = report_app.app_connect_origins()
    assert "https://mcp.example.org" in origins
    assert "https://mcp.west.k8s.example.org" in origins


def test_connect_domains_collapse_to_one_origin_when_the_bases_agree(monkeypatch):
    """Not a duplicate-origin list when only one base is configured."""
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://mcp.example.org")
    monkeypatch.setattr(report_tools, "REPORT_LINK_BASE_URL", None)
    assert report_app.app_connect_origins() == ["https://mcp.example.org"]


def test_connect_domains_are_bare_origins_not_full_urls(two_bases):
    """A CSP source is scheme://host[:port]; a path makes the directive useless."""
    for origin in report_app.app_connect_origins():
        assert re.fullmatch(r"https?://[^/]+", origin), origin


def test_resource_domains_match_what_the_report_page_actually_loads(two_bases):
    """Coupled to the /r endpoint's own img-src, which is coupled to the template.

    The app renders the SAME markup, so the moment the page is allowed a new image
    origin, the app must be too -- or the masthead silently goes blank inside the app
    while still working in a browser tab.
    """
    img_src = re.search(r"img-src ([^;]+);", _REPORT_HEADERS["Content-Security-Policy"]).group(1)
    assert set(report_app.resource_ui_meta()["ui"]["csp"]["resourceDomains"]) == set(img_src.split())


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def test_the_stylesheet_is_extracted_from_the_template_not_copied(two_bases):
    """Mutating the template must move the app. Guards against a drifting copy."""
    from importlib.resources import files

    source = (files("rcsb_mcp.report") / "templates" / "report.html.j2").read_text("utf-8")
    template_css = re.search(r"<style>(.*?)</style>", source, re.S).group(1).strip()
    assert template_css in report_app.render_app_html()


def test_the_app_speaks_the_handshake_it_declares(two_bases):
    script = _script()
    assert report_app.UI_PROTOCOL_VERSION in report_app.render_app_html()
    # Call sites, not prose: every one of these names also appears in a comment, so a
    # bare substring check would pass with the code itself broken.
    for call in (
        'request("ui/initialize"',
        'method: "ui/notifications/initialized"',
        'msg.method === "ui/notifications/tool-result"',
    ):
        assert call in script, call


def test_the_app_handles_both_results_the_tool_can_return(two_bases):
    """url XOR html -- the app must not assume the link path (see RenderReportResult)."""
    html = report_app.render_app_html()
    assert "data.html" in html
    assert "data.url" in html


def test_the_app_always_announces_initialized_even_if_initialize_fails(two_bases):
    """A rejected ui/initialize must not leave the view silent.

    A host that never receives `ui/notifications/initialized` keeps the iframe
    reserved-but-hidden forever, which is indistinguishable from the app being ignored.
    So the catch branch must announce too, and a timeout must cover a host that never
    replies at all. Guards the exact deadlock that shipped in the first version.
    """
    script = re.search(r"<script>(.*?)</script>", report_app.render_app_html(), re.S).group(1)
    # Scope to the handshake: in diagnostics mode the beacon has its own `.catch(` earlier
    # in the script, and matching the first one would inspect the wrong branch.
    handshake = script[script.index('request("ui/initialize"'):]
    catch = re.search(r"\.catch\(function \(\) \{(.*?)\}\);", handshake, re.S)
    assert catch and "announceReady" in catch.group(1), "catch branch does not announce"
    assert "setTimeout(function () { announceReady(null); }" in script, "no timeout fallback"


def test_the_app_sends_both_handshake_param_shapes(two_bases):
    """appInfo/appCapabilities is the normative shape; clientInfo/capabilities is what the
    spec's own example shows (ext-apps#634). Send both rather than bet on one."""
    script = re.search(r"<script>(.*?)</script>", report_app.render_app_html(), re.S).group(1)
    for field in ("appInfo:", "appCapabilities:", "clientInfo:", "capabilities:"):
        assert field in script, field


def test_the_resource_uri_ends_in_html():
    """Kept because the first render followed the rename `report` -> `report.html`.

    That rename ALSO busted Claude's cache of a broken earlier app, and nothing logged
    tells the two explanations apart -- so the suffix is not known to matter. It costs
    nothing and matches both official examples, so it stays until proven irrelevant.
    """
    assert report_app.APP_RESOURCE_URI.endswith(".html")


def test_the_resource_uri_is_content_addressed():
    """claude.ai caches the app by URI, across fresh chats: after a deploy that changed
    the app, Claude ran the tool and never re-read the resource, so it rendered the OLD
    app. Every change to the HTML must therefore produce a URI Claude has not seen."""
    html = report_app.render_app_html()
    assert report_app.APP_RESOURCE_URI == report_app._content_uri(html)
    assert report_app._content_uri(html) == report_app._content_uri(html)  # stable
    assert report_app._content_uri(html + " ") != report_app._content_uri(html)


def test_the_hash_ignores_cluster_specific_csp(monkeypatch):
    """connectDomains differs between west and east in production; if it fed the hash,
    each cluster would publish a different URI and a GSLB-split listing/read would miss."""
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://a.example.org")
    first = report_app._content_uri(report_app.render_app_html())
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://b.example.org")
    assert report_app._content_uri(report_app.render_app_html()) == first


def test_a_stale_version_uri_still_serves_the_current_app(ui_enabled):
    """A chat that cached tools/list before a deploy points at the previous hash."""
    import asyncio

    from mcp.server.fastmcp import FastMCP

    server = FastMCP("t")
    report_app.register_report_app(server)

    async def read(uri):
        return list(await server.read_resource(uri))[0].content

    current = asyncio.run(read(report_app.APP_RESOURCE_URI))
    assert asyncio.run(read(report_app.APP_RESOURCE_PREFIX + "-0123456789ab.html")) == current


def test_the_beacon_never_ships_while_it_is_off():
    """The beacon posts host details to the server. Off by default, it must leave no trace:
    the JS hooks compile to no-op stubs, so the calls sprinkled through the app stay
    harmless."""
    assert not report_app.REPORT_APP_BEACON_ENABLED  # the suite runs with it off
    html = report_app.render_app_html()
    assert report_app.BEACON_PATH not in html
    assert "function diag() {}" in html


def _registrations():
    calls = {"resources": [], "routes": []}

    class _Mcp:
        def resource(self, uri, **kw):
            calls["resources"].append(uri)
            return lambda fn: fn

        def custom_route(self, path, methods):
            calls["routes"].append((path, tuple(methods)))
            return lambda fn: fn

    return _Mcp(), calls


def test_the_beacon_route_is_not_registered_while_it_is_off(ui_enabled):
    mcp, calls = _registrations()
    report_app.register_report_app(mcp)
    assert calls["routes"] == []


def test_switching_the_beacon_on_wires_the_script_and_the_route_together(ui_enabled, monkeypatch):
    """The hook points are only worth keeping if one flag brings them back whole: a script
    that posts to a route nobody registered would fail silently inside the pane."""
    monkeypatch.setattr(report_app, "REPORT_APP_BEACON_ENABLED", True)
    mcp, calls = _registrations()
    report_app.register_report_app(mcp)
    assert calls["routes"] == [(report_app.BEACON_PATH, ("POST",))]

    script = _script()
    assert 'new URL(url).origin + "' + report_app.BEACON_PATH + '"' in script
    assert "__BEACON_PATH__" not in script


def _script():
    return re.search(r"<script>(.*?)</script>", report_app.render_app_html(), re.S).group(1)


def test_the_app_reports_its_content_size_to_the_host(two_bases):
    """Without ui/notifications/size-changed the host keeps its default-height pane and
    the report scrolls inside it -- the first thing a user noticed once it rendered."""
    script = _script()
    # The call site, not the comment above it that names the same method.
    assert 'method: "ui/notifications/size-changed"' in script
    assert "new ResizeObserver(" in script


def test_size_is_measured_from_the_html_box_not_scroll_height(two_bases):
    """documentElement.scrollHeight never reports less than the viewport, so a view that
    started tall could never shrink to fit a short report."""
    script = _script()
    measure = re.search(r"function reportSize\(\) \{(.*?)\n  \}", script, re.S).group(1)
    assert "getBoundingClientRect" in measure
    assert "scrollHeight" not in measure


def test_size_reports_are_not_debounced_on_animation_frames(two_bases):
    """A host may throttle requestAnimationFrame in an iframe it is still holding hidden;
    then no size would ever be sent and the pane would never grow."""
    assert "requestAnimationFrame(" not in _script()  # a call, not the comment explaining why


def test_the_scrollbar_gutter_is_reserved(two_bases):
    """Without a stable gutter the view's width depends on whether it momentarily
    overflows, the table rewraps, the height changes, and host and view chase each
    other (measured 2342 -> 2381 -> 2342 px)."""
    assert "scrollbar-gutter: stable" in report_app.render_app_html()


def test_the_app_carries_no_second_renderer(two_bases):
    """The app transplants server-rendered markup; it must not build rows itself.

    A JS port was prototyped and rejected (Python str(2.0) is "2.0", JavaScript
    String(2.0) is "2"), so a <td> or <tr> built in the app is the regression.
    """
    script = re.search(r"<script>(.*?)</script>", report_app.render_app_html(), re.S).group(1)
    assert "<td" not in script
    assert "<tr" not in script
