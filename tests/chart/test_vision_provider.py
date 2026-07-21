"""Unit tests for app/chart/vision_provider.py — the placeholder
provider's output, the factory's key-based switching, and (mocked, no
real network call) that AnthropicVisionProvider raises a clean
VisionProviderError on failure rather than leaking an SDK exception."""
import pytest

from app.chart.vision_provider import (
    CONFIDENCE_FIELDS,
    EVIDENCE_FIELDS,
    MAX_CONFIDENCE_FACTORS_PER_FIELD,
    MAX_EVIDENCE_BULLETS_PER_FIELD,
    AnthropicVisionProvider,
    CachingVisionProvider,
    PlaceholderVisionProvider,
    VisionProviderError,
    get_vision_provider,
)
from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    get_vision_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_vision_provider.cache_clear()


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


@pytest.mark.asyncio
async def test_placeholder_provider_includes_sprint20_phase6_characteristics():
    """Sprint 20 Phase 6 -- freshness, rejection strength, and FVG size,
    the three characteristics the trader asked the AI to learn from."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    for key in ("orderBlockFreshness", "rejectionStrength", "fvgSize"):
        assert key in result


@pytest.mark.asyncio
async def test_placeholder_provider_includes_sprint20_phase8_characteristics():
    """Sprint 20 Phase 8 ("AI Learning Engine") -- equal highs/lows,
    BOS type, and touch number."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    for key in ("equalHighsNearby", "equalLowsNearby", "bosType", "touchNumber"):
        assert key in result


@pytest.mark.asyncio
async def test_placeholder_provider_includes_sprint20_phase9_confidence_fields():
    """Sprint 20 Phase 9 ("Confidence-Tiered Reasoning") -- the vision
    model's own honest confidence in its three interpretive judgment
    calls (order block freshness, rejection strength, FVG mitigation),
    separate from the overall readConfidence."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    for key in (
        "orderBlockFreshnessConfidence",
        "rejectionStrengthConfidence",
        "fvgMitigationConfidence",
    ):
        assert key in result
        assert isinstance(result[key], (int, float))


def test_schema_hint_documents_the_three_confidence_fields():
    """The prompt-embedded schema hint must ask the vision model for
    all three confidence fields, or a real Anthropic call would never
    know to supply them."""
    from app.chart.vision_provider import VISION_ANALYSIS_SCHEMA_HINT

    for key in (
        "orderBlockFreshnessConfidence",
        "rejectionStrengthConfidence",
        "fvgMitigationConfidence",
    ):
        assert key in VISION_ANALYSIS_SCHEMA_HINT


def test_anthropic_prompt_instructs_honest_confidence_scoring():
    """The prompt sent to Claude must explicitly instruct it to score
    these three fields low unless it can point to real visible
    evidence, rather than defaulting to a confident-sounding label."""
    provider = AnthropicVisionProvider(api_key="fake-key-for-prompt-test")
    prompt = provider._prompt()
    assert "honest" in prompt.lower()
    assert "confidence" in prompt.lower()


def test_factory_returns_placeholder_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_vision_provider()
    assert isinstance(provider, PlaceholderVisionProvider)


def test_factory_returns_anthropic_when_api_key_set(monkeypatch):
    """Phase 11: the factory now wraps the real provider in a
    CachingVisionProvider (so identical screenshots resolve to one
    shared fingerprint across Pre-Trade Check / Chart Analysis Engine),
    so the returned object is no longer an AnthropicVisionProvider
    instance directly -- check the wrapped provider's .name and inner
    type instead, same convention CachingCalendarProvider already uses."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key-not-real")
    provider = get_vision_provider()
    assert isinstance(provider, CachingVisionProvider)
    assert provider.name == "anthropic"
    assert isinstance(provider._inner, AnthropicVisionProvider)


