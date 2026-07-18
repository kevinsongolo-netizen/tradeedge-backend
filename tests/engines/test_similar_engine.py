"""Similar Trade Engine tests — weighted-v1 algorithm + legacy parity."""
import json
from pathlib import Path

import pytest

from app.engines.similar_engine import (
    normalize_similarity_weights,
    search_similar,
    search_similar_legacy,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sample_trades.json"


@pytest.fixture(scope="module")
def history():
    return json.loads(FIXTURES.read_text())


def test_identical_trade_is_100_percent_similar(history):
    candidate = dict(history[0])
    candidate["id"] = "a-different-id-entirely"
    result = search_similar(candidate, [history[0]])
    assert len(result["similar"]) == 1
    assert result["similar"][0]["similarity"] == 100.0


def test_self_exclusion_by_id(history):
    candidate = dict(history[0])  # same id as history[0]
    result = search_similar(candidate, history)
    assert all(m["id"] != candidate["id"] for m in result["similar"])


def test_completely_different_trade_scores_low():
    candidate = {"id": "x", "pair": "EURUSD", "direction": "buy", "session": "London", "rr": 3.0, "confidence": 90}
    entry = {"id": "y", "pair": "BTCUSD", "direction": "sell", "session": "Asian", "rr": 0.3, "confidence": 20}
    result = search_similar(candidate, [entry], min_similarity=0)
    assert result["similar"][0]["similarity"] < 40


def test_min_similarity_filters_out_weak_matches(history):
    candidate = dict(history[0])
    candidate["id"] = "diff"
    result_strict = search_similar(candidate, history, min_similarity=99.9)
    result_loose = search_similar(candidate, history, min_similarity=0)
    assert len(result_strict["similar"]) <= len(result_loose["similar"])


def test_limit_truncates_results(history):
    candidate = dict(history[0])
    candidate["id"] = "diff"
    result = search_similar(candidate, history, min_similarity=0, limit=3)
    assert len(result["similar"]) <= 3


def test_aggregate_outputs_present(history):
    candidate = dict(history[0])
    candidate["id"] = "diff"
    result = search_similar(candidate, history, min_similarity=0, limit=10)
    for key in ("wins", "losses", "breakeven", "winRate", "averageRR", "averageProfit", "confidence", "algorithm", "weightsSnapshot"):
        assert key in result


def test_every_match_has_outcome_field(history):
    candidate = dict(history[0])
    candidate["id"] = "diff"
    result = search_similar(candidate, history, min_similarity=0, limit=5)
    for match in result["similar"]:
        assert match["outcome"] in ("Win", "Loss", "Breakeven")


def test_weights_normalize_to_100():
    weights = normalize_similarity_weights({"pair": 500})
    assert abs(sum(weights.values()) - 100) < 1e-9


def test_empty_history_returns_empty_result():
    result = search_similar({"pair": "EURUSD"}, [])
    assert result["similar"] == []
    assert result["winRate"] is None


def test_legacy_algorithm_runs_and_returns_same_shape(history):
    candidate = dict(history[0])
    candidate["id"] = "diff"
    result = search_similar_legacy(candidate, history)
    assert result["algorithm"] == "legacy"
    for key in ("similar", "wins", "losses", "winRate", "averageRR"):
        assert key in result


def test_entry_proximity_only_applies_to_same_pair():
    candidate = {"id": "a", "pair": "EURUSD", "entry": 1.1000}
    same_pair_close = {"id": "b", "pair": "EURUSD", "entry": 1.1001}
    diff_pair_close = {"id": "c", "pair": "GBPUSD", "entry": 1.1001}
    r1 = search_similar(candidate, [same_pair_close], min_similarity=0)
    r2 = search_similar(candidate, [diff_pair_close], min_similarity=0)
    assert r1["similar"][0]["similarity"] >= r2["similar"][0]["similarity"]


# --- Sprint 20 Phase 2 -- stop/target placement as their own dimensions ----


def test_same_rr_but_very_different_stop_size_scores_lower_than_matching_stop_size():
    """Two trades can share the exact same R:R with wildly different risk
    sizing (a 0.1%-of-price stop vs. a 5%-of-price stop) -- similarity
    should treat those as meaningfully different setups, not identical
    just because the ratio matches."""
    candidate = {
        "id": "cand", "pair": "EURUSD", "direction": "buy",
        "entry": 1.1000, "sl": 1.0989, "tp": 1.1033,  # tight stop, ~0.1% risk, R:R ~3
    }
    tight_match = {
        "id": "tight", "pair": "EURUSD", "direction": "buy",
        "entry": 1.2000, "sl": 1.1988, "tp": 1.2036,  # same ~0.1% risk, same R:R
        "pnl": 10,
    }
    wide_mismatch = {
        "id": "wide", "pair": "EURUSD", "direction": "buy",
        "entry": 1.1000, "sl": 1.0450, "tp": 1.1165,  # ~5% risk, same R:R ~3
        "pnl": -10,
    }
    result = search_similar(candidate, [tight_match, wide_mismatch], min_similarity=0, limit=10)
    by_id = {m["id"]: m["similarity"] for m in result["similar"]}
    assert by_id["tight"] > by_id["wide"]


def test_stop_distance_pct_present_only_with_entry_and_sl():
    candidate_missing_sl = {"id": "a", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "rr": 2.0}
    entry = {"id": "b", "pair": "EURUSD", "direction": "buy", "entry": 1.1, "sl": 1.09, "tp": 1.12, "rr": 2.0}
    # Should not blow up even though the candidate has no SL to compare.
    result = search_similar(candidate_missing_sl, [entry], min_similarity=0)
    assert len(result["similar"]) == 1


def test_target_distance_pct_contributes_to_similarity():
    candidate = {"id": "cand", "pair": "GOLDmicro", "direction": "sell", "entry": 4000, "sl": 4010, "tp": 3980}
    close_target = {"id": "close", "pair": "GOLDmicro", "direction": "sell", "entry": 4000, "sl": 4010, "tp": 3979, "pnl": 5}
    far_target = {"id": "far", "pair": "GOLDmicro", "direction": "sell", "entry": 4000, "sl": 4010, "tp": 3800, "pnl": -5}
    result = search_similar(candidate, [close_target, far_target], min_similarity=0)
    by_id = {m["id"]: m["similarity"] for m in result["similar"]}
    assert by_id["close"] > by_id["far"]


# --- Sprint 20 Phase 4 -- orderType and FVG as their own dimensions --------


def test_order_type_matching_scores_higher_than_mismatched():
    """Market vs. limit vs. stop, bucketed from free text -- same
    direction/pair on both candidates so orderType is the only thing
    that differs between the two comparisons."""
    candidate = {"id": "cand", "pair": "EURUSD", "direction": "buy", "orderType": "Buy Limit"}
    same_type = {"id": "match", "pair": "EURUSD", "direction": "buy", "orderType": "Buy Limit", "pnl": 5}
    diff_type = {"id": "mismatch", "pair": "EURUSD", "direction": "buy", "orderType": "Market", "pnl": -5}
    result = search_similar(candidate, [same_type, diff_type], min_similarity=0)
    by_id = {m["id"]: m["similarity"] for m in result["similar"]}
    assert by_id["match"] > by_id["mismatch"]


def test_order_type_ignores_direction_word_same_category():
    """"Buy Limit" and "Sell Limit" should score as the SAME order-type
    category (direction is already its own separate dimension) --
    verified directly against the category helper, not diluted by other
    similarity dimensions."""
    from app.engines.similar_engine import _order_type_similarity
    assert _order_type_similarity("Buy Limit", "Sell Limit") == 1.0
    assert _order_type_similarity("Buy Limit", "Market") == 0.0


def test_order_type_absent_when_not_recognized():
    """A candidate with no orderType (or unrecognized text) shouldn't
    have this dimension counted at all -- never blow up either."""
    candidate = {"id": "a", "pair": "EURUSD", "direction": "buy"}
    entry = {"id": "b", "pair": "EURUSD", "direction": "buy", "orderType": "Buy Limit", "pnl": 5}
    result = search_similar(candidate, [entry], min_similarity=0)
    assert len(result["similar"]) == 1


def test_fvg_presence_matching_scores_higher_than_mismatched():
    """User's own ask: FVG presence should be its own similarity
    dimension, not just implicitly folded into h4PoiType."""
    candidate = {"id": "cand", "pair": "GOLDmicro", "direction": "sell", "m15Confirmations": ["FVG"]}
    has_fvg = {"id": "match", "pair": "GOLDmicro", "direction": "sell", "m15Confirmations": ["FVG"], "pnl": 5}
    no_fvg = {"id": "mismatch", "pair": "GOLDmicro", "direction": "sell", "m15Confirmations": [], "pnl": -5}
    result = search_similar(candidate, [has_fvg, no_fvg], min_similarity=0)
    by_id = {m["id"]: m["similarity"] for m in result["similar"]}
    assert by_id["match"] > by_id["mismatch"]


def test_timeframe_matching_scores_higher_than_mismatched():
    """Sprint 20 Phase 5 -- timeframe (M15/H1/...) was read off every
    screenshot all along but never actually compared. Same
    direction/pair on both comparisons so timeframe is the only thing
    that differs."""
    candidate = {"id": "cand", "pair": "EURUSD", "direction": "buy", "timeframe": "M15"}
    same_tf = {"id": "match", "pair": "EURUSD", "direction": "buy", "timeframe": "M15", "pnl": 5}
    diff_tf = {"id": "mismatch", "pair": "EURUSD", "direction": "buy", "timeframe": "H4", "pnl": -5}
    result = search_similar(candidate, [same_tf, diff_tf], min_similarity=0)
    by_id = {m["id"]: m["similarity"] for m in result["similar"]}
    assert by_id["match"] > by_id["mismatch"]


def test_timeframe_absent_when_not_set():
    candidate = {"id": "a", "pair": "EURUSD", "direction": "buy"}
    entry = {"id": "b", "pair": "EURUSD", "direction": "buy", "timeframe": "M15", "pnl": 5}
    result = search_similar(candidate, [entry], min_similarity=0)
    assert len(result["similar"]) == 1
