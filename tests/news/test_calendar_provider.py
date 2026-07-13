"""Unit tests for app/news/calendar_provider.py — placeholder output,
factory key-based switching, and (mocked, no real network call) that
FinnhubCalendarProvider wraps failures as CalendarProviderError."""
import pytest

from app.config import get_settings
from app.news.calendar_provider import (
    CalendarProviderError,
    FinnhubCalendarProvider,
    PlaceholderCalendarProvider,
    get_calendar_provider,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_placeholder_provider_labels_output_as_placeholder():
    provider = PlaceholderCalendarProvider()
    events = await provider.get_events("2026-07-11", "2026-07-15")
    assert len(events) == 1
    assert events[0]["isPlaceholder"] is True
    assert "PLACEHOLDER" in events[0]["event"]


def test_factory_returns_placeholder_when_no_api_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    provider = get_calendar_provider()
    assert isinstance(provider, PlaceholderCalendarProvider)


def test_factory_returns_finnhub_when_api_key_set(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "fake-test-key-not-real")
    provider = get_calendar_provider()
    assert isinstance(provider, FinnhubCalendarProvider)


@pytest.mark.asyncio
async def test_finnhub_provider_wraps_network_failure(monkeypatch):
    provider = FinnhubCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError("simulated network failure")

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    with pytest.raises(CalendarProviderError):
        await provider.get_events("2026-07-11", "2026-07-15")


@pytest.mark.asyncio
async def test_finnhub_provider_wraps_unexpected_response_shape(monkeypatch):
    provider = FinnhubCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpectedKey": []}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    with pytest.raises(CalendarProviderError, match="Unexpected response shape"):
        await provider.get_events("2026-07-11", "2026-07-15")


@pytest.mark.asyncio
async def test_finnhub_provider_parses_valid_response(monkeypatch):
    provider = FinnhubCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "economicCalendar": [
                    {
                        "time": "2026-07-13 12:30:00",
                        "country": "US",
                        "event": "Non-Farm Payrolls",
                        "impact": "high",
                        "actual": 200000,
                        "estimate": 180000,
                        "prev": 175000,
                    }
                ]
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    events = await provider.get_events("2026-07-11", "2026-07-15")
    assert len(events) == 1
    assert events[0]["event"] == "Non-Farm Payrolls"
    assert events[0]["impact"] == "high"
    assert events[0]["isPlaceholder"] is False
