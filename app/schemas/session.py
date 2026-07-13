"""Trading session schemas (Sprint 12 — Market Context Filters)."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class SessionDetectRequest(CamelModel):
    timestamp: datetime | None = Field(
        default=None,
        description="UTC timestamp to check. Omit to use the current time.",
    )


class SessionDetectResult(CamelModel):
    utc_time: str
    active_sessions: list[str] = Field(default_factory=list)
    primary_session: str
    is_overlap: bool
