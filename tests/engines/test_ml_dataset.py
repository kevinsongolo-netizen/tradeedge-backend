"""ML Dataset Builder tests — schema, leakage safety, validation, CSV."""
from app.engines.ml_dataset import ML_COLUMN_ORDER, build_dataset, to_csv, validate_dataset, validate_row

ENTRIES = [
    {
        "id": "1", "date": "2026-01-01", "pair": "eurusd", "direction": "buy", "asset": "Forex",
        "entry": 1.10, "sl": 1.09, "tp": 1.12, "exit": 1.12, "pnl": 100, "rr": 2.0,
        "session": "London", "ruleScore": 80, "executionScore": 85, "overallScore": 82,
        "ruleRecommendation": "TAKE", "executionGrade": "GOOD",
    },
    {
        "id": "2", "date": "2026-01-02", "pair": "eurusd", "direction": "sell", "asset": "Forex",
        "entry": 1.11, "sl": 1.12, "tp": 1.09, "exit": 1.09, "pnl": -80, "rr": 1.5,
        "session": "London", "ruleScore": 60, "executionScore": 50, "overallScore": 55,
        "ruleRecommendation": "CAUTION", "executionGrade": "FAIR",
    },
]


def test_build_dataset_produces_snake_case_columns():
    rows = build_dataset(ENTRIES)
    assert set(rows[0].keys()) == set(ML_COLUMN_ORDER)


def test_historical_columns_never_see_future_trades():
    rows = build_dataset(ENTRIES)
    # First (chronologically earliest) row has no prior history.
    assert rows[0]["hist_trades_total"] == 0
    # Second row's history reflects exactly the first trade.
    assert rows[1]["hist_trades_total"] == 1
    assert rows[1]["hist_trades_pair"] == 1


def test_outcome_and_targets_match_pnl():
    rows = build_dataset(ENTRIES)
    assert rows[0]["outcome"] == "Win"
    assert rows[0]["y_win"] == 1
    assert rows[1]["outcome"] == "Loss"
    assert rows[1]["y_win"] == 0


def test_validate_row_flags_missing_required_fields():
    result = validate_row({"id": "1"})
    assert result["valid"] is False
    assert any("Missing" in e for e in result["errors"])


def test_validate_dataset_quality_score():
    rows = build_dataset(ENTRIES)
    report = validate_dataset(rows)
    assert report["qualityScore"] == 100
    assert report["validCount"] == 2


def test_csv_header_matches_column_order():
    rows = build_dataset(ENTRIES)
    csv_text = to_csv(rows)
    header = csv_text.splitlines()[0].split(",")
    assert header == ML_COLUMN_ORDER


def test_csv_row_count_matches_input():
    rows = build_dataset(ENTRIES)
    csv_text = to_csv(rows)
    assert len(csv_text.splitlines()) == len(rows) + 1  # header + rows
