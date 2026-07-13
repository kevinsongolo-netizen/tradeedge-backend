"""Tests for the backtesting engine (Sprint 13).

``_simulate_trade_outcome`` is tested directly with synthetic candles.
``run_backtest``'s orchestration (entry/exit lifecycle, stats
aggregation, one-trade-at-a-time skipping) is tested by monkeypatching
its two engine dependencies (``analyze_candles`` and ``validate_trade``,
both imported by name into ``app.backtest.backtest_engine``'s own
namespace, so they're patched there — not on their origin modules) so
the test controls exactly when a "VALID" setup is found, without
needing to hand-construct real market structure. ``normalize`` is
imported as a module, so patching ``app.chart.normalize.from_candle_analysis``
works via the live module reference.
"""
import pytest

import app.backtest.backtest_engine as bt
from app.backtest.backtest_engine import (
    MIN_TOTAL_CANDLES,
    _simulate_trade_outcome,
    run_backtest,
)
from app.chart import normalize


def _flat_candles(n, price=100.0):
    return [{"time": str(i), "open": price, "high": price, "low": price, "close": price} for i in range(n)]


# ---------- _simulate_trade_outcome ----------


def test_simulate_buy_hits_take_profit_first():
    candles = _flat_candles(5)
    candles[3] = {"time": "3", "open": 100, "high": 106, "low": 99, "close": 105}
    result = _simulate_trade_outcome(candles, entry_index=2, direction="buy", stop_loss=98, take_profit=106)
    assert result["outcome"] == "WIN"
    assert result["exit_index"] == 3


def test_simulate_buy_hits_stop_loss_first():
    candles = _flat_candles(5)
    candles[3] = {"time": "3", "open": 100, "high": 101, "low": 97, "close": 98}
    result = _simulate_trade_outcome(candles, entry_index=2, direction="buy", stop_loss=98, take_profit=106)
    assert result["outcome"] == "LOSS"


def test_simulate_sell_hits_take_profit_first():
    candles = _flat_candles(5)
    candles[3] = {"time": "3", "open": 100, "high": 101, "low": 93, "close": 94}
    result = _simulate_trade_outcome(candles, entry_index=2, direction="sell", stop_loss=102, take_profit=94)
    assert result["outcome"] == "WIN"


def test_simulate_open_when_neither_level_reached():
    candles = _flat_candles(5)
    result = _simulate_trade_outcome(candles, entry_index=2, direction="buy", stop_loss=98, take_profit=106)
    assert result["outcome"] == "OPEN"
    assert result["exit_index"] is None


# ---------- run_backtest input validation ----------


def test_raises_on_too_few_candles():
    with pytest.raises(ValueError, match="at least"):
        run_backtest(_flat_candles(3))


def test_raises_on_too_many_candles():
    with pytest.raises(ValueError, match="Too many"):
        run_backtest(_flat_candles(2001))


def test_raises_on_lookback_window_too_small():
    with pytest.raises(ValueError, match="lookback_window"):
        run_backtest(_flat_candles(MIN_TOTAL_CANDLES + 1), lookback_window=1)


# ---------- run_backtest orchestration (mocked engine calls) ----------


def _fake_valid_analysis_dict():
    return {
        "source": "candles",
        "trend": "Bullish",
        "structure": "Bullish",
        "currentPriceContext": "Inside Bullish Order Block",
        "liquidity": "No clear equal-highs/equal-lows liquidity detected",
        "latestEvent": "Bullish BOS detected",
        "fvgStatus": None,
        "premiumDiscount": "Discount",
        "bias": "BUY",
        "confidence": 92,
        "zones": [],
        "entryZone": None,
        "notes": [],
        "isPlaceholder": False,
    }


