"""Unit tests for app/chart/vision_provider.py — the placeholder
provider's output, the factory's key-based switching, and (mocked, no
real network call) that AnthropicVisionProvider raises a clean
VisionProviderError on failure rather than leaking an SDK exception."""
import pytest

from app.chart.vision_provider import (
    AnthropicVisionProvider,
    PlaceholderVisionProvider,
    VisionProviderError,
    get_vision_provider,
)
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_placeholder_provider_labels_output_as_placeholder():
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    assert result["isPlaceholder"] is True
    assert result["provider"] == "placeholder"
    assert "PLACEHOLDER" in result["currentPriceContext"]


@pytest.mark.asyncio
async def test_placeholder_provider_rejects_empty_image():
    provider = PlaceholderVisionProvider()
    with pytest.raises(VisionProviderError):
        await provider.analyze_screenshot(b"", "image/png")


@pytest.mark.asyncio
async def test_placeholder_provider_includes_sprint20_setup_fields():
    """Sprint 20: the vision provider now also reads the trader's own
    pending order/position (pair, timeframe, direction, entry, SL, TP,
    R:R, lots, POI type) off the screenshot, not just chart structure."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    for key in (
        "pair", "timeframe", "orderDirection", "orderType",
        "entry", "stopLoss", "takeProfit", "riskReward", "lots", "poiType",
    ):
        assert key in result


def test_factory_returns_placeholder_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_vision_provider()
    assert isinstance(provider, PlaceholderVisionProvider)


def test_factory_returns_anthropic_when_api_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key-not-real")
    provider = get_vision_provider()
    assert isinstance(provider, AnthropicVisionProvider)


@pytest.mark.asyncio
async def test_anthropic_provider_wraps_api_failure_as_vision_error(monkeypatch):
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                raise RuntimeError("simulated network failure")

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    with pytest.raises(VisionProviderError):
        await provider.analyze_screenshot(b"fake-bytes", "image/png")
