"""Pluggable economic-calendar provider (Sprint 12).

Mirrors ``app/chart/vision_provider.py``'s design exactly: an ABC,
a placeholder implementation active by default, a real implementation
that only activates once an API key is configured, and one factory
function as the single switch point. ``FinnhubCalendarProvider`` calls
Finnhub's free-tier economic calendar endpoint (``GET
/calendar/economic``) — see https://finnhub.io/docs/api/economic-calendar.
Finnhub's exact free-tier field set can change without notice, so every
field read here is defensive (``.get()`` with a fallback) and any
unexpected shape is wrapped as ``CalendarProviderError`` rather than
raising a raw exception or silently returning wrong data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
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


def get_calendar_provider() -> CalendarProvider:
    from app.config import get_settings

    settings = get_settings()
    if settings.finnhub_api_key:
        return FinnhubCalendarProvider(settings.finnhub_api_key)
    return PlaceholderCalendarProvider()