def test_orchestration_records_one_win(monkeypatch):
    calls = {"n": 0}

    def fake_analyze_candles(window):
        return object()

    def fake_validate_trade(analysis, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "tradeStatus": "VALID",
                "direction": "buy",
                "confidence": 80,
                "reasonsPassed": [],
                "reasonsFailed": [],
                "suggestedEntry": 100.0,
                "stopLoss": 98.0,
                "takeProfit": 106.0,
                "riskReward": 3.0,
                "recommendation": "TAKE",
            }
        return {
            "tradeStatus": "INVALID",
            "direction": None,
            "confidence": 0,
            "reasonsPassed": [],
            "reasonsFailed": ["no signal"],
            "suggestedEntry": None,
            "stopLoss": None,
            "takeProfit": None,
            "riskReward": None,
            "recommendation": "WAIT",
        }

    monkeypatch.setattr(bt, "analyze_candles", fake_analyze_candles)
    monkeypatch.setattr(bt, "validate_trade", fake_validate_trade)
    monkeypatch.setattr(normalize, "from_candle_analysis", lambda smc: _fake_valid_analysis_dict())

    n = MIN_TOTAL_CANDLES + 10
    candles = _flat_candles(n, price=100.0)
    # Entry happens at index MIN_CANDLES_FOR_ANALYSIS (= MIN_TOTAL_CANDLES - 5),
    # with entry fill = that candle's open (100.0, from _flat_candles). Make
    # the candle two steps later spike to take profit.
    entry_index = bt.MIN_CANDLES_FOR_ANALYSIS
    candles[entry_index + 2] = {
        "time": str(entry_index + 2), "open": 100.0, "high": 107.0, "low": 99.5, "close": 106.5,
    }

    result = run_backtest(candles, min_rr=2.0)
    assert result["total_trades"] == 1
    assert result["wins"] == 1
    assert result["losses"] == 0
    assert result["win_rate"] == 100.0
    assert result["trades"][0]["outcome"] == "WIN"
    assert result["trades"][0]["r_multiple"] == pytest.approx(3.0)


def test_orchestration_records_one_loss(monkeypatch):
    def fake_analyze_candles(window):
        return object()

    def fake_validate_trade(analysis, **kwargs):
        return {
            "tradeStatus": "VALID",
            "direction": "buy",
            "confidence": 80,
            "reasonsPassed": [],
            "reasonsFailed": [],
            "suggestedEntry": 100.0,
            "stopLoss": 98.0,
            "takeProfit": 106.0,
            "riskReward": 3.0,
            "recommendation": "TAKE",
        } if fake_validate_trade.calls == 0 else {
            "tradeStatus": "INVALID", "direction": None, "confidence": 0,
            "reasonsPassed": [], "reasonsFailed": ["no signal"],
            "suggestedEntry": None, "stopLoss": None, "takeProfit": None,
            "riskReward": None, "recommendation": "WAIT",
        }
    fake_validate_trade.calls = 0

    def counting_validate_trade(analysis, **kwargs):
        result = fake_validate_trade(analysis, **kwargs)
        fake_validate_trade.calls += 1
        return result

    monkeypatch.setattr(bt, "analyze_candles", fake_analyze_candles)
    monkeypatch.setattr(bt, "validate_trade", counting_validate_trade)
    monkeypatch.setattr(normalize, "from_candle_analysis", lambda smc: _fake_valid_analysis_dict())

    n = MIN_TOTAL_CANDLES + 10
    candles = _flat_candles(n, price=100.0)
    entry_index = bt.MIN_CANDLES_FOR_ANALYSIS
    candles[entry_index + 1] = {
        "time": str(entry_index + 1), "open": 100.0, "high": 100.5, "low": 97.0, "close": 97.5,
    }

    result = run_backtest(candles, min_rr=2.0)
    assert result["total_trades"] == 1
    assert result["losses"] == 1
    assert result["trades"][0]["outcome"] == "LOSS"
    assert result["trades"][0]["r_multiple"] == -1.0
    assert result["profit_factor"] == 0.0
