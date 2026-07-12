"""Sprint 7 schemas — dataset validation report, training, model
registry, and prediction (``/api/v1/ml/train`` et al.).

New file; does not modify Sprint 6's ``app/schemas/ml.py`` (the
existing ``/ml/dataset``, ``/ml/validate``, ``/ml/exports`` contract is
untouched).
"""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class DuplicateTrades(CamelModel):
    count: int
    ids: list[str] = Field(default_factory=list)


class ClassDistribution(CamelModel):
    wins: int
    losses: int
    breakeven: int
    win_rate: float
    is_balanced: bool


class DatasetValidationReport(CamelModel):
    """Phase 1 deliverable — dataset-level validation report."""

    total_trades: int
    valid_trades: int
    invalid_trades: int
    missing_fields: dict[str, int]
    duplicate_trades: DuplicateTrades
    class_distribution: ClassDistribution
    min_training_rows: int
    ready_for_training: bool
    reason: str | None = None


class ModelMetrics(CamelModel):
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float | None = Field(default=None, alias="rocAuc")


class SplitSizes(CamelModel):
    train: int
    val: int
    test: int


class TrainingRequest(CamelModel):
    """Empty for now — trains on the current user's full history.
    Kept as a body (rather than no body at all) so future options
    (e.g. an explicit algorithm override, a date-range cutoff) can be
    added without breaking the endpoint's shape."""

    force: bool = False


class TrainingResult(CamelModel):
    version: str
    algorithm: str
    rows_used: int
    split_sizes: SplitSizes
    candidates: dict[str, ModelMetrics]
    val_metrics: ModelMetrics = Field(alias="valMetrics")
    test_metrics: ModelMetrics = Field(alias="testMetrics")
    train_metrics: ModelMetrics = Field(alias="trainMetrics")
    overfit_warning: bool
    trained_at: str
    model_path: str


class ModelInfo(CamelModel):
    id: int
    version: str
    algorithm: str | None
    trained_at: str | None
    training_rows: int | None
    metrics: dict | None
    is_active: bool
    file_path: str | None


class PredictionRequest(CamelModel):
    """A candidate trade — logged or not-yet-logged — to score. Only
    the setup fields go here; historical/rolling features are computed
    server-side from the user's real trade history (Section: "learn
    from the user's own trading history"), never supplied by the
    caller."""

    pair: str
    asset: str | None = None
    direction: str | None = None
    session: str | None = None
    h4_trend: str | None = None
    h4_poi_type: str | None = None
    has_bos: bool = False
    has_choch: bool = False
    has_liquidity_sweep: bool = False
    planned_rr: float | None = Field(default=None, alias="plannedRR")
    rule_score: float | None = None
    execution_score: float | None = None
    confidence: float | None = None
    emotion: str | None = None


class PredictionResult(CamelModel):
    win_probability: float
    predicted_quality_score: float
    predicted_quality_bucket: str
    model_version: str
    algorithm: str
