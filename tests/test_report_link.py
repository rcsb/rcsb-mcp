"""Self-contained report links: the codec (report/link.py) and the /r endpoint.

The endpoint decodes attacker-supplied input on a public route, so the guards are
tested as hard requirements, not nice-to-haves: oversized token, non-base64,
non-gzip, gzip bomb, non-UTF-8, and schema-invalid payloads must all be refused.
"""

from __future__ import annotations

import base64
import gzip
import json
from urllib.parse import urlparse

import pytest
from starlette.testclient import TestClient

from rcsb_mcp.report import link
from rcsb_mcp.report.link import LinkError, MAX_DECOMPRESSED, MAX_ENCODED

# A resolved ReportDocument — what the codec packs and the /r endpoints render.
REPORT = {
    "title": "Iron-type nitrile hydratases",
    "columns": [
        {"key": "pdb_id", "label": "PDB ID", "kind": "pdb_id"},
        {"key": "title", "label": "Title"},
    ],
    "rows": [{"pdb_id": "2AHJ", "title": "NITRILE HYDRATASE COMPLEXED WITH NITRIC OXIDE"}],
}

# What the AGENT sends to the tool: identifiers + reasoning, no table.
TOOL_INPUT = {
    "title": "Iron-type nitrile hydratases",
    "result_type": "entry",
    "results": [{"id": "2AHJ", "evidence": {"grounds": "NITRILE HYDRATASE COMPLEXED WITH NITRIC OXIDE"}}],
}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# --------------------------------------------------------------------------
# Codec
# --------------------------------------------------------------------------


def test_round_trips():
    payload = json.dumps(REPORT)
    assert link.decode_report(link.encode_report(payload)) == payload


def test_encoding_is_deterministic():
    """Same report -> same token, so the link is content-addressed and cacheable."""
    payload = json.dumps(REPORT)
    assert link.encode_report(payload) == link.encode_report(payload)


def test_compression_actually_shrinks_a_repetitive_report():
    payload = json.dumps({**REPORT, "rows": [{"pdb_id": f"{i:04d}", "title": "X-RAY DIFFRACTION structure"} for i in range(40)]})
    token = link.encode_report(payload)
    assert len(token) < len(payload), "encoded token should be smaller than the raw JSON"


@pytest.mark.parametrize(
    "bad, needle",
    [
        ("", "empty"),
        ("x" * (MAX_ENCODED + 1), "exceeds"),
        ("!!!not base64!!!", "base64url"),
        (_b64(b"this is not gzip"), "gzip"),
    ],
)
def test_decode_rejects_malformed(bad, needle):
    with pytest.raises(LinkError, match=needle):
        link.decode_report(bad)


def test_decode_rejects_gzip_bomb():
    """A tiny token that inflates past the cap is refused before it fills memory."""
    bomb = _b64(gzip.compress(b"a" * (MAX_DECOMPRESSED * 40), mtime=0))
    assert len(bomb) < 100_000  # the token itself is small...
    with pytest.raises(LinkError, match="exceeds"):
        link.decode_report(bomb)  # ...but decoding refuses to expand it


def test_decode_rejects_non_utf8():
    with pytest.raises(LinkError, match="UTF-8"):
        link.decode_report(_b64(gzip.compress(b"\xff\xfe\xff", mtime=0)))


def test_decode_accepts_just_under_the_cap():
    payload = "a" * (MAX_DECOMPRESSED - 16)
    assert link.decode_report(_b64(gzip.compress(payload.encode(), mtime=0))) == payload


# --------------------------------------------------------------------------
# /r endpoint
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    # Module-scoped: create_app() wires the FastMCP session-manager lifespan to the
    # module-level `mcp` singleton, which can only be run once per process. The /r
    # route is stateless, so one client is shared across the endpoint tests.
    from rcsb_mcp import server

    with TestClient(server.create_app()) as c:
        yield c


def _token(report: dict) -> str:
    return link.encode_report(json.dumps(report))


