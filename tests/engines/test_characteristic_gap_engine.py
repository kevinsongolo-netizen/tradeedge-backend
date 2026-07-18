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


def test_winner_checklist_has_short_labels_for_matched_and_missing():
    """Sprint 20 Phase 6 -- 'Compared with your winning trades' checklist:
    every evaluable dimension appears with a short ✓/✗-style label, not
    just the unmatched ones as prose (winnerGaps already does that)."""
    similar = [
        _trade(f"w{i}", "Win", pair="BTCUSD", direction="sell", session="London",
               m15Confirmations=["BOS", "Liquidity Sweep"])
        for i in range(4)
    ]
    candidate = {
        "pair": "BTCUSD",       # matches
        "direction": "sell",    # matches
        "session": "New York",  # mismatch
        "m15Confirmations": ["BOS"],  # missing Liquidity Sweep
    }
    result = build_characteristic_gaps(candidate, similar)
    labels = {row["label"]: row["matched"] for row in result["winnerChecklist"]}
    assert labels.get("Same Pair") is True
    assert labels.get("Same Direction") is True
    assert "London Session" in labels
    assert labels["London Session"] is False
    assert "Liquidity Sweep" in labels
    assert labels["Liquidity Sweep"] is False


def test_winner_checklist_empty_without_enough_winners():
    similar = [_trade("w1", "Win"), _trade("l1", "Loss")]
    candidate = {"m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert result["winnerChecklist"] == []


# --- Sprint 20 Phase 7 -- "AI Trade Mentor" weakness ranking ------------------

def test_standalone_weakness_flags_need_no_history():
    """Order Block mitigation, weak rejection, filled FVG, and
    counter-trend are self-evident regardless of sample size -- no
    similar trades needed for them to show up."""
    candidate = {
        "direction": "sell", "h4Trend": "Bullish",
        "m15Confirmations": ["Mitigated Order Block", "Weak Rejection", "Filled FVG"],
    }
    result = build_characteristic_gaps(candidate, [])
    labels = {w["label"] for w in result["weaknesses"]}
    assert "Order Block already mitigated" in labels
    assert "Weak rejection candle" in labels
    assert "Fair Value Gap already filled" in labels
    assert "Counter-trend setup" in labels


def test_no_counter_trend_flag_when_aligned():
    candidate = {"direction": "sell", "h4Trend": "Bearish", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, [])
    assert not any(w["label"] == "Counter-trend setup" for w in result["weaknesses"])


def test_weaknesses_ranked_most_severe_first():
    """A standalone flag (severity 100) must outrank a historical
    winner-gap miss with a lower share."""
    similar = [
        _trade(f"w{i}", "Win", session="London", m15Confirmations=["BOS"])
        for i in range(3)
    ] + [_trade("w4", "Win", session="New York", m15Confirmations=["BOS"])]  # dilutes session share below 100%
    candidate = {
        "session": "Asian",
        "m15Confirmations": ["Mitigated Order Block"],
    }
    result = build_characteristic_gaps(candidate, similar)
    weaknesses = result["weaknesses"]
    assert weaknesses[0]["label"] == "Order Block already mitigated"


def test_weakness_deduped_between_standalone_and_historical_echo():
    """A candidate that both standalone-flags AND historically echoes
    the same tag (e.g. Mitigated Order Block) should only see it once."""
    similar = [_trade(f"l{i}", "Loss", m15Confirmations=["Mitigated Order Block"]) for i in range(4)]
    candidate = {"m15Confirmations": ["Mitigated Order Block"]}
    result = build_characteristic_gaps(candidate, similar)
    count = sum(1 for w in result["weaknesses"] if w["label"] == "Order Block already mitigated")
    assert count == 1


def test_better_than_losers_surfaces_good_tag_pair():
    similar = [_trade(f"l{i}", "Loss", m15Confirmations=["Mitigated Order Block"]) for i in range(4)]
    candidate = {"m15Confirmations": ["Fresh Order Block"]}
    result = build_characteristic_gaps(candidate, similar)
    assert any("Fresh Order Block" in r for r in result["betterThanLosers"])


def test_better_than_losers_surfaces_higher_rr():
    similar = [_trade(f"l{i}", "Loss", rr=1.0, m15Confirmations=[]) for i in range(4)]
    candidate = {"rr": 3.0, "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert any("Risk:Reward" in r for r in result["betterThanLosers"])


def test_better_than_losers_never_claims_neutral_categorical_is_better():
    """Session/pair have no inherent 'better' direction -- must never
    appear in betterThanLosers even when they differ from losers."""
    similar = [_trade(f"l{i}", "Loss", session="Asian", m15Confirmations=[]) for i in range(4)]
    candidate = {"session": "London", "m15Confirmations": []}
    result = build_characteristic_gaps(candidate, similar)
    assert not any("session" in r.lower() or "London" in r for r in result["betterThanLosers"])


def test_weaknesses_and_better_than_losers_empty_without_enough_data():
    candidate = {"m15Confirmations": []}
    result = build_characteristic_gaps(candidate, [])
    assert result["betterThanLosers"] == []
