"""Phase 3/4 — training pipeline + model comparison tests."""
import random

import pytest

from app.ml.features import prepare_training_data
from app.ml.train import (
    MIN_ROWS_FOR_SPLIT,
    InsufficientDataError,
    compute_metrics,
    split_dataset,
    train_and_compare,
)


def _synthetic_rows(n=80, seed=7):
    rng = random.Random(seed)
    pairs = ["EURUSD", "GBPUSD", "XAUUSD"]
    sessions = ["London", "New York", "Asian"]
    trends = ["Bullish", "Bearish", "Ranging"]
    pois = ["Order Block", "FVG", "Liquidity"]
    emotions = ["Calm", "Confident", "FOMO", "Anxious"]

    rows = []
    for i in range(n):
        good_setup = rng.random() < 0.5
        win = rng.random() < (0.7 if good_setup else 0.3)
        pnl = rng.uniform(20, 200) if win else -rng.uniform(20, 150)
        rows.append({
            "id": f"t{i}", "date": f"2026-01-{(i % 28) + 1:02d}",
            "pair": rng.choice(pairs), "asset": "Forex", "direction": rng.choice(["buy", "sell"]),
            "session": rng.choice(sessions), "h4_trend": rng.choice(trends), "h4_poi_type": rng.choice(pois),
            "emotion": rng.choice(emotions),
            "has_bos": int(good_setup), "has_choch": int(not good_setup), "has_liquidity_sweep": rng.randint(0, 1),
            "planned_rr": round(rng.uniform(1, 4), 2),
            "rule_score": rng.randint(60, 95) if good_setup else rng.randint(30, 80),
            "execution_score": rng.randint(50, 95),
            "confidence": rng.randint(1, 5),
            "rules_followed": "all", "followed_plan": "Yes", "stop_loss": 1.1, "exit_reason": "TP",
            "pnl": pnl, "rr": abs(pnl) / 50,
            "validation_status": "valid",
            "outcome": "Win" if pnl > 0 else "Loss",
            "y_win": 1 if pnl > 0 else 0,
        })
    return rows


def test_insufficient_data_raises_before_splitting():
    X, y = prepare_training_data(_synthetic_rows(n=5))
    with pytest.raises(InsufficientDataError):
        train_and_compare(X, y)


def test_insufficient_data_error_message_mentions_minimum():
    X, y = prepare_training_data(_synthetic_rows(n=MIN_ROWS_FOR_SPLIT - 1))
    with pytest.raises(InsufficientDataError) as exc_info:
        train_and_compare(X, y)
    assert str(MIN_ROWS_FOR_SPLIT) in str(exc_info.value)


def test_split_dataset_produces_three_disjoint_splits():
    X, y = prepare_training_data(_synthetic_rows(n=80))
    X_train, X_val, X_test, y_train, y_val, y_test = split_dataset(X, y)
    assert len(X_train) + len(X_val) + len(X_test) == 80
    all_idx = set(X_train.index) | set(X_val.index) | set(X_test.index)
    assert len(all_idx) == 80  # no overlap


def test_train_and_compare_selects_a_valid_algorithm_and_reports_all_metrics():
    X, y = prepare_training_data(_synthetic_rows(n=80))
    outcome = train_and_compare(X, y)
    assert outcome.algorithm in {"logistic_regression", "random_forest", "gradient_boosting"}
    assert set(outcome.candidates.keys()) == {"logistic_regression", "random_forest", "gradient_boosting"}
    for metrics in outcome.candidates.values():
        assert set(metrics.keys()) == {"accuracy", "precision", "recall", "f1", "rocAuc"}
    assert 0.0 <= outcome.test_metrics["accuracy"] <= 1.0
    assert outcome.rows_used == 80
    assert isinstance(outcome.overfit_warning, bool)
    # The fitted pipeline should be usable for prediction immediately.
    assert hasattr(outcome.pipeline, "predict_proba")


def test_compute_metrics_handles_single_class_roc_auc_gracefully():
    import pandas as pd
    y_true = pd.Series([1, 1, 1, 1])
    y_pred = [1, 1, 1, 1]
    y_proba = [0.9, 0.8, 0.95, 0.7]
    metrics = compute_metrics(y_true, y_pred, y_proba)
    assert metrics["rocAuc"] is None  # can't compute AUC with only one class present
    assert metrics["accuracy"] == 1.0
