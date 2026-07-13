"""News/economic calendar filter schemas (Sprint 12)."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class NewsCheckRequest(CamelModel):
    planned_time: datetime = Field(description="When the trade is planned (any ISO-8601 timestamp).")
    buffer_minutes: int = 60
    currencies: list[str] | None = Field(
        default=None,
        description="Restrict to these currencies/countries (e.g. ['USD','EUR']). Omit to check all.",
    )
    min_impact: str = "high"


class NewsEventOut(CamelModel):
    time: str | None = None
    currency: str
    event: str
    impact: str
    actual: float | None = None
    estimate: float | None = None
    previous: float | None = None
    is_placeholder: bool = False
    minutes_away: float | None = None


class NewsCheckResult(CamelModel):
    has_high_impact_nearby: bool
    matching_events: list[NewsEventOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    is_placeholder: bool = False
    provider: str
