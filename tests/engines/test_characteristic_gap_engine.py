"""Characteristic Gap Engine tests (Sprint 20 Phase 4).

Confirms the engine answers "what do my winners have that this
doesn't / what do my losers have that this also has?" honestly --
never a verdict, and never drawing a "pattern" from too few trades.
"""
from app.engines.characteristic_gap_engine import (
    DOMINANT_SHARE,
    MIN_SAMPLE_FOR_GAP,
    build_characteristic_gaps,
)


def _trade(id_, outcome, **kw):
    base = {"id": id_, "outcome": outcome, "h4PoiType": "OB", "premiumDiscount": "Discount",
            "session": "London", "m15Confirmations": ["BOS", "Liquidity Sweep"]}
    base.update(kw)
    return base


def test_no_gaps_when_below_minimum_sample():
    """Only 2 winners and 1 loser -- neither pool clears MIN_SAMPLE_FOR_GAP,
    so nothing is surfaced at all (no pattern from noise)."""
    similar = [
        _trade("w1", "Win"),
        _trade("w2", "Win"),
        _trade("l1", "Loss"),
    ]
    candidate = {"h4PoiType": "FVG", "premiumDiscount": "Premium", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert result["hasEnoughData"] is False
    assert result["winnerGaps"] == []
    assert result["loserEchoes"] == []


def test_winner_gap_surfaced_when_candidate_diverges_from_dominant_winning_pattern():
    """3+ winners, all in Discount -- candidate is in Premium -- must be
    flagged as a gap between this setup and the trader's own winners."""
    similar = [_trade(f"w{i}", "Win", premiumDiscount="Discount") for i in range(4)]
    candidate = {"premiumDiscount": "Premium", "m15Confirmations": ["BOS", "Liquidity Sweep"]}
    result = build_characteristic_gaps(candidate, similar)
    assert result["hasEnoughData"] is True
    assert result["winningTradeCount"] == 4
    assert any("Discount" in g and "Premium" in g for g in result["winnerGaps"])


def test_no_winner_gap_when_candidate_matches_dominant_pattern():
    similar = [_trade(f"w{i}", "Win", premiumDiscount="Discount") for i in range(4)]
    candidate = {"premiumDiscount": "Discount", "m15Confirmations": ["BOS", "Liquidity Sweep"]}
    result = build_characteristic_gaps(candidate, similar)
    assert not any("premiumDiscount" in g or "zone" in g for g in result["winnerGaps"])


def test_winner_gap_for_missing_tag():
    """4 winners all had a liquidity sweep; candidate doesn't -- flagged."""
    similar = [_trade(f"w{i}", "Win", m15Confirmations=["BOS", "Liquidity Sweep"]) for i in range(4)]
    candidate = {"m15Confirmations": ["BOS"]}
    result = build_characteristic_gaps(candidate, similar)
    assert any("liquidity sweep" in g.lower() for g in result["winnerGaps"])


def test_loser_echo_for_shared_missing_tag():
    """User's own example: 'your losers often lack a liquidity sweep,
    this one also lacks one.'"""
    similar = [_trade(f"l{i}", "Loss", m15Confirmations=["BOS"]) for i in range(4)]  # no sweep
    candidate = {"m15Confirmations": ["BOS"]}  # candidate also has no sweep
    result = build_characteristic_gaps(candidate, similar)
    assert result["losingTradeCount"] == 4
    assert any("liquidity sweep" in e.lower() and "missing it too" in e for e in result["loserEchoes"])


def test_no_loser_echo_when_candidate_has_what_losers_lack():
    similar = [_trade(f"l{i}", "Loss", m15Confirmations=["BOS"]) for i in range(4)]
    candidate = {"m15Confirmations": ["BOS", "Liquidity Sweep"]}
    result = build_characteristic_gaps(candidate, similar)
    assert not any("liquidity sweep" in e.lower() for e in result["loserEchoes"])


def test_loser_echo_for_shared_categorical_value():
    similar = [_trade(f"l{i}", "Loss", premiumDiscount="Premium") for i in range(4)]
    candidate = {"premiumDiscount": "Premium", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert any("Premium" in e and "losing trades" in e for e in result["loserEchoes"])


def test_no_gap_or_echo_when_no_dominant_pattern_exists():
    """Winners are evenly split across two POI types -- no single value
    clears DOMINANT_SHARE, so nothing gets claimed as "typical"."""
    similar = [
        _trade("w1", "Win", h4PoiType="OB"),
        _trade("w2", "Win", h4PoiType="OB"),
        _trade("w3", "Win", h4PoiType="FVG"),
        _trade("w4", "Win", h4PoiType="FVG"),
    ]
    candidate = {"h4PoiType": "Liquidity Sweep", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert not any("point-of-interest" in g for g in result["winnerGaps"])


def test_never_contains_a_verdict_field():
    similar = [_trade(f"w{i}", "Win") for i in range(4)]
    candidate = {"premiumDiscount": "Premium", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    forbidden = {"tradeStatus", "recommendation", "verdict", "isValid", "shouldTake"}
    assert forbidden.isdisjoint(result.keys())


def test_constants_match_documented_honesty_bar():
    assert MIN_SAMPLE_FOR_GAP == 3
    assert 0 < DOMINANT_SHARE <= 1
