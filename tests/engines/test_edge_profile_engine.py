"""Edge Profile Engine tests (Sprint 20 Phase 8 -- "AI Learning
Engine"). Confirms comprehensive, data-driven characteristic ranking
(not just hand-picked separators) and honest degradation.
"""
from app.engines.edge_profile_engine import (
    MAX_CHARACTERISTICS,
    MIN_CHARACTERISTIC_SUPPORT,
    MIN_SAMPLE,
    build_edge_profile,
)


def _trade(id_, pnl, **kw):
    base = {"id": id_, "pnl": pnl, "session": "London", "m15Confirmations": []}
    base.update(kw)
    return base


def test_no_data_below_minimum_sample():
    result = build_edge_profile([_trade("w1", 10), _trade("l1", -10)])
    assert result["hasEnoughData"] is False
    assert result["winnerCharacteristics"] == []
    assert result["loserCharacteristics"] == []


def test_ranks_every_kind_of_characteristic_together():
    """Tag, trend-alignment, and categorical-value characteristics all
    compete in the same ranked list -- not just tags."""
    winners = [
        _trade(f"w{i}", 10, session="London", premiumDiscount="Discount", h4Trend="Bullish", direction="buy",
               m15Confirmations=["Fresh Order Block", "Liquidity Sweep"])
        for i in range(4)
    ]
    losers = [_trade(f"l{i}", -10, session="Asian", m15Confirmations=[]) for i in range(4)]
    result = build_edge_profile(winners + losers)
    assert result["hasEnoughData"] is True
    labels = {c["label"] for c in result["winnerCharacteristics"]}
    assert "Fresh Order Block" in labels
    assert "Liquidity Sweep" in labels
    assert "London" in labels
    assert "Discount" in labels
    assert "With-Trend Setup" in labels


def test_characteristic_needs_minimum_support_not_just_one_trade():
    winners = [_trade(f"w{i}", 10, m15Confirmations=["Strong Rejection"] if i == 0 else []) for i in range(4)]
    losers = [_trade(f"l{i}", -10) for i in range(3)]
    result = build_edge_profile(winners + losers)
    labels = {c["label"] for c in result["winnerCharacteristics"]}
    assert "Strong Rejection" not in labels  # only 1 of 4 winners -- below MIN_CHARACTERISTIC_SUPPORT


def test_characteristics_not_filtered_to_separators_only():
    """Unlike pattern_discovery_engine, a characteristic common to BOTH
    winners and losers should still show up on both ranked lists --
    the trader asked to see everything discovered per side, not just
    the differences."""
    winners = [_trade(f"w{i}", 10, session="London") for i in range(4)]
    losers = [_trade(f"l{i}", -10, session="London") for i in range(4)]
    result = build_edge_profile(winners + losers)
    winner_labels = {c["label"] for c in result["winnerCharacteristics"]}
    loser_labels = {c["label"] for c in result["loserCharacteristics"]}
    assert "London" in winner_labels
    assert "London" in loser_labels


def test_max_characteristics_cap_respected():
    winners = [
        _trade(
            f"w{i}", 10, session="London", premiumDiscount="Discount", h4Trend="Bullish", direction="buy",
            m15Confirmations=["Fresh Order Block", "Liquidity Sweep", "Strong Rejection", "BOS", "CHOCH", "Equal Highs Nearby", "First Touch", "Fresh FVG", "External BOS"],
        )
        for i in range(5)
    ]
    losers = [_trade(f"l{i}", -10) for i in range(3)]
    result = build_edge_profile(winners + losers)
    assert len(result["winnerCharacteristics"]) <= MAX_CHARACTERISTICS


def test_candidate_comparison_counts_and_names_matches():
    winners = [
        _trade(f"w{i}", 10, session="London", m15Confirmations=["Fresh Order Block", "Liquidity Sweep"])
        for i in range(4)
    ]
    losers = [_trade(f"l{i}", -10, session="Asian", m15Confirmations=["Mitigated Order Block"]) for i in range(4)]
    candidate = {"session": "London", "m15Confirmations": ["Fresh Order Block"]}
    result = build_edge_profile(winners + losers, candidate=candidate)
    assert result["winnerMatchCount"] >= 2  # Fresh Order Block + London
    assert "Fresh Order Block" in result["winnerMatches"]
    assert "London" in result["winnerMatches"]
    assert result["loserMatchCount"] == 0


def test_no_candidate_comparison_fields_when_candidate_omitted():
    winners = [_trade(f"w{i}", 10) for i in range(4)]
    losers = [_trade(f"l{i}", -10) for i in range(4)]
    result = build_edge_profile(winners + losers)
    assert "winnerMatchCount" not in result
    assert "winnerMatches" not in result


def test_never_contains_a_verdict_field():
    winners = [_trade(f"w{i}", 10, session="London") for i in range(4)]
    losers = [_trade(f"l{i}", -10, session="Asian") for i in range(4)]
    result = build_edge_profile(winners + losers, candidate={"session": "London"})
    forbidden = {"tradeStatus", "recommendation", "verdict", "isValid", "shouldTake"}
    assert forbidden.isdisjoint(result.keys())


def test_constants_match_documented_honesty_bar():
    assert MIN_SAMPLE == 3
    assert MIN_CHARACTERISTIC_SUPPORT == 3
