"""Phase 2 — feature engineering pipeline tests."""
import pandas as pd

from app.ml.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    NUMERIC_FEATURES,
    add_hist_strategy_health,
    build_preprocessor,
    historical_features_for_candidate,
    historical_strategy_health_for_candidate,
    prepare_candidate_row,
    prepare_training_data,
    rows_to_frame,
)


def _entry(id_, date, *, pair="EURUSD", pnl=50.0, rr=2.0, rule_score=80, execution_score=75, **extra):
    row = {
        "id": id_,
        "date": date,
        "pair": pair,
        "asset": "Forex",
        "direction": "buy",
        "session": "London",
        "h4_trend": "Bullish",
        "h4_poi_type": "Order Block",
        "emotion": "Calm",
        "has_bos": 1,
        "has_choch": 0,
        "has_liquidity_sweep": 1,
        "planned_rr": rr,
        "rule_score": rule_score,
        "execution_score": execution_score,
        "confidence": 4,
        "rules_followed": "all",
        "followed_plan": "Yes",
        "stop_loss": 1.1,
        "exit_reason": "TP",
        "pnl": pnl,
        "rr": rr,
        "outcome": "Win" if pnl > 0 else "Loss",
        "y_win": 1 if pnl > 0 else 0,
        "validation_status": "valid",
    }
    row.update(extra)
    return row


def test_rows_to_frame_projects_exactly_feature_columns():
    rows = [_entry("a", "2026-01-01")]
    frame = rows_to_frame(rows)
    assert list(frame.columns) == FEATURE_COLUMNS


def test_rows_to_frame_fills_missing_columns_with_nan():
    frame = rows_to_frame([{"id": "a"}])
    assert frame.shape == (1, len(FEATURE_COLUMNS))
    assert frame["rule_score"].isna().all()


def test_build_preprocessor_fits_and_transforms():
    rows = [_entry(str(i), f"2026-01-{i+1:02d}", pair=("EURUSD" if i % 2 else "GBPUSD")) for i in range(10)]
    X, y = prepare_training_data(rows)
    preprocessor = build_preprocessor()
    transformed = preprocessor.fit_transform(X)
    assert transformed.shape[0] == 10
    assert len(y) == 10


def test_add_hist_strategy_health_is_none_for_first_row_then_populated():
    rows = [_entry(str(i), f"2026-01-{i+1:02d}") for i in range(5)]
    result = add_hist_strategy_health(rows)
    assert result[0]["hist_strategy_health_score"] is None
    # By the 5th row there's real prior history to compute a score from.
    assert result[-1]["hist_strategy_health_score"] is not None


def test_historical_strategy_health_for_candidate_uses_all_existing_rows():
    rows = [_entry(str(i), f"2026-01-{i+1:02d}") for i in range(5)]
    assert historical_strategy_health_for_candidate([]) is None
    assert historical_strategy_health_for_candidate(rows) is not None


def test_historical_features_for_candidate_only_sees_prior_trades():
    entries = [_entry(str(i), f"2026-01-{i+1:02d}", pnl=50.0) for i in range(10)]
    hist = historical_features_for_candidate(entries, {"pair": "EURUSD", "session": "London"})
    # All 10 prior trades won, so the rolling win rate should reflect that.
    assert hist["hist_win_rate_all"] == 1.0
    assert hist["hist_win_rate_pair"] == 1.0


def test_historical_features_for_candidate_empty_history_returns_nones():
    hist = historical_features_for_candidate([], {"pair": "EURUSD", "session": "London"})
    assert hist["hist_win_rate_all"] is None
    assert hist["hist_avg_rr_all"] is None


def test_prepare_candidate_row_shape_matches_feature_columns():
    entries = [_entry(str(i), f"2026-01-{i+1:02d}") for i in range(5)]
    candidate = {
        "pair": "eurusd", "asset": "Forex", "direction": "buy", "session": "London",
        "h4_trend": "Bullish", "h4_poi_type": "Order Block", "emotion": "Calm",
        "has_bos": True, "has_choch": False, "has_liquidity_sweep": True,
        "planned_rr": 2.5, "rule_score": 85, "execution_score": None, "confidence": 4,
    }
    row = prepare_candidate_row(entries, candidate)
    assert list(row.columns) == FEATURE_COLUMNS
    assert row.iloc[0]["pair"] == "EURUSD"  # upper-cased
    assert len(row) == 1


def test_feature_column_lists_partition_correctly():
    assert set(CATEGORICAL_FEATURES) & set(NUMERIC_FEATURES) == set()
    assert set(CATEGORICAL_FEATURES) | set(NUMERIC_FEATURES) == set(FEATURE_COLUMNS)
