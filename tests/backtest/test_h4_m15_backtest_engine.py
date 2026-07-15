"""Tests for the H4->M15 dual-timeframe backtesting engine (v2).

Same monkeypatching strategy as ``test_backtest_engine.py``: patches
``analyze_candles`` and ``validate_h4_m15_ob`` (both imported by name
into ``app.backtest.h4_m15_backtest_engine``'s own namespace) so the
test controls exactly when a "VALID" setup is found, without needing
to hand-construct real market structure -- except for the alignment
test, which specifically needs real, spaced timestamps to prove the
H4 context never gets read before its own bar has closed.
"""
from datetime import datetime, timedelta

import pytest

import app.backtest.h4_m15_backtest_engine as bt
from app.backtest.h4_m15_backtest_engine import (
    MIN_H4_CANDLES,
    MIN_M15_CANDLES,
    run_backtest_h4_m15,
)


def _h4_candles(n, start="2024-01-01T00:00:00", price=100.0):
    t0 = datetime.fromisoformat(start)
    return [
        {"time": (t0 + timedelta(hours=4 * i)).isoformat(), "open": price, "high": price, "low": price, "close": price}
        for i in range(n)
    ]


def _m15_candles(n, start="2024-01-01T00:00:00", price=100.0):
    t0 = datetime.fromisoformat(start)
    return [
        {"time": (t0 + timedelta(minutes=15 * i)).isoformat(), "open": price, "high": price, "low": price, "close": price}
        for i in range(n)
    ]


# ---------- input validation ----------


def test_raises_on_too_few_h4_candles():
    with pytest.raises(ValueError, match="H4 candles"):
        run_backtest_h4_m15(_h4_candles(3), _m15_candles(MIN_M15_CANDLES + 5))


def test_raises_on_too_few_m15_candles():
    with pytest.raises(ValueError, match="M15 candles"):
        run_backtest_h4_m15(_h4_candles(MIN_H4_CANDLES + 5), _m15_candles(3))


def test_raises_on_too_many_candles():
    with pytest.raises(ValueError, match="Too many"):
        run_backtest_h4_m15(_h4_candles(3001), _m15_candles(MIN_M15_CANDLES + 5))


def test_raises_on_lookback_too_small():
    with pytest.raises(ValueError, match="Lookback windows"):
        run_backtest_h4_m15(
            _h4_candles(MIN_H4_CANDLES + 5), _m15_candles(MIN_M15_CANDLES + 5), lookback_window_h4=1
        )


def test_raises_on_unparseable_time():
    h4 = _h4_candles(MIN_H4_CANDLES + 5)
    h4[0]["time"] = "not-a-real-date"
    with pytest.raises(ValueError, match="Could not parse candle time"):
        run_backtest_h4_m15(h4, _m15_candles(MIN_M15_CANDLES + 5))


# ---------- orchestration (mocked engine calls) ----------


def _fake_valid():
    return {
        "tradeStatus": "VALID",
        "direction": "buy",
        "confidence": 100,
        "reasonsPassed": [],
        "reasonsFailed": [],
        "suggestedEntry": 100.0,
        "stopLoss": 98.0,
        "takeProfit": 106.0,
        "riskReward": 3.0,
        "recommendation": "TAKE",
    }


def _fake_invalid():
    return {
        "tradeStatus": "INVALID", "direction": None, "confidence": 0,
        "reasonsPassed": [], "reasonsFailed": ["no signal"],
        "suggestedEntry": None, "stopLoss": None, "takeProfit": None,
        "riskReward": None, "recommendation": "WAIT",
    }


def test_orchestration_records_one_win(monkeypatch):
    calls = {"n": 0}

    def fake_validate(h4_smc, m15_smc):
        calls["n"] += 1
        return _fake_valid() if calls["n"] == 1 else _fake_invalid()

    monkeypatch.setattr(bt, "analyze_candles", lambda window: object())
    monkeypatch.setattr(bt, "validate_h4_m15_ob", fake_validate)

    # H4 history starts well BEFORE the M15 series -- realistic (you'd
    # already have H4 candles going back further than when you started
    # watching M15), and ensures enough H4 bars have already closed by
    # the time M15 begins.
    h4 = _h4_candles(MIN_H4_CANDLES + 20, start="2023-12-25T00:00:00")
    n_m15 = MIN_M15_CANDLES + 10
    m15 = _m15_candles(n_m15)
    entry_index = bt.MIN_CANDLES_FOR_ANALYSIS
    m15[entry_index + 2] = {
        "time": m15[entry_index + 2]["time"], "open": 100.0, "high": 107.0, "low": 99.5, "close": 106.5,
    }

    result = run_backtest_h4_m15(h4, m15)
    assert result["total_trades"] == 1
    assert result["wins"] == 1
    assert result["losses"] == 0
    assert result["trades"][0]["outcome"] == "WIN"
    assert result["trades"][0]["r_multiple"] == pytest.approx(3.0)


def test_orchestration_records_one_loss(monkeypatch):
    calls = {"n": 0}

    def fake_validate(h4_smc, m15_smc):
        calls["n"] += 1
        return _fake_valid() if calls["n"] == 1 else _fake_invalid()

    monkeypatch.setattr(bt, "analyze_candles", lambda window: object())
    monkeypatch.setattr(bt, "validate_h4_m15_ob", fake_validate)

    h4 = _h4_candles(MIN_H4_CANDLES + 20, start="2023-12-25T00:00:00")
    n_m15 = MIN_M15_CANDLES + 10
    m15 = _m15_candles(n_m15)
    entry_index = bt.MIN_CANDLES_FOR_ANALYSIS
    m15[entry_index + 1] = {
        "time": m15[entry_index + 1]["time"], "open": 100.0, "high": 100.5, "low": 97.0, "close": 97.5,
    }

    result = run_backtest_h4_m15(h4, m15)
    assert result["total_trades"] == 1
    assert result["losses"] == 1
    assert result["trades"][0]["outcome"] == "LOSS"
    assert result["trades"][0]["r_multiple"] == -1.0


def test_no_trade_attempted_until_enough_h4_bars_have_closed(monkeypatch):
    """Correctness-critical: even if validate_h4_m15_ob WOULD say VALID
    on every call, no trade should be recorded until enough H4 bars
    have actually closed by that point in M15 time -- proves the H4
    context isn't read before it exists (no lookahead)."""
    monkeypatch.setattr(bt, "analyze_candles", lambda window: object())
    monkeypatch.setattr(bt, "validate_h4_m15_ob", lambda h4_smc, m15_smc: _fake_valid())

    # Full-sized H4 series, but starting AFTER the M15 range even ends
    # -- so zero H4 bars have closed by any point the M15 walk reaches.
    h4 = _h4_candles(MIN_H4_CANDLES + 5, start="2030-01-01T00:00:00")
    m15 = _m15_candles(MIN_M15_CANDLES + 50)

    result = run_backtest_h4_m15(h4, m15)
    assert result["total_trades"] == 0
    assert result["trades"] == []
