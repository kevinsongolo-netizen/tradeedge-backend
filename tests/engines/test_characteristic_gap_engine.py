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


# --- Sprint 20 Phase 5 -- continuous dimensions + "matches N of M" --------


def test_winner_gap_for_smaller_stop_loss():
    """User's own example: 'Smaller stop loss' as a winning
    characteristic -- winners with a tight stop, candidate has a much
    wider one, must be flagged as a gap."""
    similar = [
        _trade(f"w{i}", "Win", entry=100.0, sl=99.0)  # 1% stop
        for i in range(4)
    ]
    candidate = {"entry": 100.0, "sl": 95.0, "m15Confirmations": []}  # 5% stop, way wider
    result = build_characteristic_gaps(candidate, similar)
    assert any("stop loss size" in g for g in result["winnerGaps"])


def test_winner_gap_for_higher_rr():
    """User's own example: 'Higher R:R' as a winning characteristic."""
    similar = [_trade(f"w{i}", "Win", rr=4.0) for i in range(4)]
    candidate = {"rr": 1.0, "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert any("risk:reward" in g for g in result["winnerGaps"])


def test_no_continuous_gap_when_candidate_is_close_to_winner_average():
    similar = [_trade(f"w{i}", "Win", rr=2.0) for i in range(4)]
    candidate = {"rr": 2.1, "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert not any("risk:reward" in g for g in result["winnerGaps"])


def test_winner_match_summary_reflects_actual_match_count():
    """Build a winning profile with 5 evaluable dimensions and a
    candidate that only matches 2 of them -- the summary must say so."""
    similar = [
        _trade(f"w{i}", "Win", h4PoiType="OB", premiumDiscount="Discount",
               session="London", h4Trend="Bearish", entry=100.0, sl=99.0, rr=3.0,
               m15Confirmations=[])
        for i in range(4)
    ]
    candidate = {
        "h4PoiType": "OB",              # matches
        "premiumDiscount": "Premium",   # mismatch
        "session": "New York",          # mismatch
        "h4Trend": "Bearish",           # matches
        "entry": 100.0, "sl": 95.0,     # much wider stop -- mismatch
        "rr": 3.1,                      # close enough -- matches
        "m15Confirmations": [],
    }
    result = build_characteristic_gaps(candidate, similar)
    # Evaluable dimensions here: h4PoiType, premiumDiscount, session,
    # h4Trend, stopDistancePct, rr = 6 total. Candidate matches
    # h4PoiType, h4Trend, and rr (close enough) = 3.
    assert result["winnerMatchTotal"] == 6
    assert result["winnerMatchCount"] == 3
    assert result["winnerMatchSummary"] == "This setup matches 3 of 6 characteristics your winning trades typically have."


def test_winner_match_fields_default_to_zero_without_enough_winners():
    similar = [_trade("w1", "Win"), _trade("l1", "Loss")]
    candidate = {"m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert result["winnerMatchCount"] == 0
    assert result["winnerMatchTotal"] == 0
    assert result["winnerMatchSummary"] is None


def test_loser_echo_for_similar_rr():
    similar = [_trade(f"l{i}", "Loss", rr=1.2) for i in range(4)]
    candidate = {"rr": 1.25, "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert any("risk:reward" in e.lower() for e in result["loserEchoes"])
