"""Setup Insight Engine tests (Sprint 20 — screenshot-first workflow).

Confirms the engine never emits a verdict (no tradeStatus/recommendation
field anywhere in its output), degrades honestly with thin history, and
produces sensible narrative/risk notes when there's a real match.
"""
import json
from pathlib import Path

import pytest

from app.engines.setup_insight_engine import (
    _detected_summary,
    build_setup_insight,
    candidate_from_vision_extraction,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_trades.json"


@pytest.fixture(scope="module")
def history():
    return json.loads(FIXTURES.read_text())


def test_candidate_from_vision_extraction_maps_direction_and_tags():
    extraction = {
        "pair": "GOLDmicro",
        "orderDirection": "SELL",
        "entry": 4001.14,
        "stopLoss": 4010.33,
        "takeProfit": 3982.77,
        "riskReward": 1.81,
        "lots": 0.06,
        "trend": "Bearish",
        "poiType": "Bearish Order Block",
        "premiumDiscount": "Premium",
        "latestEvent": "Bearish BOS detected",
        "liquidity": "Liquidity sweep above equal highs",
    }
    candidate = candidate_from_vision_extraction(extraction)
    assert candidate["pair"] == "GOLDmicro"
    assert candidate["direction"] == "sell"
    assert candidate["entry"] == 4001.14
    assert candidate["sl"] == 4010.33
    assert candidate["tp"] == 3982.77
    assert candidate["rr"] == 1.81
    assert "BOS" in candidate["m15Confirmations"]
    assert "Liquidity Sweep" in candidate["m15Confirmations"]


def test_candidate_from_vision_extraction_handles_missing_direction():
    candidate = candidate_from_vision_extraction({"pair": "EURUSD", "orderDirection": "NONE"})
    assert candidate["direction"] is None


def test_insufficient_history_returns_honest_message_not_a_fake_result():
    candidate = {"pair": "GOLDmicro", "direction": "sell", "rr": 1.8}
    thin_history = [{"id": "1", "pair": "GOLDmicro", "direction": "sell", "pnl": 10}]
    insight = build_setup_insight(candidate, thin_history)
    assert insight["hasEnoughHistory"] is False
    assert insight["sampleSize"] == 0
    assert insight["totalHistoryCount"] == 1
    assert "Not enough logged trades" in insight["narrative"][0]


def test_no_similar_matches_found_still_returns_data_not_a_verdict(history):
    candidate = {"id": "candidate", "pair": "ZZZNONEXISTENT", "direction": "buy", "rr": 99.0}
    insight = build_setup_insight(candidate, history)
    assert insight["hasEnoughHistory"] is True
    assert insight["sampleSize"] == 0
    assert insight["wins"] == 0 and insight["losses"] == 0
    assert "no similar setup found" in insight["narrative"][0]


def test_similar_matches_produce_narrative_and_consistent_counts(history):
    # Build a candidate that closely mirrors an existing history entry so
    # we're guaranteed at least one strong match.
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    assert insight["hasEnoughHistory"] is True
    assert insight["sampleSize"] >= 1
    assert insight["wins"] + insight["losses"] + insight["breakeven"] == insight["sampleSize"]
    assert len(insight["narrative"]) >= 2
    assert "similar" in insight["narrative"][0]
    assert 1 <= len(insight["topSimilar"]) <= 5


def test_output_never_contains_a_verdict_field(history):
    """The whole point of this engine: no tradeStatus/recommendation/
    VALID-INVALID gate anywhere, ever -- that decision stays with the
    trader."""
    candidate = dict(history[0])
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    forbidden_keys = {"tradeStatus", "recommendation", "verdict", "isValid"}
    assert forbidden_keys.isdisjoint(insight.keys())


def test_risk_note_flags_tight_rr_versus_winning_average():
    winners = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "pnl": 50, "rr": 3.0}
        for i in range(3)
    ]
    losers = [
        {"id": f"l{i}", "pair": "GOLDmicro", "direction": "sell", "pnl": -30, "rr": 1.0}
        for i in range(3)
    ]
    filler = [
        {"id": f"f{i}", "pair": "GOLDmicro", "direction": "sell", "pnl": 5, "rr": 2.0}
        for i in range(4)
    ]
    history_local = winners + losers + filler
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "rr": 1.1}
    insight = build_setup_insight(candidate, history_local, min_similarity=0)
    assert any("tighter than your average R:R" in note for note in insight["riskNotes"])


# --- Sprint 20 Phase 2 -- visual trade-memory cards: reasons + R-multiple --