def test_factory_returns_same_cached_instance_across_calls(monkeypatch):
    """@lru_cache must persist the same CachingVisionProvider instance
    (and therefore the same cache dict) across calls within one process
    -- without this, every request would get a fresh, empty cache and
    the whole point of Phase 11 would be defeated."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key-not-real")
    first = get_vision_provider()
    second = get_vision_provider()
    assert first is second


@pytest.mark.asyncio
async def test_anthropic_provider_wraps_api_failure_as_vision_error(monkeypatch):
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
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
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["numberConsistencyWarning"] is None


# --- Sprint 20 Phase 10 ("Direction/OrderType reconciliation") ---------------

@pytest.mark.asyncio
async def test_buy_limit_order_type_overrides_a_misread_sell_direction(monkeypatch):
    """A trader found the Chart Analysis Engine reporting SELL on the
    exact same 'Buy Limit' screenshot Pre-Trade Check correctly called
    BUY -- orderType and orderDirection are two separate judgment
    calls on one screenshot and can disagree. Since 'Buy Limit'
    unambiguously means BUY by definition, orderDirection must be
    reconciled to BUY regardless of what the model's own orderDirection
    field said."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Premium", "bias": "SELL", "readConfidence": 82,
        "pair": "BTCUSD", "timeframe": "M15",
        # The bug reproduced exactly: model says SELL, but orderType says Buy Limit.
        "orderDirection": "SELL", "orderType": "Buy Limit",
        "entry": 63984.27, "stopLoss": 63784.27, "takeProfit": 64351.35,
        "riskReward": 1.84, "lots": 0.01, "poiType": "Bullish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["orderDirection"] == "BUY"
    # With direction correctly reconciled to BUY, these SL/TP numbers
    # (SL below entry, TP above entry) are perfectly consistent -- no
    # spurious "these numbers look inconsistent with a SELL order"
    # warning should fire on numbers that were never actually wrong.
    assert result["numberConsistencyWarning"] is None


@pytest.mark.asyncio
async def test_sell_stop_order_type_overrides_a_misread_buy_direction(monkeypatch):
    """Mirror case: orderType says Sell Stop but the model's own
    orderDirection guessed BUY -- must reconcile to SELL."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bearish", "structure": "Bearish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 78,
        "pair": "EURUSD", "timeframe": "H1",
        "orderDirection": "BUY", "orderType": "Sell Stop",
        "entry": 1.0850, "stopLoss": 1.0870, "takeProfit": 1.0800,
        "riskReward": 2.5, "lots": 0.1, "poiType": "Bearish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["orderDirection"] == "SELL"
    assert result["numberConsistencyWarning"] is None


@pytest.mark.asyncio
async def test_ambiguous_order_type_leaves_direction_untouched(monkeypatch):
    """A plain 'Market' order type (no buy/sell word) or a null
    orderType is genuinely ambiguous -- must NOT be reconciled, since
    there's nothing in the text to safely derive direction from."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Premium", "bias": "SELL", "readConfidence": 60,
        "pair": "XAUUSD", "timeframe": "M15",
        "orderDirection": "SELL", "orderType": "Market",
        "entry": 4001.14, "stopLoss": 3990.0, "takeProfit": 4020.0,
        "riskReward": None, "lots": 0.06, "poiType": "Bearish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["orderDirection"] == "SELL"


