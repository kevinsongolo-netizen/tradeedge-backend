"""Unit tests for app/news/calendar_provider.py — placeholder output,
factory key-based switching (Finnhub now requires a paid plan for the
economic calendar, so JBlanked is checked first), the CachingCalendarProvider
wrapper, and (mocked, no real network calls) that both real providers wrap
failures as CalendarProviderError."""
import pytest

from app.config import get_settings
from app.news.calendar_provider import (
    CachingCalendarProvider,
    CalendarProviderError,
    FinnhubCalendarProvider,
    JblankedCalendarProvider,
    PlaceholderCalendarProvider,
    get_calendar_provider,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    get_calendar_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_calendar_provider.cache_clear()


@pytest.mark.asyncio
async def test_placeholder_provider_labels_output_as_placeholder():
    provider = PlaceholderCalendarProvider()
    events = await provider.get_events("2026-07-11", "2026-07-15")
    assert len(events) == 1
    assert events[0]["isPlaceholder"] is True
    assert "PLACEHOLDER" in events[0]["event"]


def test_factory_returns_placeholder_when_no_api_key(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("JBLANKED_API_KEY", raising=False)
    provider = get_calendar_provider()
    assert isinstance(provider, PlaceholderCalendarProvider)


def test_factory_returns_jblanked_wrapped_in_cache_when_api_key_set(monkeypatch):
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("JBLANKED_API_KEY", "fake-test-key-not-real")
    provider = get_calendar_provider()
    assert isinstance(provider, CachingCalendarProvider)
    assert isinstance(provider._inner, JblankedCalendarProvider)


def test_factory_returns_finnhub_wrapped_in_cache_when_only_finnhub_key_set(monkeypatch):
    monkeypatch.delenv("JBLANKED_API_KEY", raising=False)
    monkeypatch.setenv("FINNHUB_API_KEY", "fake-test-key-not-real")
    provider = get_calendar_provider()
    assert isinstance(provider, CachingCalendarProvider)
    assert isinstance(provider._inner, FinnhubCalendarProvider)


def test_factory_prefers_jblanked_when_both_keys_set(monkeypatch):
    monkeypatch.setenv("FINNHUB_API_KEY", "fake-test-key-not-real")
    monkeypatch.setenv("JBLANKED_API_KEY", "fake-test-key-not-real")
    provider = get_calendar_provider()
    assert isinstance(provider, CachingCalendarProvider)
    assert isinstance(provider._inner, JblankedCalendarProvider)


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


@pytest.mark.asyncio
async def test_jblanked_provider_wraps_network_failure(monkeypatch):
    provider = JblankedCalendarProvider(api_key="fake-test-key-not-real")

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
async def test_jblanked_provider_wraps_unexpected_response_shape(monkeypatch):
    provider = JblankedCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"not": "a list"}

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
async def test_jblanked_provider_parses_valid_response(monkeypatch):
    provider = JblankedCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "Name": "Core CPI m/m",
                    "Currency": "USD",
                    "Category": "Consumer Inflation Report",
                    "Impact": "High",
                    "Date": "2026.07.13 15:30:00",
                    "Actual": 0.4,
                    "Forecast": 0.4,
                    "Previous": 0.2,
                }
            ]

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
    assert events[0]["event"] == "Core CPI m/m"
    assert events[0]["currency"] == "USD"
    assert events[0]["impact"] == "high"
    assert events[0]["time"] == "2026-07-13T15:30:00"
    assert events[0]["actual"] == 0.4
    assert events[0]["isPlaceholder"] is False


@pytest.mark.asyncio
async def test_jblanked_provider_defaults_unknown_impact_to_low(monkeypatch):
    provider = JblankedCalendarProvider(api_key="fake-test-key-not-real")

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "Name": "Some Minor Release",
                    "Currency": "EUR",
                    "Impact": "None",
                    "Date": "2026.07.13 09:00:00",
                }
            ]

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
    assert events[0]["impact"] == "low"


@pytest.mark.asyncio
async def test_caching_provider_reuses_result_within_ttl():
    call_count = {"n": 0}

    class _CountingProvider:
        name = "counting"

        async def get_events(self, from_date, to_date):
            call_count["n"] += 1
            return [{"event": f"call-{call_count['n']}"}]

    provider = CachingCalendarProvider(_CountingProvider(), ttl_seconds=3600)

    first = await provider.get_events("2026-07-11", "2026-07-15")
    second = await provider.get_events("2026-07-11", "2026-07-15")

    assert call_count["n"] == 1
    assert first == second == [{"event": "call-1"}]


@pytest.mark.asyncio
async def test_caching_provider_refetches_after_ttl_expires(monkeypatch):
    call_count = {"n": 0}

    class _CountingProvider:
        name = "counting"

        async def get_events(self, from_date, to_date):
            call_count["n"] += 1
            return [{"event": f"call-{call_count['n']}"}]

    provider = CachingCalendarProvider(_CountingProvider(), ttl_seconds=1)

    fake_now = {"t": 1000.0}

    import app.news.calendar_provider as calendar_provider_module

    monkeypatch.setattr(calendar_provider_module.time, "monotonic", lambda: fake_now["t"])

    first = await provider.get_events("2026-07-11", "2026-07-15")
    fake_now["t"] += 2  # advance past the 1-second TTL
    second = await provider.get_events("2026-07-11", "2026-07-15")

    assert call_count["n"] == 2
    assert first != second


@pytest.mark.asyncio
async def test_caching_provider_separate_date_ranges_cached_independently():
    call_count = {"n": 0}

    class _CountingProvider:
        name = "counting"

        async def get_events(self, from_date, to_date):
            call_count["n"] += 1
            return [{"event": f"call-{call_count['n']}", "range": (from_date, to_date)}]

    provider = CachingCalendarProvider(_CountingProvider(), ttl_seconds=3600)

    await provider.get_events("2026-07-11", "2026-07-15")
    await provider.get_events("2026-07-16", "2026-07-20")

    assert call_count["n"] == 2
