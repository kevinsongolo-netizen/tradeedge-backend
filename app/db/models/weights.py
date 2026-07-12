"""ScoringWeights model — per-user override of engine default weights.

If no row exists for a user, every engine falls back to its own
hardcoded defaults (``DEFAULT_RULE_SCORE_WEIGHTS`` etc. in
``app/engines/*.py``). One row per user (``user_id`` is unique).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class ScoringWeights(Base):
    """Per-user weight overrides for the rule/execution/similarity engines."""

    __tablename__ = "scoring_weights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    rule_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execution_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    similarity_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="scoring_weights")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"ScoringWeights(user_id={self.user_id!r})"