def test_endpoint_renders_a_valid_link(client):
    r = client.get("/r", params={"d": _token(REPORT)})
    assert r.status_code == 200
    assert r.text.startswith("<!DOCTYPE html>")
    assert "NITRILE HYDRATASE" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_endpoint_sets_hardening_headers(client):
    r = client.get("/r", params={"d": _token(REPORT)})
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-robots-tag"].startswith("noindex")
    assert r.headers["x-content-type-options"] == "nosniff"


def test_csp_allows_the_masthead_logo_origin(client):
    """The template's logo and the endpoint's CSP are coupled across two modules.

    `default-src 'none'` covers images too, so without an explicit img-src the browser
    silently blocks the masthead logo and it renders as a broken icon -- invisible to
    every server-side test, which is why this pins the pair together. It also pins the
    allowance to that ONE origin: widening it to 'self' or '*' would let crafted report
    text reach for an attacker's host, which `default-src 'none'` exists to prevent.
    """
    from rcsb_mcp.report import ReportDocument, render_report

    csp = client.get("/r", params={"d": _token(REPORT)}).headers["content-security-policy"]
    html = render_report(ReportDocument(title="t"))

    assert 'src="https://cdn.rcsb.org/' in html, "template no longer loads the logo from the CDN"

    # Parse the directive rather than substring-match it: "img-src https:" (a scheme-wide
    # wildcard) is itself a substring of "img-src https://cdn.rcsb.org", so a naive
    # `in` check both mis-fires and misses.
    directives = {
        parts[0]: parts[1:]
        for parts in (d.strip().split() for d in csp.split(";"))
        if parts
    }
    assert directives.get("default-src") == ["'none'"], "the deny-by-default base must stay"
    assert directives.get("img-src") == ["https://cdn.rcsb.org"], (
        f"img-src must name the logo's origin and nothing else, got {directives.get('img-src')!r}. "
        "Without it the browser blocks the masthead logo; widened to 'self'/'*'/'https:' the "
        "page could be made to fetch from a host an attacker chose."
    )


def test_endpoint_escapes_hostile_report_text(client):
    """The template escapes every value, so crafted text can never become markup."""
    hostile = {**REPORT, "title": "<script>alert(1)</script>"}
    r = client.get("/r", params={"d": _token(hostile)})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


@pytest.mark.parametrize("d", ["", "!!!bad!!!", _b64(b"not gzip")])
def test_endpoint_rejects_bad_tokens(client, d):
    r = client.get("/r", params={"d": d}) if d else client.get("/r")
    assert r.status_code == 400


def test_endpoint_rejects_wellformed_but_wrong_schema(client):
    r = client.get("/r", params={"d": link.encode_report('{"not": "a report"}')})
    assert r.status_code == 400
    assert "could not render" in r.text.lower()


def test_endpoint_rejects_bomb(client):
    bomb = _b64(gzip.compress(b"a" * (MAX_DECOMPRESSED * 40), mtime=0))
    assert client.get("/r", params={"d": bomb}).status_code == 400


def test_endpoint_rejects_unknown_fields(client):
    """The schema is strict (extra=forbid): a stray field is a 400, not a 500."""
    token = link.encode_report(json.dumps({
        "title": "x",
        "result_type": "entry",
        "results": [{"id": "AAAA"}],
        "collection": {"return_type": "entry"},  # removed field
    }))
    r = client.get("/r", params={"d": token})
    assert r.status_code == 400


def test_endpoint_error_responses_are_hardened(client):
    r = client.get("/r", params={"d": "!!!bad!!!"})
    assert r.status_code == 400
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-robots-tag"].startswith("noindex")


# --------------------------------------------------------------------------
# /r/<id> short link: redirect to the self-contained URL, or an "expired" page
# --------------------------------------------------------------------------


def test_short_id_redirects_to_the_self_contained_url(client):
    from rcsb_mcp.report.store import REPORT_STORE

    token = _token(REPORT)
    uid = REPORT_STORE.put(token)
    r = client.get(f"/r/{uid}", follow_redirects=False)
    assert r.status_code == 302
    # A relative target, so it inherits the caller's host behind any ingress.
    assert r.headers["location"] == f"/r?d={token}"


