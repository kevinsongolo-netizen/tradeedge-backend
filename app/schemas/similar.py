"""Similar-trade schemas — ``POST /api/v1/ai/similar`` (Sections 4.4, 7)."""
from __future__ import annotations

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.trade import TradeAnalyzeIn


class SimilarSearchRequest(CamelModel):
    candidate: TradeAnalyzeIn
    min_similarity: float = 50.0
    limit: int = 10
    algorithm: str = "weighted-v1"  # or "legacy"


class FeatureContribution(CamelModel):
    feature: str
    weight: float
    similarity: float
    contribution: float


class SimilarTradeMatch(CamelModel):
    id: str
    pair: str | None = None
    direction: str | None = None
    date: str | None = None
    similarity: float
    pnl: float | None = None
    rr: float | None = None
    rule_score: int | None = None
    execution_score: int | None = None
    outcome: str
    contributions: list[FeatureContribution] = Field(default_factory=list)


class SimilarSearchResult(CamelModel):
    similar: list[SimilarTradeMatch]
    wins: int
    losses: int
    breakeven: int
    win_rate: float | None
    average_rr: float | None = Field(default=None, alias="averageRR")
    average_profit: float | None
    average_rule_score: float | None
    average_execution_score: float | None
    confidence: float
    algorithm: str
    weights_snapshot: dict[str, float]