@pytest.mark.asyncio
async def test_caching_vision_provider_reuses_result_for_identical_bytes(monkeypatch):
    """Phase 11: a trader saw the SAME screenshot produce slightly
    different free-text descriptions between Pre-Trade Check and the
    Chart Analysis Engine ("Multiple Bullish FVGs marked on chart,
    appearing mitigated" vs. "Bullish FVG marked and visible on chart")
    because each upload independently called the vision API. With
    CachingVisionProvider, the second call with byte-identical image
    content must return the cached result WITHOUT invoking the inner
    provider again -- guaranteeing every module reads one shared
    fingerprint per screenshot."""
    call_count = {"n": 0}
    payload = {
        "trend": "Bullish", "structure": "Bullish",
        "currentPriceContext": "x", "liquidity": "x",
        "latestEvent": None,
        "fvgStatus": "Bullish FVG marked and visible on chart",
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                call_count["n"] += 1
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    inner = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    provider = CachingVisionProvider(inner)

    image_bytes = b"identical-screenshot-bytes"
    first = await provider.analyze_screenshot(image_bytes, "image/png")
    second = await provider.analyze_screenshot(image_bytes, "image/png")

    assert call_count["n"] == 1
    assert first == second
    assert second["fvgStatus"] == "Bullish FVG marked and visible on chart"


@pytest.mark.asyncio
async def test_caching_vision_provider_calls_inner_again_for_different_bytes(monkeypatch):
    """Different screenshots are different content -- each must still
    get its own, independent analysis rather than colliding on a single
    cache entry."""
    call_count = {"n": 0}
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                call_count["n"] += 1
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    inner = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    provider = CachingVisionProvider(inner)

    await provider.analyze_screenshot(b"screenshot-one", "image/png")
    await provider.analyze_screenshot(b"screenshot-two", "image/png")

    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_caching_vision_provider_expires_after_ttl(monkeypatch):
    """A near-zero TTL should behave like no caching at all -- confirms
    the cache actually respects its expiry window rather than caching
    forever regardless of the configured ttl_seconds."""
    call_count = {"n": 0}
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                call_count["n"] += 1
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    inner = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    provider = CachingVisionProvider(inner, ttl_seconds=0)

    image_bytes = b"identical-screenshot-bytes"
    await provider.analyze_screenshot(image_bytes, "image/png")
    await provider.analyze_screenshot(image_bytes, "image/png")

    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_caching_vision_provider_returns_a_copy_not_a_shared_reference(monkeypatch):
    """Callers (e.g. full_analysis_from_image's fingerprint = dict(raw))
    already copy defensively, but the cache itself must not hand out the
    exact same dict object on every hit either -- mutating one caller's
    result must never be visible to a different caller reading the same
    cached screenshot."""
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": None,
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    inner = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    provider = CachingVisionProvider(inner)

    image_bytes = b"identical-screenshot-bytes"
    first = await provider.analyze_screenshot(image_bytes, "image/png")
    first["pair"] = "MUTATED"
    second = await provider.analyze_screenshot(image_bytes, "image/png")

    assert second["pair"] == "BTCUSD"


@pytest.mark.asyncio
async def test_placeholder_provider_includes_evidence_for_every_interpretive_field():
    """Phase 12: the trader asked to understand HOW the AI reached each
    conclusion, not just what it concluded. The placeholder provider's
    output must have the same shape a real read would -- one evidence
    entry per interpretive field, honestly labeled since there's no
    real screenshot behind it."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")
    assert set(result["evidence"].keys()) == set(EVIDENCE_FIELDS)
    for field in EVIDENCE_FIELDS:
        assert isinstance(result["evidence"][field], list)
        assert len(result["evidence"][field]) >= 1
        assert "PLACEHOLDER" in result["evidence"][field][0]


def _evidence_payload(**overrides):
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": "Bullish FVG mitigated",
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_anthropic_provider_passes_through_valid_evidence_bullets(monkeypatch):
    """Happy path: the model follows the schema exactly -- its evidence
    bullets should flow through untouched (aside from the standard
    shape guarantee applied to every field)."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _evidence_payload(evidence={
        "fvgStatus": ["Price closed back inside the gap on the last two candles", "The imbalance is largely filled"],
        "trend": ["Higher highs and higher lows across the last 5 candles"],
    })
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["evidence"]["fvgStatus"] == [
        "Price closed back inside the gap on the last two candles",
        "The imbalance is largely filled",
    ]
    assert result["evidence"]["trend"] == ["Higher highs and higher lows across the last 5 candles"]
    # Every other EVIDENCE_FIELDS key the model didn't mention still
    # exists, just empty -- never absent.
    assert result["evidence"]["structure"] == []
    assert set(result["evidence"].keys()) == set(EVIDENCE_FIELDS)


