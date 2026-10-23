"""Network-free tests for the browser landing page at /mcp and /.

The advertised endpoint URL gets clicked, and a browser's GET used to get the SDK's 406
JSON-RPC error. The middleware must answer exactly those page loads and leave every MCP
request alone, so most of these pin the routing rule rather than the page text.
"""
import asyncio
import pathlib
import sys

from starlette.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from rcsb_mcp.landing import BrowserLandingMiddleware  # noqa: E402

# What Chrome sends on a page load.
BROWSER_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
)


def _client():
    # No `with`: the lifespan (which starts the session manager, and can run only once per
    # process -- see the fixture in test_report_link.py) is not needed for these routes.
    from rcsb_mcp import server

    return TestClient(server.create_app())


def test_browser_get_of_the_endpoint_gets_the_landing_page():
    r = _client().get("/mcp", headers={"Accept": BROWSER_ACCEPT})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Model Context Protocol" in r.text
    assert "http://testserver/mcp" in r.text
    assert "Accept" in r.headers["vary"]
    assert "default-src 'none'" in r.headers["content-security-policy"]


def test_site_root_serves_the_same_page():
    r = _client().get("/", headers={"Accept": BROWSER_ACCEPT})
    assert r.status_code == 200
    assert "http://testserver/mcp" in r.text


def test_forwarded_proto_sets_the_scheme_shown():
    r = _client().get(
        "/mcp", headers={"Accept": BROWSER_ACCEPT, "X-Forwarded-Proto": "https"}
    )
    assert "https://testserver/mcp" in r.text


def test_reflected_host_is_escaped():
    r = _client().get(
        "/mcp", headers={"Accept": BROWSER_ACCEPT, "Host": 'x"><script>alert(1)</script>'}
    )
    assert "<script>" not in r.text
    assert "&lt;script&gt;" in r.text


# --- pass-through: anything that is not a browser page load reaches the MCP app -------- #
def _routed_to_mcp(method: str, path: str, accept: str | None) -> bool:
    reached = []

    async def mcp_app(scope, receive, send):
        reached.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = BrowserLandingMiddleware(mcp_app, mcp_path="/mcp", version="test")
    headers = [(b"accept", accept.encode())] if accept is not None else []
    scope = {
        "type": "http", "method": method, "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": headers, "scheme": "http",
        "server": ("testserver", 80), "client": ("testclient", 1), "root_path": "",
        "http_version": "1.1",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    return bool(reached)


def test_mcp_client_requests_pass_through():
    # Streamable-HTTP POST and the client's SSE GET.
    assert _routed_to_mcp("POST", "/mcp", "application/json, text/event-stream")
    assert _routed_to_mcp("POST", "/mcp", BROWSER_ACCEPT)
    assert _routed_to_mcp("GET", "/mcp", "text/event-stream")
    assert _routed_to_mcp("GET", "/mcp", "text/html, text/event-stream")


def test_non_browser_gets_keep_the_protocol_answer():
    # curl's default, and no Accept at all: still the SDK's 406, not HTML.
    assert _routed_to_mcp("GET", "/mcp", "*/*")
    assert _routed_to_mcp("GET", "/mcp", None)
    assert _routed_to_mcp("GET", "/mcp", "application/json")


def test_browser_gets_elsewhere_are_not_intercepted():
    assert _routed_to_mcp("GET", "/r", BROWSER_ACCEPT)
    assert _routed_to_mcp("GET", "/healthz", BROWSER_ACCEPT)


def test_trailing_slash_is_the_same_endpoint():
    assert not _routed_to_mcp("GET", "/mcp/", BROWSER_ACCEPT)
