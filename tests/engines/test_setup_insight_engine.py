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


def test_candidate_from_vision_extraction_maps_phase6_characteristics():
    """Sprint 20 Phase 6 -- order block freshness, rejection strength,
    and FVG size become tags on m15Confirmations, same mechanism as
    BOS/CHoCH/liquidity sweep/FVG."""
    fresh = candidate_from_vision_extraction({"orderBlockFreshness": "Fresh", "rejectionStrength": "Strong", "fvgSize": "Large"})
    assert "Fresh Order Block" in fresh["m15Confirmations"]
    assert "Strong Rejection" in fresh["m15Confirmations"]
    assert "Large FVG" in fresh["m15Confirmations"]

    mitigated = candidate_from_vision_extraction({"orderBlockFreshness": "Mitigated", "rejectionStrength": "Weak", "fvgSize": "Small"})
    assert "Mitigated Order Block" in mitigated["m15Confirmations"]
    assert "Strong Rejection" not in mitigated["m15Confirmations"]
    assert "Large FVG" not in mitigated["m15Confirmations"]


def test_candidate_from_vision_extraction_maps_phase8_characteristics():
    """Sprint 20 Phase 8 ("AI Learning Engine") -- equal highs/lows, BOS
    type, and touch number all become tags, plus Fresh/Mitigated FVG."""
    fresh_fvg = candidate_from_vision_extraction({
        "fvgStatus": "Bullish FVG unmitigated",
        "equalHighsNearby": True,
        "equalLowsNearby": False,
        "bosType": "External",
        "touchNumber": "First",
    })
    assert "Fresh FVG" in fresh_fvg["m15Confirmations"]
    assert "Equal Highs Nearby" in fresh_fvg["m15Confirmations"]
    assert "Equal Lows Nearby" not in fresh_fvg["m15Confirmations"]
    assert "External BOS" in fresh_fvg["m15Confirmations"]
    assert "First Touch" in fresh_fvg["m15Confirmations"]

    mitigated_fvg = candidate_from_vision_extraction({
        "fvgStatus": "Bearish FVG mitigated",
        "bosType": "Internal",
        "touchNumber": "Second",
    })
    assert "Mitigated FVG" in mitigated_fvg["m15Confirmations"]
    assert "Filled FVG" in mitigated_fvg["m15Confirmations"]
    assert "Fresh FVG" not in mitigated_fvg["m15Confirmations"]
    assert "Internal BOS" in mitigated_fvg["m15Confirmations"]
    assert "Second Touch" in mitigated_fvg["m15Confirmations"]

    third_touch = candidate_from_vision_extraction({"touchNumber": "Third+"})
    assert "Third+ Touch" in third_touch["m15Confirmations"]


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


def test_low_confidence_message_shown_instead_of_misleading_win_rate():
    """Sprint 20 Phase 4 -- a "0%" or "100%" win rate computed from 1-2
    similar trades is not a real statistic. Below MIN_SIMILAR_FOR_
    CONFIDENT_STAT (3), winRate/averageRR/averageProfit must be
    withheld (None) and the narrative must say so in plain language,
    even though there IS enough TOTAL history logged overall."""
    reference = {
        "id": "match-1", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
        "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": -50.0, "outcome": "Loss",
    }
    # 4 unrelated trades (different pair/direction/asset) so they fall
    # below the default similarity threshold and never join the match.
    padding = [
        {"id": f"pad-{i}", "pair": "EURUSD", "direction": "buy", "asset": "Forex",
         "entry": 1.10, "sl": 1.095, "tp": 1.12, "rr": 2.0, "pnl": 20.0, "outcome": "Win"}
        for i in range(4)
    ]
    history = [reference] + padding
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0}

    insight = build_setup_insight(candidate, history)
    assert insight["hasEnoughHistory"] is True
    assert insight["sampleSize"] == 1
    assert insight["lowConfidence"] is True
    assert insight["winRate"] is None
    assert insight["averageRR"] is None
    assert insight["averageProfit"] is None
    assert any("Low confidence" in line and "Continue journaling" in line for line in insight["narrative"])
    # Must NOT state a bare win-rate percentage anywhere in the narrative.
    assert not any("win rate)." in line for line in insight["narrative"])


