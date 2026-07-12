"""AI analysis schemas — ``/api/v1/ai/*`` (Section 4.3)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel


class RuleBreakdownItem(CamelModel):
    key: str
    ok: bool
    partial: bool
    points: int
    max_points: int
    text: str


class ExecutionBreakdownItem(CamelModel):
    key: str
    ok: bool
    points: int
    max_points: int
    text: str
    suggestion: str = ""


class WeightsPayload(CamelModel):
    """Body of ``PUT /ai/weights`` — any missing key falls back to the
    engine's own default for that key."""

    rule: dict[str, float] | None = None
    execution: dict[str, float] | None = None
    similarity: dict[str, float] | None = None


class AnalyzeResult(CamelModel):
    """Response shape for ``POST /ai/analyze`` — a superset of what the
    JS ``runAiAnalysisPipeline`` used to return for rule + execution
    (Section 4.3). Execution fields are ``None`` for an open trade."""

    rule_score: int | None = None
    execution_score: int | None = None
    overall_score: int | None = None
    recommendation: str | None = None
    grade: str | None = None
    rule_breakdown: list[RuleBreakdownItem] = Field(default_factory=list)
    execution_breakdown: list[ExecutionBreakdownItem] = Field(default_factory=list)
    passed_reasons: list[str] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    mistakes: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    rule_engine_version: str
    execution_engine_version: str
    weights_snapshot: dict


class RuleOnlyResult(CamelModel):
    rule_score: int
    recommendation: str
    rule_breakdown: list[RuleBreakdownItem]
    passed_reasons: list[str]
    missing_confirmations: list[str]
    rule_engine_version: str
    weights: dict[str, float]


class ExecutionOnlyResult(CamelModel):
    execution_score: int
    grade: str
    execution_breakdown: list[ExecutionBreakdownItem]
    strengths: list[str]
    mistakes: list[str]
    suggestions: list[str]
    execution_engine_version: str


class AnalysisHistoryItem(CamelModel):
    id: int
    trade_id: str
    rule_score: int | None
    execution_score: int | None
    overall_score: int | None
    recommendation: str | None
    grade: str | None
    rule_engine_version: str | None
    execution_engine_version: str | None
    created_at: str


class AnalysisHistoryResponse(CamelModel):
    items: list[AnalysisHistoryItem]
