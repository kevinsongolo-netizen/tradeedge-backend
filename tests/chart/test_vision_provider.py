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


def _fake_response_with_text(text: str):
    class _Block:
        type = "text"

    block = _Block()
    block.text = text

    class _Response:
        content = [block]

    return _Response()


@pytest.mark.asyncio
async def test_anthropic_provider_parses_plain_json_response(monkeypatch):
    """The happy path: Claude follows the "respond with ONLY JSON"
    instruction exactly."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "XAUUSD", "timeframe": "M15", "orderDirection": "SELL",
        "orderType": "Sell Limit", "entry": 4001.14, "stopLoss": 4010.33,
        "takeProfit": 3982.77, "riskReward": 1.99, "lots": 0.06,
        "poiType": "Bearish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["pair"] == "XAUUSD"
    assert result["isPlaceholder"] is False


@pytest.mark.asyncio
async def test_anthropic_provider_recovers_json_wrapped_in_markdown_fence(monkeypatch):
    """Sprint 20 fix: vision models sometimes wrap the JSON answer in a
    ```json fence despite being told not to -- this used to raise
    'Vision model did not return valid JSON' and should now parse fine."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    fenced = '```json\n{"trend": "Bullish", "structure": "Bullish", ' \
             '"currentPriceContext": "x", "liquidity": "x", "latestEvent": null, ' \
             '"fvgStatus": null, "premiumDiscount": "Discount", "bias": "BUY", ' \
             '"readConfidence": 70, "pair": "GOLDmicro", "timeframe": "M15", ' \
             '"orderDirection": "SELL", "orderType": "Sell Limit", "entry": 4001.14, ' \
             '"stopLoss": 4010.33, "takeProfit": 3982.77, "riskReward": 1.99, ' \
             '"lots": 0.06, "poiType": "Bearish Order Block"}\n```'

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(fenced)

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["pair"] == "GOLDmicro"


@pytest.mark.asyncio
async def test_anthropic_provider_recovers_json_with_stray_surrounding_text(monkeypatch):
    """Sprint 20 fix: a stray sentence before/after the JSON object
    (no code fence) should also be recovered rather than failing."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    wrapped = (
        'Here is the analysis:\n'
        '{"trend": "Ranging", "structure": "Ranging", "currentPriceContext": "x", '
        '"liquidity": "x", "latestEvent": null, "fvgStatus": null, '
        '"premiumDiscount": "Equilibrium", "bias": "NONE", "readConfidence": 40, '
        '"pair": "EURUSD", "timeframe": "H1", "orderDirection": null, '
        '"orderType": null, "entry": null, "stopLoss": null, "takeProfit": null, '
        '"riskReward": null, "lots": null, "poiType": null}\n'
        'Let me know if you need anything else.'
    )

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(wrapped)

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_anthropic_provider_raises_clean_error_on_genuinely_unparseable_response(monkeypatch):
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text("I'm not able to read this chart clearly.")

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    with pytest.raises(VisionProviderError, match="valid JSON"):
        await provider.analyze_screenshot(b"fake-bytes", "image/png")


@pytest.mark.asyncio
async def test_placeholder_provider_includes_number_consistency_key():
    """Field always present (None when nothing to flag) so the frontend
    and schema can rely on it existing."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    assert result["numberConsistencyWarning"] is None


@pytest.mark.asyncio
async def test_anthropic_provider_flags_sell_stop_loss_below_entry(monkeypatch):
    """A SELL's stop loss must sit above entry (protects against price
    rising against the short) -- if the vision model reads a SL below
    entry, that's internally impossible and should be flagged, not
    silently trusted (this is the bug a real user hit: GOLDmicro SELL
    read with entry 63815.43 / SL 26276 -- SL on the wrong side)."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "SELL", "readConfidence": 90,
        "pair": "GOLDmicro", "timeframe": "M15", "orderDirection": "SELL",
        "orderType": "Sell Limit", "entry": 63815.43, "stopLoss": 26276,
        "takeProfit": 63025.16, "riskReward": None, "lots": 0.06,
        "poiType": "Bearish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["numberConsistencyWarning"] is not None
    assert "SELL" in result["numberConsistencyWarning"]


@pytest.mark.asyncio
async def test_anthropic_provider_recomputes_risk_reward_deterministically(monkeypatch):
    """When SL/TP are on the correct side of entry, riskReward is
    recomputed from the numbers in Python (exact arithmetic) rather than
    trusting whatever ratio the vision model stated."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "SELL", "readConfidence": 90,
        "pair": "XAUUSD", "timeframe": "M15", "orderDirection": "SELL",
        "orderType": "Sell Limit", "entry": 4001.14, "stopLoss": 4010.33,
        "takeProfit": 3982.77, "riskReward": 999,  # deliberately wrong -- should be overridden
        "lots": 0.06, "poiType": "Bearish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["numberConsistencyWarning"] is None
    expected = round(abs(3982.77 - 4001.14) / abs(4001.14 - 4010.33), 2)
    assert result["riskReward"] == expected


@pytest.mark.asyncio
async def test_anthropic_provider_no_warning_when_sl_tp_missing(monkeypatch):
    """No SL/TP read at all (both null) isn't a consistency problem --
    it's just an incomplete read, already visible as '—' in the UI."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "SELL", "readConfidence": 75,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "SELL",
        "orderType": "Sell Limit", "entry": 63572.92, "stopLoss": None,
        "takeProfit": None, "riskReward": None, "lots": None, "poiType": None,
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["numberConsistencyWarning"] is None
