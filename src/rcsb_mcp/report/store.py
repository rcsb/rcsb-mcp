"""Short-TTL store mapping a compact ``url_id`` to a packed report token.

This backs the short report link (Design A). ``rcsb_render_report`` stores the
self-contained report token (see :mod:`rcsb_mcp.report.link`) under a short
``url_id`` and hands the agent a compact ``…/r/<url_id>`` link — cheap for the
model to emit, versus re-emitting the ~2 KB packed URL. The ``/r/<url_id>``
endpoint looks the token up and 302-redirects the browser to the durable,
self-contained ``/r?d=<token>`` URL, which renders with nothing stored. So the
page the user lands on needs no server state and survives eviction; the store
only has to bridge from the tool call to the first click.

**The tool mints a short link ONLY against a store that is shared across replicas.**
The deployment runs several replicas with no session affinity, so the pod that runs
the tool is rarely the pod the browser hits — a link stored on one pod would 410 on
another. Each store therefore advertises ``shared``: the tool emits a short ``/r/<id>``
link only when ``REPORT_STORE.shared`` is true, and otherwise hands back the
self-contained ``/r?d=`` link (correct everywhere, just without the token saving).
This is what makes degradation real: there is no configuration in which the tool emits
a short link the endpoints can't resolve.

* :class:`RedisReportStore` is ``shared = True`` — configure it with ``RCSB_MCP_REDIS_URL``
  to unlock short links across replicas. A runtime Redis error degrades a write to the
  fat URL and a read to the "expired" page.
* :class:`InMemoryReportStore` is ``shared = False`` — process-local, so the tool skips it
  and emits the fat URL. A single-process deployment (local dev, one replica, or sticky
  sessions) can opt it in with ``RCSB_MCP_REPORT_SHARED_STORE=true``.

Env:
* ``RCSB_MCP_REDIS_URL`` — redis:// URL of a shared store; unset ⇒ in-memory.
* ``RCSB_MCP_REPORT_SHARED_STORE`` — treat the in-memory store as shared (single
  process only; UNSAFE across replicas). Ignored when Redis is configured.
* ``RCSB_MCP_REPORT_TTL_SECONDS`` — link lifetime (default 3600).
* ``RCSB_MCP_REPORT_CACHE_MAX`` — in-memory entry cap (default 2048).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import re
import threading
import time
from typing import Protocol

__all__ = [
    "ReportStore",
    "InMemoryReportStore",
    "RedisReportStore",
    "build_report_store",
    "url_id_for",
    "URL_ID_RE",
    "REPORT_STORE",
    "REPORT_TTL_SECONDS",
]

_log = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


REPORT_TTL_SECONDS = _env_int("RCSB_MCP_REPORT_TTL_SECONDS", 3600)
_CACHE_MAX = _env_int("RCSB_MCP_REPORT_CACHE_MAX", 2048)

# url_id is a 12-byte BLAKE2b digest of the token, base64url'd -> exactly 16 chars,
# no padding. 96 bits is collision-safe for a short-TTL cache, and content-addressing
# makes storage idempotent: the same report yields the same id, so re-rendering never
# grows the store and the tool stays idempotent (its idempotentHint).
_URL_ID_BYTES = 12
# The endpoint validates the path segment before touching the store: base64url chars
# only, bounded length. Rejects junk fast and keeps a crafted id from reaching Redis.
# \Z (not $) so a trailing newline can't slip through — $ matches before a final \n.
URL_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")


def url_id_for(token: str) -> str:
    """Deterministic, content-addressed id for a packed report token."""
    digest = hashlib.blake2b(token.encode("ascii"), digest_size=_URL_ID_BYTES).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class ReportStore(Protocol):
    """A short-TTL token store. Both methods degrade to ``None`` on failure."""

    # True only if the store resolves a write from ANY replica (i.e. it is shared and
    # durable enough to bridge the tool call to the click). The tool mints a short link
    # only when this is true; otherwise it emits the self-contained fat URL.
    shared: bool

    def put(self, token: str) -> str | None:
        """Store ``token`` under its content-addressed id; return the id, or None
        if the store is unavailable (caller then emits the fat URL instead)."""

    def get(self, url_id: str) -> str | None:
        """Return the token for ``url_id``, or None if absent, expired, or the
        store is unavailable."""


class InMemoryReportStore:
    """Process-local TTL store. Reliable within one process only.

    Correct for local dev, tests, and a single replica. Across replicas it cannot
    see another pod's writes, so it reports ``shared = False`` and the tool declines
    to mint short links against it (emitting the fat URL instead). A single-process
    operator can flip this on via ``RCSB_MCP_REPORT_SHARED_STORE`` (see build_report_store).
    """

    shared = False

    def __init__(self, ttl_seconds: int = REPORT_TTL_SECONDS, max_entries: int = _CACHE_MAX) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def put(self, token: str) -> str:
        uid = url_id_for(token)
        expiry = time.time() + self._ttl
        with self._lock:
            self._data[uid] = (token, expiry)
            if len(self._data) > self._max:
                self._evict_locked()
        return uid

    def get(self, url_id: str) -> str | None:
        now = time.time()
        with self._lock:
            hit = self._data.get(url_id)
            if hit is None:
                return None
            token, expiry = hit
            if expiry <= now:
                self._data.pop(url_id, None)
                return None
            return token

    def _evict_locked(self) -> None:
        """Drop expired entries first, then the soonest-to-expire until under cap."""
        now = time.time()
        for key in [k for k, (_, exp) in self._data.items() if exp <= now]:
            self._data.pop(key, None)
        if len(self._data) <= self._max:
            return
        overflow = len(self._data) - self._max
        for key, _ in sorted(self._data.items(), key=lambda kv: kv[1][1])[:overflow]:
            self._data.pop(key, None)


class RedisReportStore:
    """Shared TTL store backed by Redis — reliable across replicas.

    Any connectivity or client error degrades to ``None`` rather than raising, so
    a store outage never takes down report rendering: writes fall back to the fat
    URL, reads to the "expired" page.
    """

    shared = True

    def __init__(
        self,
        url: str,
        ttl_seconds: int = REPORT_TTL_SECONDS,
        key_prefix: str = "rcsb:report:",
        client: object | None = None,
    ) -> None:
        if client is None:
            import redis  # lazy: only imported when a shared store is configured

            client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        self._client = client
        self._ttl = ttl_seconds
        self._prefix = key_prefix

    def put(self, token: str) -> str | None:
        uid = url_id_for(token)
        try:
            self._client.set(self._prefix + uid, token, ex=self._ttl)
        except Exception as exc:  # noqa: BLE001 — any redis error must degrade, not raise
            _log.warning("report store write failed, falling back to inline link: %s", exc)
            return None
        return uid

    def get(self, url_id: str) -> str | None:
        try:
            value = self._client.get(self._prefix + url_id)
        except Exception as exc:  # noqa: BLE001 — any redis error must degrade, not raise
            _log.warning("report store read failed: %s", exc)
            return None
        if value is None:
            return None
        return value.decode("ascii") if isinstance(value, (bytes, bytearray)) else str(value)


def build_report_store() -> ReportStore:
    """Pick the store from the environment: Redis if configured, else in-memory.

    Falling back to the in-memory store is SAFE — it reports ``shared = False``, so the
    tool declines short links and emits the self-contained fat URL. Short links are lost,
    but no link is ever dead. ``RCSB_MCP_REPORT_SHARED_STORE=true`` marks the in-memory
    store shared for single-process deployments that can honestly resolve it.
    """
    url = os.environ.get("RCSB_MCP_REDIS_URL", "").strip()
    if url:
        try:
            return RedisReportStore(url)
        except Exception as exc:  # noqa: BLE001 — redis missing/misconfigured: still boot
            _log.warning(
                "RCSB_MCP_REDIS_URL is set but the Redis store could not be built (%s); "
                "using an in-memory store. Short report links are DISABLED (the tool emits "
                "self-contained links instead) until this is fixed.",
                exc,
            )
        # Redis was intended but unavailable: return a SAFE process-local store. Do NOT
        # honor RCSB_MCP_REPORT_SHARED_STORE here — the operator asked for shared Redis on
        # what is presumably a multi-replica deployment, so promoting a process-local store
        # to shared=True would re-open the cross-replica dead-link bug. Emit fat URLs instead.
        return InMemoryReportStore()
    store = InMemoryReportStore()
    if _env_bool("RCSB_MCP_REPORT_SHARED_STORE"):
        store.shared = True  # operator asserts a single process / sticky routing
    return store


# One store per process, shared by the tool (writer) and the /r/<id> route (reader).
REPORT_STORE: ReportStore = build_report_store()
