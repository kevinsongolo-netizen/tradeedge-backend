"""Pluggable economic-calendar provider (Sprint 12).

Mirrors ``app/chart/vision_provider.py``'s design exactly: an ABC,
a placeholder implementation active by default, real implementations
that only activate once an API key is configured, and one factory
function as the single switch point.

Two real providers exist:

* ``JblankedCalendarProvider`` -- JBlanked's News API (MQL5 feed), see
  https://www.jblanked.com/news/api/docs/calendar/. Free, but their
  free tier is rate-limited to 1 request/day (as of the note on their
  docs page) -- see ``CachingCalendarProvider`` below for how this app
  stays within that limit despite the website polling every 60s.
* ``FinnhubCalendarProvider`` -- Finnhub's economic calendar endpoint
  (``GET /calendar/economic``), see
  https://finnhub.io/docs/api/economic-calendar. Finnhub moved this
  specific endpoint behind their paid plan at some point (confirmed via
  a live 403 Forbidden against a real free-tier key), so this is only
  useful to someone who's paid for it -- kept here rather than deleted
  since the code still works correctly if you have.

Every field read from either provider is defensive (``.get()`` with a
fallback) and any unexpected response shape is wrapped as
``CalendarProviderError`` rather than raising a raw exception or
silently returning wrong data.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from functools import lru_cache
from typing import Any


class CalendarProviderError(Exception):
    """Raised whenever a provider can't produce a usable event list —
    network failure, bad API key, unexpected response shape, etc."""


class CalendarProvider(ABC):
    name: str

    @abstractmethod
    async def get_events(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Returns economic events between ``from_date``/``to_date``
        (``YYYY-MM-DD`` strings), each normalized to:
        ``{"time": iso8601 str, "currency": str, "event": str,
        "impact": "low"|"medium"|"high", "actual": float|None,
        "estimate": float|None, "previous": float|None}``.
        """


