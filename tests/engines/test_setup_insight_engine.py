"""Setup Insight Engine tests (Sprint 20 — screenshot-first workflow).

Confirms the engine never emits a verdict (no tradeStatus/recommendation
field anywhere in its output), degrades honestly with thin history, and
produces sensible narrative/risk notes when there's a real match.
"""
import json
from pathlib import Path

import pytest

from app.engines.setup_insight_engine import (
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
