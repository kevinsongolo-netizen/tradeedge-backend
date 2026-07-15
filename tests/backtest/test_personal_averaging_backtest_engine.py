"""Tests for the Personal Averaging Strategy backtest engine (Sprint
18). Same monkeypatching strategy as ``test_h4_m15_backtest_engine.py``:
patches ``analyze_candles`` and ``validate_personal_averaging`` (both
imported by name into ``app.backtest.personal_averaging_backtest_engine``'s
own namespace) so the test controls exactly when a TAKE/ADD signal
fires, without needing real market structure -- this engine's real
value (cycle/MAE/add-on tracking) is about the state machine around
the strategy call, not the strategy's own internals (already covered
by ``test_personal_averaging_strategy.py``)."""
from datetime import datetime, timedelta

import pytest

import app.backtest.personal_averaging_backtest_engine as bt
from app.backtest.personal_averaging_backtest_engine import (
    MIN_DAILY_CANDLES,
    MIN_M15_CANDLES,
    run_backtest_personal_averaging,
)


def _daily_candles(n, start="2023-12-01T00:00:00"):
    t0 = datetime.fromisoformat(start)
    return [
        {"time": (t0 + timedelta(days=i)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100.5}
        for i in range(n)
    ]


def _m15_candles(prices, start="2024-01-01T00:00:00"):
    """One bar per price -- open=high=low=close=price for simplicity
    unless the test needs a range, in which case pass a (o, h, l, c) tuple."""
    t0 = datetime.fromisoformat(start)
    rows = []
    for i, p in enumerate(prices):
        if isinstance(p, tuple):
            o, h, l, c = p
        else:
            o = h = l = c = p
        rows.append({"time": (t0 + timedelta(minutes=15 * i)).isoformat(), "open": o, "high": h, "low": l, "close": c})
    return rows


def _fake_analyze_candles(monkeypatch, dummy="SMC"):
    monkeypatch.setattr(bt, "analyze_candles", lambda candles: dummy)


# ---------- input validation ----------

def test_raises_on_too_few_daily_candles():
    with pytest.raises(ValueError):
        run_backtest_personal_averaging(_daily_candles(1), _m15_candles([100] * 30))


def test_raises_on_too_few_m15_candles():
    with pytest.raises(ValueError):
        run_backtest_personal_averaging(_daily_candles(5), _m15_candles([100] * 3))


# ---------- no signals at all ----------

def test_no_validation_calls_return_valid_means_no_cycles(monkeypatch):
    _fake_analyze_candles(monkeypatch)
    monkeypatch.setattr(bt, "validate_personal_averaging", lambda daily, m15, open_trade_in_loss=False: {
        "tradeStatus": "INVALID", "direction": None, "recommendation": "WAIT",
    })
    result = run_backtest_personal_averaging(_daily_candles(5), _m15_candles([100] * 30))
    assert result["cycles_total"] == 0
    assert result["cycles_closed"] == 0
    assert result["cycles_open"] == 0
    assert result["total_trades"] == 0


# ---------- simple single-entry cycle that recovers to breakeven ----------

def test_single_entry_cycle_closes_at_breakeven(monkeypatch):
    _fake_analyze_candles(monkeypatch)
    call_count = {"n": 0}

    def fake_validate(daily, m15, open_trade_in_loss=False):
        call_count["n"] += 1
        # Fire exactly one TAKE signal on the very first call, WAIT after.
        if call_count["n"] == 1:
            return {"tradeStatus": "VALID", "direction": "buy", "recommendation": "TAKE"}
        return {"tradeStatus": "INVALID", "direction": None, "recommendation": "WAIT"}

    monkeypatch.setattr(bt, "validate_personal_averaging", fake_validate)

    # Prices: flat at 100 until entry (fills at next bar's open = 100),
    # then rises so a bullish position recovers to >= breakeven quickly.
    prices = [100] * 25 + [100, 100, 105, 106, 107]
    result = run_backtest_personal_averaging(_daily_candles(5), _m15_candles(prices))

    assert result["cycles_total"] == 1
    assert result["cycles_closed"] == 1
    assert result["cycles_open"] == 0
    cycle = result["cycles_detail"][0]
    assert cycle["direction"] == "buy"
    assert cycle["add_on_used"] is False
    assert cycle["outcome"] == "CLOSED"
    assert cycle["net_pnl_per_unit"] >= 0


# ---------- add-on entry used when floating in a loss ----------

def test_add_on_entry_fires_when_in_loss_and_recovers(monkeypatch):
    _fake_analyze_candles(monkeypatch)
    call_count = {"n": 0}

    def fake_validate(daily, m15, open_trade_in_loss=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tradeStatus": "VALID", "direction": "buy", "recommendation": "TAKE"}
        if open_trade_in_loss and call_count["n"] == 3:
            return {"tradeStatus": "VALID", "direction": "buy", "recommendation": "ADD"}
        return {"tradeStatus": "INVALID", "direction": None, "recommendation": "WAIT"}

    monkeypatch.setattr(bt, "validate_personal_averaging", fake_validate)

    # Signal-check calls fire once per bar starting at i=9 (call_count
    # 1 -> i=9, entry fills at bar 10; call_count 2 -> i=10; call_count
    # 3 -> i=11, using bar 11's close for the in-loss check, add-on
    # fills at bar 12). Bar 10 = entry price, bar 11 = underwater,
    # bars 13+ = well above both entries so the cycle can recover.
    prices = [100] * 10 + [100, 90, 90, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130, 130]
    result = run_backtest_personal_averaging(_daily_candles(5), _m15_candles(prices))

    assert result["cycles_total"] == 1
    cycle = result["cycles_detail"][0]
    assert cycle["add_on_used"] is True
    assert len(cycle["entries"]) == 2
    assert cycle["outcome"] == "CLOSED"
    assert cycle["max_adverse_excursion"] < 0  # it really was underwater before recovering


# ---------- cycle that never recovers within the data window ----------

def test_cycle_still_open_at_end_of_data(monkeypatch):
    _fake_analyze_candles(monkeypatch)
    call_count = {"n": 0}

    def fake_validate(daily, m15, open_trade_in_loss=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"tradeStatus": "VALID", "direction": "buy", "recommendation": "TAKE"}
        return {"tradeStatus": "INVALID", "direction": None, "recommendation": "WAIT"}

    monkeypatch.setattr(bt, "validate_personal_averaging", fake_validate)

    # Entry fills at bar 10 (price 100); every bar after that stays
    # below 100, so the cycle can never reach breakeven and is still
    # open at the end of the data.
    prices = [100] * 10 + [100] + [95, 90, 85, 80, 75, 70, 65, 60, 55, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50]
    result = run_backtest_personal_averaging(_daily_candles(5), _m15_candles(prices))

    assert result["cycles_total"] == 1
    assert result["cycles_closed"] == 0
    assert result["cycles_open"] == 1
    cycle = result["cycles_detail"][0]
    assert cycle["outcome"] == "OPEN"
    assert cycle["exit_time"] is None
    assert cycle["net_pnl_per_unit"] < 0


def test_notes_flag_win_rate_is_not_meaningful(monkeypatch):
    _fake_analyze_candles(monkeypatch)
    monkeypatch.setattr(bt, "validate_personal_averaging", lambda daily, m15, open_trade_in_loss=False: {
        "tradeStatus": "INVALID", "direction": None, "recommendation": "WAIT",
    })
    result = run_backtest_personal_averaging(_daily_candles(5), _m15_candles([100] * 30))
    assert any("not a meaningful risk measure" in n for n in result["notes"])