def test_high_confidence_stats_shown_once_sample_clears_the_bar():
    """Same shape but with >=3 similar trades -- the normal, confident
    win-rate narrative and real stats must be present, unaffected by
    the new low-confidence gate."""
    matches = [
        {"id": f"match-{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0, "outcome": "Win"}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0}

    insight = build_setup_insight(candidate, matches)
    assert insight["sampleSize"] >= 3
    assert insight["lowConfidence"] is False
    assert insight["winRate"] is not None
    assert any("win rate)." in line for line in insight["narrative"])


def test_build_setup_insight_includes_characteristic_gaps(history):
    """Sprint 20 Phase 4 -- build_setup_insight must surface the
    winner/loser characteristic-gap analysis alongside the existing
    similarity narrative, computed from the same similar-trade list."""
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    assert "characteristicGaps" in insight
    gaps = insight["characteristicGaps"]
    assert "hasEnoughData" in gaps
    assert "winnerGaps" in gaps and "loserEchoes" in gaps


def test_characteristic_gaps_absent_stats_when_thin_history():
    """When there isn't even enough TOTAL history yet, no gap analysis
    is attempted (there's no similar list to draw from)."""
    candidate = {"pair": "GOLDmicro", "direction": "sell", "rr": 1.8}
    thin_history = [{"id": "1", "pair": "GOLDmicro", "direction": "sell", "pnl": 10}]
    insight = build_setup_insight(candidate, thin_history)
    assert "characteristicGaps" not in insight or insight.get("characteristicGaps") is None


def test_top_similar_includes_the_matched_trades_own_screenshot():
    """Sprint 20 Phase 5 -- each similar trade card must carry that
    past trade's own entry screenshot URL, so the trader can visually
    compare it to the current setup, not just read a similarity %."""
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0,
         "screenshots": [{"url": "https://cdn.example/entry.png", "kind": "entry"}]}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0}
    insight = build_setup_insight(candidate, matches)
    assert insight["topSimilar"], "expected at least one similar match"
    for s in insight["topSimilar"]:
        assert s["screenshotUrl"] == "https://cdn.example/entry.png"


def test_top_similar_screenshot_url_is_none_when_trade_has_no_screenshot():
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0}
    insight = build_setup_insight(candidate, matches)
    for s in insight["topSimilar"]:
        assert s["screenshotUrl"] is None


def test_top_similar_breakdown_shows_both_matches_and_mismatches():
    """Sprint 20 Phase 5 -- 'explain why the similarity score is what it
    is': the breakdown must include dimensions that DIDN'T match too
    (Different session, Different trend, ...), not just the good ones."""
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0,
         "session": "New York", "h4Trend": "Bullish"}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0,
                 "session": "London", "h4Trend": "Bearish"}
    insight = build_setup_insight(candidate, matches)
    assert insight["topSimilar"], "expected at least one similar match"
    row = insight["topSimilar"][0]
    breakdown = row["breakdown"]
    by_feature = {b["feature"]: b for b in breakdown}
    # Same pair/direction/asset/rr -> matched.
    assert by_feature["pair"]["matched"] is True
    assert by_feature["direction"]["matched"] is True
    # Different session/trend -> present in the breakdown AND marked mismatched.
    assert by_feature["session"]["matched"] is False
    assert by_feature["h4Trend"]["matched"] is False
    # Every row has a human label, not just the raw feature key.
    assert all(b["label"] for b in breakdown)


def test_breakdown_only_includes_dimensions_actually_evaluated():
    """A dimension the candidate never set (e.g. no session given) must
    not appear in the breakdown at all -- nothing to explain about a
    comparison that was never made."""
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "session": "London", "pnl": 5}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell"}  # no session set
    insight = build_setup_insight(candidate, matches)
    row = insight["topSimilar"][0]
    features = {b["feature"] for b in row["breakdown"]}
    assert "session" not in features


def test_reasons_list_still_capped_at_three_after_untruncating_contributions():
    """similar_engine no longer pre-truncates contributions to the top 3
    -- _contribution_reasons must still cap its own curated output at 3
    so the short 'why similar' bullet list doesn't balloon."""
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "session": "London", "h4Trend": "Bearish", "premiumDiscount": "Discount",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0,
         "m15Confirmations": ["BOS", "CHOCH", "Liquidity Sweep", "FVG"]}
        for i in range(5)
    ]
    candidate = dict(matches[0])
    candidate["id"] = "candidate"
    insight = build_setup_insight(candidate, matches)
    assert len(insight["topSimilar"][0]["reasons"]) <= 3


def test_candidate_from_vision_extraction_maps_timeframe():
    """Sprint 20 Phase 5 -- timeframe was read off every screenshot all
    along (see VISION_ANALYSIS_SCHEMA_HINT) but never carried into the
    candidate used for similarity comparison until now."""
    extraction = {"pair": "EURUSD", "orderDirection": "BUY", "timeframe": "M15"}
    candidate = candidate_from_vision_extraction(extraction)
    assert candidate["timeframe"] == "M15"


