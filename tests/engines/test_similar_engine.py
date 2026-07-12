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
