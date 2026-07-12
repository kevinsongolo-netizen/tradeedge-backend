"""ML dataset schemas — ``/api/v1/ml/*`` (Sections 4.7 and 8)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelModel


class MlRow(BaseModel):
    """Deliberately **not** a ``CamelModel`` — Section 8's column names
    are snake_case (the ML/Python contract), unlike the camelCase used
    by the rest of the JSON API (Section 6, for the JS frontend). Both
    the JSON and CSV export use these exact keys."""

    model_config = ConfigDict(from_attributes=True)

    # Identity
    id: str
    user_id: int
    date: str
    dataset_version: str
    exported_at: str | None = None

    # Instrument & session
    pair: str
    direction: str
    asset: str
    session: str
    day_of_week: int
    hour_of_day: int | None = None
    news: str | None = None

    # Setup / strategy (SMC features)
    h4_trend: str | None = None
    h4_poi_type: str | None = None
    premium_discount: str | None = None
    m15_confirmations: str = ""
    has_bos: int = 0
    has_choch: int = 0
    has_liquidity_sweep: int = 0
    confidence: float | None = None

    # Risk / execution
    entry: float
    stop_loss: float | None = None
    take_profit: float | None = None
    lots: float | None = None
    planned_rr: float | None = None
    exit: float | None = None
    pnl: float
    rr: float
    exit_reason: str | None = None
    emotion: str | None = None
    followed_plan: str | None = None
    rules_followed: str | None = None

    # AI scores
    rule_score: int
    execution_score: int
    overall_score: int
    rule_recommendation: str
    execution_grade: str

    # Statistical context (leakage-controlled — Section 8.6)
    hist_trades_total: int
    hist_trades_pair: int
    hist_trades_session: int
    hist_win_rate_all: float | None = None
    hist_win_rate_pair: float | None = None
    hist_win_rate_session: float | None = None
    hist_expectancy_all: float | None = None
    hist_avg_rr_all: float | None = None
    hist_streak_dir: int | None = None
    hist_rule_score_ema10: float | None = None
    hist_execution_score_ema10: float | None = None

    # Targets
    outcome: str
    y_win: int
    y_pnl: float
    y_rr_realized: float
    y_quality_bucket: str

    # Validation
    validation_status: str
    validation_errors: str = ""
    validation_warnings: str = ""


class MlValidationRowReport(CamelModel):
    index: int
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MlValidationReport(CamelModel):
    total: int
    valid_count: int
    invalid_count: int
    quality_score: int
    rows: list[MlValidationRowReport]


class MlExportRequest(CamelModel):
    format: str = "both"  # "json" | "csv" | "both"


class MlExportFile(CamelModel):
    format: str
    path: str
    checksum: str


class MlExportResult(CamelModel):
    row_count: int
    rejected_count: int
    quality_score: int
    dataset_version: str
    files: list[MlExportFile]
