"""Phase 1 — dataset validation report tests."""
from app.ml.dataset_validation import MIN_TRAINING_ROWS, generate_validation_report


def _row(id_, *, valid=True, outcome="Win", missing=None):
    errors = [] if valid else [f"Missing {f}" for f in (missing or ["pnl"])]
    return {
        "id": id_,
        "validation_status": "valid" if valid else "rejected",
        "validation_errors": "|".join(errors),
        "outcome": outcome,
    }


def test_empty_dataset_reports_zero_and_not_ready():
    report = generate_validation_report([])
    assert report["totalTrades"] == 0
    assert report["validTrades"] == 0
    assert report["readyForTraining"] is False
    assert report["reason"] is not None


def test_counts_valid_and_invalid_rows():
    rows = [_row("a", valid=True), _row("b", valid=False, missing=["pnl", "rr"]), _row("c", valid=True)]
    report = generate_validation_report(rows)
    assert report["totalTrades"] == 3
    assert report["validTrades"] == 2
    assert report["invalidTrades"] == 1


def test_missing_field_counts_are_tallied_across_rows():
    rows = [
        _row("a", valid=False, missing=["pnl"]),
        _row("b", valid=False, missing=["pnl", "rr"]),
        _row("c", valid=True),
    ]
    report = generate_validation_report(rows)
    assert report["missingFields"]["pnl"] == 2
    assert report["missingFields"]["rr"] == 1


def test_duplicate_ids_are_detected():
    rows = [_row("dup"), _row("dup"), _row("unique")]
    report = generate_validation_report(rows)
    assert report["duplicateTrades"]["count"] == 1
    assert report["duplicateTrades"]["ids"] == ["dup"]


def test_class_distribution_counts_outcomes():
    rows = [
        _row("a", outcome="Win"),
        _row("b", outcome="Win"),
        _row("c", outcome="Loss"),
        _row("d", outcome="Breakeven"),
    ]
    report = generate_validation_report(rows)
    dist = report["classDistribution"]
    assert dist["wins"] == 2
    assert dist["losses"] == 1
    assert dist["breakeven"] == 1
    assert dist["winRate"] == 50.0


def test_ready_for_training_requires_minimum_valid_rows():
    just_under = [_row(str(i)) for i in range(MIN_TRAINING_ROWS - 1)]
    just_enough = [_row(str(i)) for i in range(MIN_TRAINING_ROWS)]
    assert generate_validation_report(just_under)["readyForTraining"] is False
    assert generate_validation_report(just_enough)["readyForTraining"] is True
