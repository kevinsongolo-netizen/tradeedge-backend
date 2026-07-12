"""Sprint 8 schemas — Pre-Trade Analysis (Vision Phases 5 & 7).

``POST /api/v1/assistant/pretrade-analysis`` reuses
``app.schemas.ml_training.PredictionRequest`` as its request body
(identical fields — a candidate trade's setup) rather than declaring a
near-duplicate schema.
"""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class PreTradeAnalysisResult(CamelModel):
    trade_quality_score: float | None
    win_probability: float | None
    ai_confidence: str  # "High" | "Medium" | "Low"
    risk_level: str  # "Low" | "Medium" | "High"
    expected_rr: float | None
    historical_win_rate: float | None
    similar_trades_count: int
    recommendation: str  # "Strong Buy" | "Buy" | "Wait" | "Avoid"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    historical_reasons: list[str] = Field(default_factory=list)
    ml_available: bool
    model_version: str | None = None
    algorithm: str | None = None
