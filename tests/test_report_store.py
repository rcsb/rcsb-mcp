"""The short-link store (report/store.py): url_id derivation, TTL, eviction.

The store bridges the tool call to the first browser click for the short /r/<id>
link. It is intentionally lossy (TTL + cap): a miss degrades to the fat URL or the
"expired" page, never to a crash — so the guarantees tested here are id stability,
honest expiry, and a bounded footprint.
"""

from __future__ import annotations

import time

from rcsb_mcp.report.store import (
    URL_ID_RE,
    InMemoryReportStore,
    RedisReportStore,
    build_report_store,
    url_id_for,
)


# --------------------------------------------------------------------------
# url_id: content-addressed and stable
# --------------------------------------------------------------------------


def test_url_id_is_deterministic_and_content_addressed():
    assert url_id_for("some-token") == url_id_for("some-token")
    assert url_id_for("a") != url_id_for("b")


def test_url_id_is_a_short_urlsafe_string():
    uid = url_id_for("some-token")
    assert len(uid) == 16
    assert URL_ID_RE.match(uid)
    assert "=" not in uid and "/" not in uid and "+" not in uid


# --------------------------------------------------------------------------
# In-memory store: round trip, idempotency, expiry, eviction
# --------------------------------------------------------------------------


def test_put_then_get_round_trips():
    store = InMemoryReportStore()
    uid = store.put("the-token")
    assert store.get(uid) == "the-token"


def test_put_is_idempotent_for_identical_content():
    store = InMemoryReportStore()
    a = store.put("same")
    b = store.put("same")
    assert a == b
    assert len(store._data) == 1


def test_get_miss_returns_none():
    assert InMemoryReportStore().get("nope") is None


# --------------------------------------------------------------------------
# `shared`: the flag the tool gates short links on (the dead-link fix)
# --------------------------------------------------------------------------


def test_in_memory_store_is_not_shared_by_default():
    assert InMemoryReportStore().shared is False


def test_redis_store_is_shared():
    assert RedisReportStore.shared is True


def test_env_override_marks_in_memory_store_shared(monkeypatch):
    """A single-process operator can opt the in-memory store into short links."""
    monkeypatch.delenv("RCSB_MCP_REDIS_URL", raising=False)
    monkeypatch.setenv("RCSB_MCP_REPORT_SHARED_STORE", "true")
    store = build_report_store()
    assert isinstance(store, InMemoryReportStore)
    assert store.shared is True


def test_no_override_keeps_in_memory_store_unshared(monkeypatch):
    monkeypatch.delenv("RCSB_MCP_REDIS_URL", raising=False)
    monkeypatch.delenv("RCSB_MCP_REPORT_SHARED_STORE", raising=False)
    store = build_report_store()
    assert isinstance(store, InMemoryReportStore)
    assert store.shared is False


def test_broken_redis_ignores_the_shared_override(monkeypatch):
    """Redis intended but unbuildable (missing pkg / bad URL) must fall back to a SAFE
    shared=False store even if RCSB_MCP_REPORT_SHARED_STORE is set — else a multi-replica
    deploy re-opens the cross-replica dead-link bug.

    Uses a MALFORMED SCHEME so construction fails deterministically either way: with
    redis installed `from_url` raises ValueError, without it the lazy import raises
    ImportError. (A well-formed host must NOT be used here — `from_url` is lazy and
    constructs fine without connecting, so the store would come back shared=True.)
    """
    monkeypatch.setenv("RCSB_MCP_REDIS_URL", "rdis://typo:6379")
    monkeypatch.setenv("RCSB_MCP_REPORT_SHARED_STORE", "true")
    store = build_report_store()
    assert isinstance(store, InMemoryReportStore)
    assert store.shared is False, "a set-but-broken Redis URL must NOT yield a shared in-memory store"


def test_expired_entry_is_not_returned():
    store = InMemoryReportStore(ttl_seconds=100)
    uid = store.put("tok")
    assert store.get(uid) == "tok"
    # Force the stored expiry into the past; get must drop and miss.
    token, _ = store._data[uid]
    store._data[uid] = (token, time.time() - 1)
    assert store.get(uid) is None
    assert uid not in store._data, "an expired entry is purged on read"


def test_store_is_bounded_by_max_entries():
    store = InMemoryReportStore(max_entries=3)
    ids = [store.put(f"token-{i}") for i in range(10)]
    assert len(store._data) <= 3
    # The most recent put has the latest expiry, so it survives eviction.
    assert store.get(ids[-1]) == "token-9"


# --------------------------------------------------------------------------
# Redis-backed store: happy path via an injected client, and error-degradation
# --------------------------------------------------------------------------


class _FakeRedis:
    """Minimal stand-in for redis.Redis — enough to exercise put/get + SETEX."""

    def __init__(self):
        self.kv: dict[str, bytes] = {}
        self.last_ex = None

    def set(self, key, value, ex=None):
        self.kv[key] = value.encode() if isinstance(value, str) else value
        self.last_ex = ex

    def get(self, key):
        return self.kv.get(key)


class _BrokenRedis:
    def set(self, *a, **k):
        raise ConnectionError("redis down")

    def get(self, *a, **k):
        raise ConnectionError("redis down")


def test_redis_store_put_get_round_trip_with_ttl():
    fake = _FakeRedis()
    store = RedisReportStore("redis://ignored", ttl_seconds=42, client=fake)
    uid = store.put("tok")
    assert uid == url_id_for("tok")
    assert store.get(uid) == "tok"
    assert fake.last_ex == 42, "must SETEX with the configured TTL"
    assert "rcsb:report:" in next(iter(fake.kv)), "keys are namespaced"


def test_redis_store_get_miss_returns_none():
    store = RedisReportStore("redis://ignored", client=_FakeRedis())
    assert store.get("absent") is None


def test_redis_store_degrades_to_none_on_errors():
    """A store outage must return None (→ fat-URL fallback / expired page), not raise."""
    store = RedisReportStore("redis://ignored", client=_BrokenRedis())
    assert store.put("tok") is None
    assert store.get("whatever") is None


# --------------------------------------------------------------------------
# url_id validation regex (the endpoint's fast-reject gate)
# --------------------------------------------------------------------------


def test_url_id_re_rejects_junk():
    assert URL_ID_RE.match("AbC-_9" * 2)
    assert not URL_ID_RE.match("has/slash")
    assert not URL_ID_RE.match("has space")
    assert not URL_ID_RE.match("")
    assert not URL_ID_RE.match("x" * 65)


def test_url_id_re_rejects_trailing_newline():
    """`$` would allow one trailing newline; the gate uses `\\Z` and must not."""
    assert not URL_ID_RE.match("validlookingid\n")