def test_short_id_followed_renders_the_report(client):
    from rcsb_mcp.report.store import REPORT_STORE

    uid = REPORT_STORE.put(_token(REPORT))
    r = client.get(f"/r/{uid}", follow_redirects=True)
    assert r.status_code == 200
    assert "NITRILE HYDRATASE" in r.text


def test_unknown_short_id_shows_expired_page(client):
    r = client.get("/r/" + "a" * 16, follow_redirects=False)
    assert r.status_code == 410
    assert "expired" in r.text.lower()
    assert r.headers["cache-control"] == "no-store", "never cache a transient miss"
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("bad", ["has%20space", "x" * 65, "no.dots"])
def test_malformed_short_id_shows_expired_page(client, bad):
    """A single-segment id that fails the charset/length gate is a 410, not a 500."""
    r = client.get(f"/r/{bad}", follow_redirects=False)
    assert r.status_code == 410


# --------------------------------------------------------------------------
# End-to-end: the tool's link resolves at the endpoint to the same document
# --------------------------------------------------------------------------


def test_tool_short_link_renders_at_endpoint(client, monkeypatch):
    """The exact short link the tool emits must resolve and render at /r/<id>."""
    import asyncio

    from mcp.server.fastmcp import FastMCP

    from rcsb_mcp.report import routes as report_routes
    from rcsb_mcp.report import tools as report_tools
    from rcsb_mcp.report.store import InMemoryReportStore

    # A shared store so the tool takes the short-link path; the SAME instance must back
    # the endpoint (the tool writes it, /r/<id> reads it — the route resolves REPORT_STORE
    # via report.routes' globals now, so patch it there).
    store = InMemoryReportStore()
    store.shared = True
    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://reports.example.org")
    monkeypatch.setattr(report_tools, "REPORT_STORE", store)
    monkeypatch.setattr(report_routes, "REPORT_STORE", store)

    mcp = FastMCP("test")
    report_tools.register_report_tools(mcp)
    _c, res = asyncio.run(mcp.call_tool("rcsb_render_report", {"params": {"report": TOOL_INPUT}}))

    assert "/r?d=" not in res["url"], "the tool hands back the short link, not the fat URL"
    uid = urlparse(res["url"]).path.rsplit("/", 1)[-1]
    r = client.get(f"/r/{uid}", follow_redirects=True)
    assert r.status_code == 200
    assert "NITRILE HYDRATASE" in r.text


def test_tool_never_emits_a_link_the_endpoint_would_reject(monkeypatch):
    """The emit gate must match the endpoint's accept gate.

    A low-entropy report compresses to a tiny URL but its JSON exceeds
    MAX_DECOMPRESSED — which the endpoint refuses. The tool must fall back to html
    rather than hand back a link that 400s (a dead report).
    """
    import asyncio

    from mcp.server.fastmcp import FastMCP

    from rcsb_mcp.report import ReportRequest, tools as report_tools

    monkeypatch.setattr(report_tools, "REPORT_BASE_URL", "https://reports.example.org")
    big = {
        "title": "probe",
        "result_type": "entry",
        "results": [
            {"id": "AAAA", "evidence": {"grounds": "NITRILE HYDRATASE COMPLEXED WITH NITRIC OXIDE"}}
            for _ in range(3000)
        ],
    }
    from rcsb_mcp.report.enrich import build_document

    report_json = asyncio.run(build_document(ReportRequest(**big), None)).model_dump_json(exclude_defaults=True)
    assert len(report_json) > MAX_DECOMPRESSED, "test setup: report must exceed the cap"
    # ... and yet it compresses tiny, which is exactly the trap:
    assert len(link.encode_report(report_json)) < 2000

    mcp = FastMCP("test")
    report_tools.register_report_tools(mcp)
    _c, res = asyncio.run(mcp.call_tool("rcsb_render_report", {"params": {"report": big}}))
    assert res["url"] is None, "must not emit a link the endpoint would reject"
    assert res["html"].startswith("<!DOCTYPE html>")
