"""Pattern Discovery Engine tests (Sprint 20 Phase 6 -- "learn from my
screenshots"). Confirms standalone winner-vs-loser separation is only
ever surfaced when there's real data behind it, and never a verdict.
"""
from app.engines.pattern_discovery_engine import MIN_SAMPLE, build_discovered_patterns


def _trade(id_, pnl, **kw):
    base = {"id": id_, "pnl": pnl, "session": "London", "m15Confirmations": []}
    base.update(kw)
    return base


def test_no_patterns_below_minimum_sample_either_side():
    history = [_trade("w1", 10), _trade("w2", 10), _trade("l1", -10)]
    result = build_discovered_patterns(history)
    assert result["hasEnoughData"] is False
    assert result["patterns"] == []


def test_categorical_separation_surfaced_when_real():
    winners = [_trade(f"w{i}", 10, session="London") for i in range(4)]
    losers = [_trade(f"l{i}", -10, session="Asian") for i in range(4)]
    result = build_discovered_patterns(winners + losers)
    assert result["hasEnoughData"] is True
    assert any("London" in p and "session" in p for p in result["patterns"])


def test_no_categorical_pattern_when_both_sides_share_the_value():
    winners = [_trade(f"w{i}", 10, session="London") for i in range(4)]
    losers = [_trade(f"l{i}", -10, session="London") for i in range(4)]
    result = build_discovered_patterns(winners + losers)
    assert not any("session" in p for p in result["patterns"])


def test_tag_separation_surfaced_for_winners():
    winners = [_trade(f"w{i}", 10, m15Confirmations=["Fresh Order Block"]) for i in range(4)]
    losers = [_trade(f"l{i}", -10, m15Confirmations=["Mitigated Order Block"]) for i in range(4)]
    result = build_discovered_patterns(winners + losers)
    joined = " ".join(result["patterns"])
    assert "fresh, untested Order Block" in joined
    assert "your winning trades usually have" in joined.lower() or "Your winning trades usually have" in joined


def test_tag_separation_surfaced_for_losers():
    winners = [_trade(f"w{i}", 10, m15Confirmations=[]) for i in range(4)]
    losers = [_trade(f"l{i}", -10, m15Confirmations=["Mitigated Order Block"]) for i in range(4)]
    result = build_discovered_patterns(winners + losers)
    assert any("Your losing trades usually have an already-mitigated Order Block" in p for p in result["patterns"])


def test_never_contains_a_verdict_field():
    winners = [_trade(f"w{i}", 10, session="London") for i in range(4)]
    losers = [_trade(f"l{i}", -10, session="Asian") for i in range(4)]
    result = build_discovered_patterns(winners + losers)
    forbidden = {"tradeStatus", "recommendation", "verdict", "isValid", "shouldTake"}
    assert forbidden.isdisjoint(result.keys())


def test_constant_matches_documented_honesty_bar():
    assert MIN_SAMPLE == 3
