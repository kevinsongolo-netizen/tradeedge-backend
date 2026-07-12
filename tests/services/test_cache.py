"""Cache tests — ``app/services/cache.py`` (Sprint 8 audit fix).

Regression coverage for a bug found while writing Sprint 8's coach
deep-dive tests: ``TradeService._invalidate_caches()`` calls
``coach_cache.invalidate(user_id)`` and ``stats_cache.invalidate(user_id)``
with a bare ``user_id``, but every entry these caches actually store is
keyed by a tuple like ``("insights", user_id, limit)`` or
``("summary", user_id)``. The original ``invalidate()`` did an exact
``dict.pop(key, None)``, which never matched those tuple keys — a
silent no-op. ``stats_cache`` (a ``FingerprintCache``) happened to
self-heal on the next read because its fingerprint changes whenever
trades change, but ``coach_cache`` (a plain ``TTLCache``) had no such
safety net: it could serve up to 60 seconds of pre-trade data after a
trade was logged.
"""
import asyncio

from app.services.cache import FingerprintCache, TTLCache


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_ttlcache_invalidate_clears_every_key_for_a_user():
    cache = TTLCache(ttl_seconds=60.0)
    _run(cache.get_or_set(("insights", 1, 6), lambda: "insights-for-1"))
    _run(cache.get_or_set(("deep_dive", 1), lambda: "deep-dive-for-1"))
    _run(cache.get_or_set(("insights", 2, 6), lambda: "insights-for-2"))

    cache.invalidate(1)

    # user 1's entries are gone -> factory re-runs and returns fresh value
    assert _run(cache.get_or_set(("insights", 1, 6), lambda: "fresh-insights-for-1")) == "fresh-insights-for-1"
    assert _run(cache.get_or_set(("deep_dive", 1), lambda: "fresh-deep-dive-for-1")) == "fresh-deep-dive-for-1"
    # user 2's entry is untouched -> still cached, factory does not re-run
    assert _run(cache.get_or_set(("insights", 2, 6), lambda: "should-not-run")) == "insights-for-2"


def test_fingerprintcache_invalidate_clears_every_key_for_a_user():
    cache = FingerprintCache()
    _run(cache.get_or_set(("summary", 1), "fp-a", lambda: "summary-for-1"))
    _run(cache.get_or_set(("charts", 1), "fp-a", lambda: "charts-for-1"))
    _run(cache.get_or_set(("summary", 2), "fp-a", lambda: "summary-for-2"))

    cache.invalidate(1)

    # Same fingerprint as before, but the entries were dropped -> factory reruns.
    assert _run(cache.get_or_set(("summary", 1), "fp-a", lambda: "fresh-summary-for-1")) == "fresh-summary-for-1"
    assert _run(cache.get_or_set(("charts", 1), "fp-a", lambda: "fresh-charts-for-1")) == "fresh-charts-for-1"
    # user 2 untouched
    assert _run(cache.get_or_set(("summary", 2), "fp-a", lambda: "should-not-run")) == "summary-for-2"


def test_ttlcache_invalidate_unknown_user_is_a_safe_noop():
    cache = TTLCache(ttl_seconds=60.0)
    _run(cache.get_or_set(("insights", 1, 6), lambda: "insights-for-1"))
    cache.invalidate(999)  # no entries for user 999
    assert _run(cache.get_or_set(("insights", 1, 6), lambda: "should-not-run")) == "insights-for-1"