@pytest.mark.asyncio
async def test_anthropic_provider_defaults_missing_evidence_key_entirely(monkeypatch):
    """The model can still omit "evidence" from its JSON altogether
    (older prompt caching, a genuinely lazy response, etc.) -- this
    must never KeyError or leave the field missing from the result."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _evidence_payload()  # no "evidence" key at all
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert set(result["evidence"].keys()) == set(EVIDENCE_FIELDS)
    assert all(result["evidence"][field] == [] for field in EVIDENCE_FIELDS)


@pytest.mark.asyncio
async def test_anthropic_provider_coerces_malformed_evidence_shapes(monkeypatch):
    """A vision model can drift from the schema in small ways -- a bare
    string instead of a one-item list, non-string junk inside a list,
    blank/whitespace-only strings, or a field that isn't even a
    list/string at all. None of that should reach the UI as-is."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _evidence_payload(evidence={
        "fvgStatus": "A single bare string instead of a list",
        "trend": ["Real evidence", "  ", 42, None, ""],
        "structure": 12345,  # not a list or string at all
    })
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["evidence"]["fvgStatus"] == ["A single bare string instead of a list"]
    assert result["evidence"]["trend"] == ["Real evidence"]
    assert result["evidence"]["structure"] == []


@pytest.mark.asyncio
async def test_anthropic_provider_caps_evidence_bullets_per_field(monkeypatch):
    """A model that gets carried away and lists ten bullets for one
    field should be trimmed to MAX_EVIDENCE_BULLETS_PER_FIELD -- a
    handful of concrete bullets is more verifiable than a wall of text."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    long_list = [f"Evidence bullet number {i}" for i in range(10)]
    payload = _evidence_payload(evidence={"fvgStatus": long_list})
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert len(result["evidence"]["fvgStatus"]) == MAX_EVIDENCE_BULLETS_PER_FIELD
    assert result["evidence"]["fvgStatus"] == long_list[:MAX_EVIDENCE_BULLETS_PER_FIELD]


@pytest.mark.asyncio
async def test_placeholder_provider_includes_facts_and_confidence_breakdown():
    """Phase 13 ("Facts vs. Interpretation vs. Confidence") -- the
    trader asked to separate literal chart detections from AI
    inference, and to see WHY each confidence number is what it is.
    The placeholder's shape must match what a real read would produce."""
    provider = PlaceholderVisionProvider()
    result = await provider.analyze_screenshot(b"fake-image-bytes", "image/png")

    assert isinstance(result["detectedLabels"], list)
    assert len(result["detectedLabels"]) >= 1
    assert all("PLACEHOLDER" in label for label in result["detectedLabels"])

    assert set(result["confidenceBreakdown"].keys()) == set(CONFIDENCE_FIELDS)
    for field in CONFIDENCE_FIELDS:
        entry = result["confidenceBreakdown"][field]
        assert isinstance(entry["finalConfidence"], int)
        assert 0 <= entry["finalConfidence"] <= 100
        assert isinstance(entry["positiveFactors"], list)
        assert isinstance(entry["negativeFactors"], list)

    # The three Phase 9 legacy flat fields must stay consistent with
    # their Phase 13 breakdown counterparts even on the placeholder.
    assert result["orderBlockFreshnessConfidence"] == result["confidenceBreakdown"]["orderBlockFreshness"]["finalConfidence"]
    assert result["rejectionStrengthConfidence"] == result["confidenceBreakdown"]["rejectionStrength"]["finalConfidence"]
    assert result["fvgMitigationConfidence"] == result["confidenceBreakdown"]["fvgStatus"]["finalConfidence"]


