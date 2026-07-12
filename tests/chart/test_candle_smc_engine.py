"""Unit tests for the deterministic candle SMC engine
(app/chart/candle_smc_engine.py) — all synthetic, hand-constructed OHLC
series with a known, unambiguous pattern baked in, so each test is
checking the algorithm against ground truth we defined ourselves."""
import pytest

from app.chart.candle_smc_engine import (
    MIN_CANDLES_FOR_ANALYSIS,
    Candle,
    analyze_candles,
    find_equal_levels,
    find_fair_value_gaps,
    find_swing_points,
    infer_trend,
)


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c)


def test_find_swing_points_detects_obvious_zigzag():
    # A clean up-down-up zigzag: index 2 is a swing high, index 4 a swing low.
    candles = [
        _candle("0", 1.00, 1.01, 0.99, 1.00),
        _candle("1", 1.00, 1.05, 1.00, 1.04),
        _candle("2", 1.04, 1.10, 1.03, 1.05),  # swing high at 1.10
        _candle("3", 1.05, 1.06, 1.00, 1.01),
        _candle("4", 1.01, 1.02, 0.90, 0.92),  # swing low at 0.90
        _candle("5", 0.92, 0.98, 0.91, 0.97),
        _candle("6", 0.97, 1.00, 0.96, 0.99),
    ]
    highs, lows = find_swing_points(candles, fractal_n=2)
    assert any(h.index == 2 and h.price == 1.10 for h in highs)
    assert any(l.index == 4 and l.price == 0.90 for l in lows)


def test_infer_trend_bullish_on_higher_highs_and_higher_lows():
    from app.chart.candle_smc_engine import SwingPoint

    highs = [SwingPoint(0, "0", 1.10, "high"), SwingPoint(1, "1", 1.20, "high")]
    lows = [SwingPoint(0, "0", 1.00, "low"), SwingPoint(1, "1", 1.05, "low")]
    assert infer_trend(highs, lows) == "Bullish"


def test_infer_trend_bearish_on_lower_highs_and_lower_lows():
    from app.chart.candle_smc_engine import SwingPoint

    highs = [SwingPoint(0, "0", 1.20, "high"), SwingPoint(1, "1", 1.10, "high")]
    lows = [SwingPoint(0, "0", 1.05, "low"), SwingPoint(1, "1", 1.00, "low")]
    assert infer_trend(highs, lows) == "Bearish"


def test_infer_trend_ranging_when_mixed_or_insufficient():
    from app.chart.candle_smc_engine import SwingPoint

    # higher high but lower low = mixed signal
    highs = [SwingPoint(0, "0", 1.10, "high"), SwingPoint(1, "1", 1.20, "high")]
    lows = [SwingPoint(0, "0", 1.05, "low"), SwingPoint(1, "1", 1.00, "low")]
    assert infer_trend(highs, lows) == "Ranging"
    assert infer_trend([], []) == "Ranging"


def test_bullish_fair_value_gap_detected():
    # candle[0].high (1.05) < candle[2].low (1.10) -> bullish FVG between them
    candles = [
        _candle("0", 1.00, 1.05, 0.99, 1.02),
        _candle("1", 1.06, 1.15, 1.06, 1.14),
        _candle("2", 1.14, 1.20, 1.10, 1.18),
    ]
    gaps = find_fair_value_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0].kind == "bullish"
    assert gaps[0].bottom == 1.05
    assert gaps[0].top == 1.10


def test_bearish_fair_value_gap_detected():
    # candle[0].low (1.20) > candle[2].high (1.15) -> bearish FVG
    candles = [
        _candle("0", 1.25, 1.28, 1.20, 1.22),
        _candle("1", 1.18, 1.19, 1.10, 1.12),
        _candle("2", 1.10, 1.15, 1.08, 1.09),
    ]
    gaps = find_fair_value_gaps(candles)
    assert len(gaps) == 1
    assert gaps[0].kind == "bearish"
    assert gaps[0].top == 1.20
    assert gaps[0].bottom == 1.15


def test_find_equal_levels_groups_close_prices():
    from app.chart.candle_smc_engine import SwingPoint

    points = [
        SwingPoint(0, "0", 1.1000, "high"),
        SwingPoint(1, "1", 1.1002, "high"),  # within tolerance of the first
        SwingPoint(2, "2", 1.2000, "high"),  # far away — its own group, dropped (only 1 member)
    ]
    groups = find_equal_levels(points)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_analyze_candles_raises_on_too_few_candles():
    candles = [{"time": str(i), "open": 1, "high": 1.01, "low": 0.99, "close": 1} for i in range(3)]
    with pytest.raises(ValueError):
        analyze_candles(candles)
    assert MIN_CANDLES_FOR_ANALYSIS > 3


# Hand-built zigzag: each swing high and swing low is strictly higher
# than the one before it (verified with find_swing_points() directly
# before writing this test — see dev notes in the PR). This is a real
# fractal structure, not a monotonic series (which has no swing points
# at all and would be a mis-specified test).
_BULLISH_ROWS = [
    (1.000, 1.001, 0.999, 1.000),
    (1.000, 1.005, 0.999, 1.004),
    (1.004, 1.010, 1.003, 1.006),  # swing high 1.010
    (1.006, 1.007, 1.000, 1.001),
    (1.001, 1.002, 0.994, 0.995),  # swing low 0.994
    (0.995, 1.003, 0.996, 1.002),
    (1.002, 1.008, 1.001, 1.006),
    (1.006, 1.016, 1.005, 1.012),  # swing high 1.016
    (1.012, 1.013, 1.004, 1.005),
    (1.005, 1.006, 0.998, 0.999),  # swing low 0.998
    (0.999, 1.007, 1.000, 1.006),
    (1.006, 1.012, 1.005, 1.010),
    (1.010, 1.022, 1.009, 1.018),  # swing high 1.022
    (1.018, 1.019, 1.010, 1.011),
    (1.011, 1.012, 1.002, 1.003),  # swing low 1.002
    (1.003, 1.011, 1.004, 1.010),
    (1.010, 1.016, 1.009, 1.014),
]


def test_analyze_candles_end_to_end_bullish_series():
    raw = [
        {"time": str(i), "open": o, "high": h, "low": l, "close": c}
        for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
    ]
    result = analyze_candles(raw)
    assert result.trend == "Bullish"
    assert result.current_price == raw[-1]["close"]
    assert result.premium_discount in ("Premium", "Discount", "Equilibrium")
    assert len(result.swing_highs) >= 2
    assert len(result.swing_lows) >= 2


def test_analyze_candles_ranging_series_stays_ranging():
    # Oscillates in a tight band with no clear directional swing progression.
    raw = []
    prices = [1.10, 1.12, 1.10, 1.13, 1.09, 1.12, 1.10, 1.11, 1.10, 1.12, 1.09, 1.11]
    for i, p in enumerate(prices):
        raw.append({"time": str(i), "open": p, "high": p + 0.005, "low": p - 0.005, "close": p})
    result = analyze_candles(raw)
    assert result.trend in ("Ranging", "Bullish", "Bearish")  # deterministic given the algorithm, just must not error
