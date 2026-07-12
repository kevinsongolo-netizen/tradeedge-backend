"""AIAnalysis model — versioned scoring history.

One row per ``analyze`` call. Rows are never mutated or deleted (except
via cascade when the parent trade is deleted); ``trades.rule_score`` /
``execution_score`` / ``overall_score`` / ``rule_recommendation`` are a
denormalized *cache* of the most recent row here, kept in sync by
``app/services/ai_service.py``.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.trade import Trade
    from app.db.models.user import User


class AIAnalysis(Base):
    """A single, immutable rule+execution scoring run for one trade."""

    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("ix_ai_analyses_trade_created", "trade_id", "created_at"),
        Index("ix_ai_analyses_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(
        ForeignKey("trades.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    rule_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)

    rule_breakdown: Mapped[list | None] = mapped_column(JSON, nullable=True)
    execution_breakdown: Mapped[list | None] = mapped_column(JSON, nullable=True)
    passed_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missing_confirmations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mistakes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggestions: Mapped[list | None] = mapped_column(JSON, nullable=True)

    rule_engine_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    execution_engine_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weights_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    trade: Mapped["Trade"] = relationship(back_populates="analyses")
    user: Mapped["User"] = relationship(back_populates="analyses")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"AIAnalysis(id={self.id!r}, trade_id={self.trade_id!r}, overall={self.overall_score!r})"
