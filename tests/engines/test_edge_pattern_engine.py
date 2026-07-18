"""Edge Pattern Engine tests (Sprint 20 Phase 5 -- "Best Pattern").

Confirms multi-dimensional pattern discovery: a "pattern" here always
means pair+direction+timeframe+POI+zone+session ALL matching, never a
partial overlap -- and that it degrades honestly with too little data,
same as every other engine in this app.
"""
from app.engines.edge_pattern_engine import (
    EDGE_MIN_SAMPLE,
    MAX_PATTERNS,
    build_edge_patterns,
)


def _trade(id_, pnl, **kw):
    base = {
        "id": id_, "pnl": pnl, "pair": "btcusd", "direction": "sell", "timeframe": "M15",
        "h4PoiType": "Bearish Order Block", "premiumDiscount": "Premium", "session": "London", "rr": 2.5,
    }
    base.update(kw)
    return base


def test_no_patterns_below_minimum_sample():
    history = [_trade(f"t{i}", 10) for i in range(2)]  # only 2, below EDGE_MIN_SAMPLE
    result = build_edge_patterns(history)
    assert result["hasEnoughData"] is False
    assert result["patterns"] == []


def test_pattern_surfaced_once_sample_clears_the_bar():
    history = [_trade(f"t{i}", 50 if i < 3 else -20) for i in range(4)]
    result = build_edge_patterns(history)
    assert result["hasEnoughData"] is True
    assert len(result["patterns"]) == 1
    p = result["patterns"][0]
    assert p["pair"] == "btcusd"
    assert p["direction"] == "sell"
    assert p["timeframe"] == "M15"
    assert p["poiType"] == "Bearish Order Block"
    assert p["premiumDiscount"] == "Premium"
    assert p["session"] == "London"
    assert p["count"] == 4
    assert p["wins"] == 3
    assert p["losses"] == 1
    assert p["winRate"] == 75.0


def test_partial_dimension_overlap_never_forms_a_pattern():
    """Same pair/direction but a DIFFERENT timeframe on each of 3
    trades -- 3 separate 1-count 'patterns' by the strict all-six-match
    rule, none of which clears EDGE_MIN_SAMPLE, even though 3 trades
    exist in total."""
    history = [
        _trade("t0", 10, timeframe="M15"),
        _trade("t1", 10, timeframe="H1"),
        _trade("t2", 10, timeframe="H4"),
    ]
    result = build_edge_patterns(history)
    assert result["patterns"] == []


def test_trade_missing_any_dimension_is_excluded_entirely():
    history = [_trade(f"t{i}", 10) for i in range(3)]
    history.append(_trade("no-session", 10, session=None))
    result = build_edge_patterns(history)
    # The no-session trade must not silently join the 3-count group nor
    # form its own -- it's simply excluded from pattern discovery.
    assert result["patterns"][0]["count"] == 3


def test_ranked_by_win_rate_and_expectancy_best_first():
    strong = [_trade(f"s{i}", 50, pair="eurusd", direction="buy") for i in range(4)]
    weak = [_trade(f"w{i}", -10 if i < 2 else 5, pair="gbpusd", direction="buy") for i in range(4)]
    result = build_edge_patterns(strong + weak)
    assert result["patterns"][0]["pair"] == "eurusd"


def test_max_patterns_cap_respected():
    groups = []
    for n in range(5):
        groups += [_trade(f"g{n}-{i}", 10, pair=f"pair{n}") for i in range(4)]
    result = build_edge_patterns(groups)
    assert len(result["patterns"]) <= MAX_PATTERNS


def test_never_contains_a_verdict_field():
    history = [_trade(f"t{i}", 50) for i in range(4)]
    result = build_edge_patterns(history)
    forbidden = {"tradeStatus", "recommendation", "verdict", "isValid", "shouldTake"}
    assert forbidden.isdisjoint(result.keys())
    for p in result["patterns"]:
        assert forbidden.isdisjoint(p.keys())


def test_constant_matches_documented_honesty_bar():
    assert EDGE_MIN_SAMPLE == 3
