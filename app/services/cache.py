"""Small in-process caches used by the stats/coach services (Section 5.3).

No external cache dependency (Redis etc.) in Sprint 6 — single-process
dev deployment, so a plain dict behind a lock is sufficient. Swapping
to Redis later (Section 13.4) only touches this module.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any


class FingerprintCache:
    """Caches one value per key, invalidated whenever the caller's
    fingerprint for that key changes (Section 5.3: "fingerprint key
    derived from (user_id, len(trades), max(updated_at))")."""

    def __init__(self) -> None:
        self._store: dict[Any, tuple[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: Any, fingerprint: str, factory) -> Any:
        async with self._lock:
            cached = self._store.get(key)
            if cached is not None and cached[0] == fingerprint:
                return cached[1]
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        async with self._lock:
            self._store[key] = (fingerprint, value)
        return value

    def invalidate(self, user_id: Any) -> None:
        """Drops every cached entry for ``user_id``. Cache keys here are
        always tuples like ``("summary", user_id)`` — never the bare
        ``user_id`` itself — so callers that just want "clear this
        user's cache" (e.g. ``TradeService`` after any write) can pass
        the user_id alone rather than needing to know every named key
        (summary/charts/health/setups/mistakes/...) this cache holds."""
        stale = [k for k in self._store if isinstance(k, tuple) and len(k) >= 2 and k[1] == user_id]
        for k in stale:
            self._store.pop(k, None)


class TTLCache:
    """Plain TTL cache — used for the coach insights cache layered on
    top of the stats fingerprint cache (Section 5.3)."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._store: dict[Any, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: Any, factory) -> Any:
        now = time.monotonic()
        async with self._lock:
            cached = self._store.get(key)
            if cached is not None and cached[0] > now:
                return cached[1]
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        async with self._lock:
            self._store[key] = (now + self._ttl, value)
        return value

    def invalidate(self, user_id: Any) -> None:
        """Drops every cached entry for ``user_id`` (e.g. both
        ``("insights", user_id, limit)`` for every ``limit`` a caller
        might have used, and ``("deep_dive", user_id)``) — same
        by-user-id semantics as ``FingerprintCache.invalidate()``.

        BUG FIX (Sprint 8 audit): this used to do
        ``self._store.pop(key, None)`` with ``key`` being the raw
        ``user_id`` passed straight through from
        ``TradeService._invalidate_caches()``. Since every actual
        stored key is a tuple (``("insights", user_id, limit)`` /
        ``("deep_dive", user_id)``), that pop never matched anything —
        ``coach_cache.invalidate(user_id)`` was a silent no-op, so
        ``/coach/insights`` and ``/coach/deep-dive`` could serve up to
        60 seconds of stale data after any trade write. Unlike
        ``stats_cache`` (a ``FingerprintCache``, which self-heals on
        the next call because the fingerprint itself changes when
        trades change), this cache has no fingerprint check, so the
        staleness was real and unmasked."""
        stale = [k for k in self._store if isinstance(k, tuple) and len(k) >= 2 and k[1] == user_id]
        for k in stale:
            self._store.pop(k, None)


# Module-level singletons shared across requests within the same process.
stats_cache = FingerprintCache()
coach_cache = TTLCache(ttl_seconds=60.0)