def test_breakdown_points_are_signed_percent_of_total_weight():
    """Sprint 20 Phase 6 -- each breakdown row also carries its actual
    signed point contribution (e.g. +20/-10), not just matched/mismatched,
    so the UI can show '✓ Same Pair (+20%)' / '✗ Different Session (-10%)'.
    Matched rows get positive points, mismatched rows negative, and the
    magnitude is that dimension's weight share of everything evaluated."""
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
         "entry": 4000.0, "sl": 4010.0, "tp": 3970.0, "rr": 3.0, "pnl": 60.0,
         "session": "New York", "h4Trend": "Bullish"}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell", "asset": "Metals",
                 "entry": 4001.0, "sl": 4011.0, "tp": 3971.0, "rr": 3.0,
                 "session": "London", "h4Trend": "Bearish"}
    insight = build_setup_insight(candidate, matches)
    row = insight["topSimilar"][0]
    by_feature = {b["feature"]: b for b in row["breakdown"]}
    assert by_feature["pair"]["points"] > 0
    assert by_feature["session"]["points"] < 0
    assert by_feature["h4Trend"]["points"] < 0
    total_weight_points = sum(abs(b["points"]) for b in row["breakdown"])
    # Signed points are each a share of 100 -- the total magnitude across
    # every evaluated dimension should land close to 100.
    assert 90 <= total_weight_points <= 110


def test_confidence_explanation_populated_when_low_confidence(history):
    """Sprint 20 Phase 7 -- 'AI Confidence Explanation': itemized reasons
    accompany the low-confidence narrative, not just the bare sentence."""
    thin_history = [
        {"id": "t1", "pair": "GOLDmicro", "direction": "sell", "pnl": -50.0, "date": "2026-01-01"},
        {"id": "t2", "pair": "GOLDmicro", "direction": "sell", "pnl": 10.0, "date": "2026-01-02"},
    ]
    candidate = {"pair": "GOLDmicro", "direction": "sell"}
    insight = build_setup_insight(candidate, thin_history, min_total_history=1)
    assert insight["lowConfidence"] is True
    explanation = insight["confidenceExplanation"]
    assert any("2 similar trades" in r or "Only 2" in r for r in explanation)
    assert any("1 of them" in r for r in explanation)


def test_confidence_explanation_empty_when_confident(history):
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "pnl": 60.0}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell"}
    insight = build_setup_insight(candidate, matches)
    assert insight["lowConfidence"] is False
    assert insight["confidenceExplanation"] == []


def test_improvement_suggestions_reuse_winner_checklist_missing_rows(history):
    matches = [
        {"id": f"w{i}", "pair": "GOLDmicro", "direction": "sell", "pnl": 60.0,
         "session": "London", "m15Confirmations": ["Liquidity Sweep"]}
        for i in range(5)
    ]
    candidate = {"id": "candidate", "pair": "GOLDmicro", "direction": "sell",
                 "session": "New York", "m15Confirmations": []}
    insight = build_setup_insight(candidate, matches)
    suggestions = insight["characteristicGaps"]["improvementSuggestions"]
    assert any("London Session" in s for s in suggestions)
    assert any("Liquidity Sweep" in s for s in suggestions)
    assert all(s.startswith("Wait for:") for s in suggestions)


def test_build_setup_insight_includes_edge_profile(history):
    """Sprint 20 Phase 8 -- "AI Learning Engine": build_setup_insight
    must surface the whole-history characteristic discovery (edge
    profile), computed from the FULL history (not just the similar
    subset), and compare it against the candidate."""
    reference = history[0]
    candidate = dict(reference)
    candidate["id"] = "brand-new-candidate"
    insight = build_setup_insight(candidate, history)
    assert "edgeProfile" in insight
    profile = insight["edgeProfile"]
    assert profile is not None
    assert profile["hasEnoughData"] is True
    assert "winnerCharacteristics" in profile and "loserCharacteristics" in profile
    assert "winnerMatchCount" in profile and "winnerMatches" in profile
    assert "loserMatchCount" in profile and "loserMatches" in profile
    assert profile["winnerMatchTotal"] == len(profile["winnerCharacteristics"])
    assert profile["loserMatchTotal"] == len(profile["loserCharacteristics"])


def test_edge_profile_absent_when_thin_total_history():
    """When there isn't even enough TOTAL history yet, edgeProfile is
    never attempted (matches characteristicGaps' own convention)."""
    candidate = {"pair": "GOLDmicro", "direction": "sell", "rr": 1.8}
    thin_history = [{"id": "1", "pair": "GOLDmicro", "direction": "sell", "pnl": 10}]
    insight = build_setup_insight(candidate, thin_history)
    assert "edgeProfile" not in insight or insight.get("edgeProfile") is None