def test_top_similar_includes_reasons_for_a_strong_match(history):
    """Building a candidate that's near-identical to a real history entry
    should surface WHY it's similar (same pair, same direction, etc.),
    not just a bare percentage."""
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    top = insight["topSimilar"][0]
    assert isinstance(top["reasons"], list)
    assert len(top["reasons"]) >= 1
    # The identical-trade match should at minimum explain the pair match.
    assert any("pair" in r.lower() or "direction" in r.lower() for r in top["reasons"])


def test_top_similar_r_multiple_is_signed_by_outcome(history):
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    top = insight["topSimilar"][0]
    if top["rr"] is not None:
        assert top["rMultiple"] is not None
        assert top["rMultiple"].endswith("R")
        if top["outcome"] == "Loss":
            assert top["rMultiple"].startswith("-")
        elif top["outcome"] == "Win":
            assert top["rMultiple"].startswith("+")


def test_top_similar_reasons_empty_list_not_missing_when_weak_match():
    """Even a match with no strong individual-feature reasons should
    still have a (possibly empty) reasons list, never a missing key."""
    history = [
        {"id": "h1", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09,
         "tp": 1.12, "rr": 2.0, "pnl": 10, "date": "2026-01-01"},
        {"id": "h2", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09,
         "tp": 1.12, "rr": 2.0, "pnl": 10, "date": "2026-01-02"},
        {"id": "h3", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09,
         "tp": 1.12, "rr": 2.0, "pnl": -5, "date": "2026-01-03"},
        {"id": "h4", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09,
         "tp": 1.12, "rr": 2.0, "pnl": 10, "date": "2026-01-04"},
        {"id": "h5", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09,
         "tp": 1.12, "rr": 2.0, "pnl": -5, "date": "2026-01-05"},
    ]
    candidate = {"id": "cand", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09, "tp": 1.12}
    insight = build_setup_insight(candidate, history, min_similarity=0)
    for top in insight["topSimilar"]:
        assert "reasons" in top
        assert isinstance(top["reasons"], list)


# --- Sprint 20 Phase 2 #6 -- "Detected: ..." line restates the exact
# read, in the trader's own terms, before any history comparison ------


def test_detected_summary_restates_exact_read_not_generic_bot_speak():
    raw = {
        "pair": "GOLDmicro",
        "orderDirection": "BUY",
        "orderType": "Buy Limit",
        "entry": 4001.14,
        "stopLoss": 3982.77,
        "takeProfit": 4030.0,
        "riskReward": 1.81,
        "trend": "Bullish",
        "poiType": "Bullish Order Block",
        "premiumDiscount": "Discount",
        "latestEvent": "Bullish CHOCH detected",
        "liquidity": "Liquidity sweep below equal lows",
    }
    summary = _detected_summary(raw)
    assert summary is not None
    assert summary.startswith("Detected:")
    assert "Bullish Order Block" in summary
    assert "Bullish CHOCH detected" in summary
    assert "Discount zone" in summary
    assert "Liquidity sweep below equal lows" in summary
    assert "GOLDmicro" in summary
    assert "Buy Limit" in summary
    assert "Entry 4001.14" in summary
    assert "R:R 1.81" in summary


def test_detected_summary_is_none_when_nothing_to_show():
    assert _detected_summary(None) is None
    assert _detected_summary({}) is None


def test_detected_summary_prepended_to_narrative_when_history_thin():
    candidate = {"pair": "GOLDmicro", "direction": "sell", "rr": 1.8}
    thin_history = [{"id": "1", "pair": "GOLDmicro", "direction": "sell", "pnl": 10}]
    raw = {"pair": "GOLDmicro", "orderType": "Sell Limit", "poiType": "Bearish Order Block"}
    insight = build_setup_insight(candidate, thin_history, raw_extraction=raw)
    assert insight["narrative"][0].startswith("Detected:")
    assert "Not enough logged trades" in insight["narrative"][1]


def test_detected_summary_prepended_to_narrative_on_a_real_match(history):
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    raw = {"pair": candidate["pair"], "orderType": "Buy Limit", "poiType": "Bullish FVG", "trend": "Bullish"}
    insight = build_setup_insight(candidate, history, raw_extraction=raw)
    assert insight["narrative"][0].startswith("Detected:")
    assert "similar" in insight["narrative"][1]


def test_no_raw_extraction_supplied_narrative_unchanged(history):
    """Backwards compatible -- omitting raw_extraction (e.g. a candidate
    not built from a screenshot) skips the detected line entirely
    rather than erroring or inserting a blank line."""
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    assert "similar" in insight["narrative"][0]