def _confidence_payload(**overrides):
    payload = {
        "trend": "Bullish", "structure": "Bullish", "currentPriceContext": "x",
        "liquidity": "x", "latestEvent": None, "fvgStatus": "Bullish FVG mitigated",
        "premiumDiscount": "Discount", "bias": "BUY", "readConfidence": 80,
        "pair": "BTCUSD", "timeframe": "M15", "orderDirection": "BUY",
        "orderType": "Buy Limit", "entry": 63984.27, "stopLoss": 63500.0,
        "takeProfit": 65000.0, "riskReward": 2.0, "lots": 0.01,
        "poiType": "Bullish Order Block",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_anthropic_provider_passes_through_valid_confidence_breakdown(monkeypatch):
    """Happy path: positive/negative factors flow through untouched,
    and the derived legacy flat field matches finalConfidence exactly
    (single source of truth, never independently guessed twice)."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _confidence_payload(confidenceBreakdown={
        "trend": {
            "finalConfidence": 90,
            "positiveFactors": [
                {"reason": "BOS confirms continuation", "points": 20},
                {"reason": "Higher highs", "points": 20},
            ],
            "negativeFactors": [{"reason": "Counter-trend liquidity nearby", "points": -10}],
        },
        "orderBlockFreshness": {"finalConfidence": 65, "positiveFactors": [], "negativeFactors": []},
    })
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")

    trend_entry = result["confidenceBreakdown"]["trend"]
    assert trend_entry["finalConfidence"] == 90
    assert trend_entry["positiveFactors"] == [
        {"reason": "BOS confirms continuation", "points": 20},
        {"reason": "Higher highs", "points": 20},
    ]
    assert trend_entry["negativeFactors"] == [{"reason": "Counter-trend liquidity nearby", "points": -10}]
    assert result["confidenceBreakdown"]["orderBlockFreshness"]["finalConfidence"] == 65
    assert result["orderBlockFreshnessConfidence"] == 65


@pytest.mark.asyncio
async def test_anthropic_provider_defaults_missing_confidence_breakdown_entirely(monkeypatch):
    """The model can omit "confidenceBreakdown" altogether -- every
    field must still get a neutral, honest default rather than a
    missing key or a fabricated confident-looking number."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _confidence_payload()  # no confidenceBreakdown key at all
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert set(result["confidenceBreakdown"].keys()) == set(CONFIDENCE_FIELDS)
    for field in CONFIDENCE_FIELDS:
        assert result["confidenceBreakdown"][field]["finalConfidence"] == 50
        assert result["confidenceBreakdown"][field]["positiveFactors"] == []
        assert result["confidenceBreakdown"][field]["negativeFactors"] == []


@pytest.mark.asyncio
async def test_anthropic_provider_clamps_out_of_range_confidence(monkeypatch):
    """A vision model returning 130 or -20 for a confidence number
    should be clamped to the valid 0-100 range, never passed through
    as-is or silently dropped."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    payload = _confidence_payload(confidenceBreakdown={
        "trend": {"finalConfidence": 130, "positiveFactors": [], "negativeFactors": []},
        "structure": {"finalConfidence": -20, "positiveFactors": [], "negativeFactors": []},
    })
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    assert result["confidenceBreakdown"]["trend"]["finalConfidence"] == 100
    assert result["confidenceBreakdown"]["structure"]["finalConfidence"] == 0


@pytest.mark.asyncio
async def test_anthropic_provider_enforces_factor_sign_and_caps_count(monkeypatch):
    """A positive number that lands in negativeFactors (or vice versa)
    gets its sign corrected rather than being dropped -- the model
    still clearly meant it to reduce/raise confidence given which list
    it chose. Also verifies the per-field factor-count cap."""
    provider = AnthropicVisionProvider(api_key="sk-test-fake-key-not-real")
    many_factors = [{"reason": f"factor {i}", "points": 5} for i in range(10)]
    payload = _confidence_payload(confidenceBreakdown={
        "trend": {
            "finalConfidence": 70,
            "positiveFactors": [{"reason": "Mis-signed negative", "points": -15}] + many_factors,
            "negativeFactors": [{"reason": "Mis-signed positive", "points": 15}],
        },
    })
    import json as _json

    class _FakeAsyncAnthropic:
        def __init__(self, api_key, **kwargs):
            pass

        class messages:
            @staticmethod
            async def create(**kwargs):
                return _fake_response_with_text(_json.dumps(payload))

    import anthropic

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    result = await provider.analyze_screenshot(b"fake-bytes", "image/png")
    positive = result["confidenceBreakdown"]["trend"]["positiveFactors"]
    negative = result["confidenceBreakdown"]["trend"]["negativeFactors"]
    assert positive[0] == {"reason": "Mis-signed negative", "points": 15}
    assert len(positive) == MAX_CONFIDENCE_FACTORS_PER_FIELD
    assert negative == [{"reason": "Mis-signed positive", "points": -15}]