class PlaceholderCalendarProvider(CalendarProvider):
    """Active whenever no ``FINNHUB_API_KEY`` is configured. Returns a
    small, clearly-labeled example event so the UI can demonstrate the
    feature honestly, the same way ``PlaceholderVisionProvider`` does
    for the Chart Analysis Engine's screenshot path."""

    name = "placeholder"

    async def get_events(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        return [
            {
                "time": f"{from_date}T12:30:00Z",
                "currency": "USD",
                "event": "PLACEHOLDER — Non-Farm Payrolls (example data)",
                "impact": "high",
                "actual": None,
                "estimate": None,
                "previous": None,
                "isPlaceholder": True,
            }
        ]


class FinnhubCalendarProvider(CalendarProvider):
    """Real economic calendar data via Finnhub's free tier. Lazy import
    of ``httpx`` (already a project dependency) so nothing extra is
    required at install time."""

    name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_events(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        import httpx

        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {"from": from_date, "to": to_date, "token": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # network error, timeout, non-2xx, bad JSON
            raise CalendarProviderError(f"Finnhub calendar request failed: {exc}") from exc

        raw_events = data.get("economicCalendar") if isinstance(data, dict) else None
        if raw_events is None:
            raise CalendarProviderError(
                "Unexpected response shape from Finnhub's economic calendar endpoint "
                "(no 'economicCalendar' field) — the free-tier response format may "
                "have changed; check https://finnhub.io/docs/api/economic-calendar."
            )

        events: list[dict[str, Any]] = []
        for raw in raw_events:
            impact_raw = str(raw.get("impact", "")).lower()
            impact = impact_raw if impact_raw in ("low", "medium", "high") else "low"
            events.append(
                {
                    "time": raw.get("time") or raw.get("date"),
                    "currency": raw.get("country") or raw.get("currency") or "",
                    "event": raw.get("event") or "Unnamed event",
                    "impact": impact,
                    "actual": raw.get("actual"),
                    "estimate": raw.get("estimate"),
                    "previous": raw.get("prev") or raw.get("previous"),
                    "isPlaceholder": False,
                }
            )
        return events


def _parse_jblanked_date(raw: str | None) -> str | None:
    """JBlanked returns MT-style dates like ``2024.02.08 15:30:00`` --
    converts to ISO-8601 so it matches every other provider's shape.
    Falls back to the raw string (rather than dropping the event) if
    the format ever changes underneath us."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y.%m.%d %H:%M:%S").isoformat()
    except ValueError:
        return raw


class JblankedCalendarProvider(CalendarProvider):
    """Real economic calendar data via JBlanked's News API (MQL5 feed) --
    see https://www.jblanked.com/news/api/docs/calendar/. Always used
    through ``CachingCalendarProvider`` (see ``get_calendar_provider``
    below), never called directly on every poll, since their free tier
    is rate-limited to 1 request/day."""

    name = "jblanked"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def get_events(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        import httpx

        url = "https://www.jblanked.com/news/api/mql5/calendar/range/"
        params = {"from": from_date, "to": to_date}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self._api_key}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # network error, timeout, non-2xx, bad JSON
            raise CalendarProviderError(f"JBlanked calendar request failed: {exc}") from exc

        if not isinstance(data, list):
            raise CalendarProviderError(
                "Unexpected response shape from JBlanked's calendar endpoint (expected a "
                "JSON list) -- their free-tier response format may have changed; check "
                "https://www.jblanked.com/news/api/docs/calendar/."
            )

        events: list[dict[str, Any]] = []
        for raw in data:
            impact_raw = str(raw.get("Impact", "")).lower()
            impact = impact_raw if impact_raw in ("low", "medium", "high") else "low"
            events.append(
                {
                    "time": _parse_jblanked_date(raw.get("Date")),
                    "currency": raw.get("Currency") or "",
                    "event": raw.get("Name") or "Unnamed event",
                    "impact": impact,
                    "actual": raw.get("Actual"),
                    "estimate": raw.get("Forecast"),
                    "previous": raw.get("Previous"),
                    "isPlaceholder": False,
                }
            )
        return events


class CachingCalendarProvider(CalendarProvider):
    """Wraps another provider with a simple in-process TTL cache, keyed
    by the (from_date, to_date) range. Needed because free-tier
    economic-calendar providers (JBlanked's free tier caps at 1
    request/day) can't sustain the website's 60-second auto-refresh
    poll without this -- event data for a given date range doesn't
    meaningfully change more than a few times a day anyway (only the
    "actual" value updates after a release), so serving a cached copy
    for a while is a safe trade-off, not a hack. Relies on
    ``get_calendar_provider()`` being ``@lru_cache``-d so the same
    wrapper instance (and its cache) is reused across requests within
    one running process."""

    def __init__(self, inner: CalendarProvider, ttl_seconds: int = 6 * 3600) -> None:
        self._inner = inner
        self._ttl = ttl_seconds
        self._cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
        self.name = inner.name

    async def get_events(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        key = (from_date, to_date)
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached is not None and (now - cached[0]) < self._ttl:
            return cached[1]
        events = await self._inner.get_events(from_date, to_date)
        self._cache[key] = (now, events)
        return events


@lru_cache
def get_calendar_provider() -> CalendarProvider:
    # @lru_cache is load-bearing here, not just an optimization: it's
    # what makes CachingCalendarProvider's internal cache actually
    # persist across requests (the same instance -- and its ``_cache``
    # dict -- is reused for the life of the process) instead of being
    # thrown away and rebuilt on every single call.
    from app.config import get_settings

    settings = get_settings()
    if settings.jblanked_api_key:
        return CachingCalendarProvider(JblankedCalendarProvider(settings.jblanked_api_key))
    if settings.finnhub_api_key:
        return CachingCalendarProvider(FinnhubCalendarProvider(settings.finnhub_api_key))
    return PlaceholderCalendarProvider()
