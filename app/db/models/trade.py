"""Trade model.

Mirrors the frontend's journal entry object 1:1 (see Section 3.2 of the
Sprint 6 architecture spec) so persisting a ``TradeIn`` payload is a
straight field-for-field mapping. Every column except identity fields
is nullable because trades are staged as they're entered (e.g. an open
trade has no ``exit``/``pnl`` yet).

Cached score columns (``rule_score``, ``execution_score``,
``overall_score``, ``rule_recommendation``) are denormalized copies of
the latest ``AIAnalysis`` row for fast list views; the versioned
source of truth lives in ``ai_analyses``.
"""
from __future__ import annotations

from datetime import date as date_, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.ai_analysis import AIAnalysis
    from app.db.models.user import User


class Trade(Base):
    """A single journaled trade, owned by a user."""

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("direction IN ('buy', 'sell')", name="direction_valid"),
        Index("ix_trades_user_date", "user_id", "date"),
        Index("ix_trades_user_pair", "user_id", "pair"),
        Index("ix_trades_user_session", "user_id", "session"),
    )

    # Client-supplied UUID (matches the frontend's own trade ids) so
    # upserts from the browser/migration script are idempotent.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    date: Mapped[date_ | None] = mapped_column(Date, nullable=True)
    pair: Mapped[str | None] = mapped_column(String(32), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Sprint 20 Phase 4 -- read by the vision provider today but not
    # persisted until now; only ever shown live in Chart Analysis
    # Engine's extraction display.
    timeframe: Mapped[str | None] = mapped_column(String(16), nullable=True)
    order_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column("exit", Float, nullable=True)
    sl: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp: Mapped[float | None] = mapped_column(Float, nullable=True)
    lots: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    rr: Mapped[float | None] = mapped_column(Float, nullable=True)

    h4_trend: Mapped[str | None] = mapped_column(String(32), nullable=True)
    h4_poi_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    premium_discount: Mapped[str | None] = mapped_column(String(32), nullable=True)
    m15_confirmations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    session: Mapped[str | None] = mapped_column(String(32), nullable=True)
    news: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    followed_plan: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rules_followed: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    worked: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed: Mapped[str | None] = mapped_column(Text, nullable=True)
    worked_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    failed_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    screenshots: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Sprint 20 Phase 4 -- real open/close timestamps (the existing
    # ``date`` column has no time-of-day) so "time in trade" can be
    # computed, plus the complete raw vision read so nothing the vision
    # model detects is silently discarded just because it doesn't have
    # its own dedicated column yet. See migration 0007's docstring.
    entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vision_fingerprint: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Cached from the latest ai_analyses row — see app/services/ai_service.py.
    rule_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rule_recommendation: Mapped[str | None] = mapped_column(String(16), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="trades")
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="trade",
        cascade="all, delete-orphan",
        order_by="AIAnalysis.created_at.desc()",
    )

    @property
    def time_in_trade_minutes(self) -> float | None:
        """Minutes between entered_at/closed_at -- None whenever either
        is missing (a trade logged before Sprint 20 Phase 4, or one
        that's still open). Never estimated or backfilled from ``date``
        alone -- a date has no time-of-day, so there's nothing honest
        to compute it from for older rows.

        Strips tzinfo before subtracting: SQLite has no real timezone
        type, so a value just round-tripped through the DB comes back
        naive even though it was stamped timezone-aware (UTC) in
        Python moments earlier in the same request -- without this,
        computing this property in the middle of the same
        create/update call that just set one of the two fields raises
        "can't subtract offset-naive and offset-aware datetimes".
        Every timestamp this app ever writes is UTC, so a naive
        comparison is safe."""
        if self.entered_at is None or self.closed_at is None:
            return None
        entered = self.entered_at.replace(tzinfo=None)
        closed = self.closed_at.replace(tzinfo=None)
        return (closed - entered).total_seconds() / 60.0

    def to_engine_dict(self) -> dict[str, Any]:
        """Flattens this row into the plain camelCase dict shape every
        pure engine function (``app/engines/*.py``) expects — the exact
        JSON shape the frontend used to keep in ``localStorage``.
        """
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "pair": self.pair,
            "direction": self.direction,
            "asset": self.asset,
            "timeframe": self.timeframe,
            "orderType": self.order_type,
            "entry": self.entry,
            "exit": self.exit_price,
            "sl": self.sl,
            "tp": self.tp,
            "lots": self.lots,
            "pnl": self.pnl,
            "rr": self.rr,
            "h4Trend": self.h4_trend,
            "h4PoiType": self.h4_poi_type,
            "premiumDiscount": self.premium_discount,
            "m15Confirmations": self.m15_confirmations or [],
            "session": self.session,
            "news": self.news,
            "confidence": self.confidence,
            "followedPlan": self.followed_plan,
            "rulesFollowed": self.rules_followed,
            "exitReason": self.exit_reason,
            "emotion": self.emotion,
            "notes": self.notes,
            "worked": self.worked,
            "failed": self.failed,
            "workedTags": self.worked_tags or [],
            "failedTags": self.failed_tags or [],
            "screenshots": self.screenshots or [],
            "enteredAt": self.entered_at.isoformat() if self.entered_at else None,
            "closedAt": self.closed_at.isoformat() if self.closed_at else None,
            "timeInTradeMinutes": self.time_in_trade_minutes,
            "visionFingerprint": self.vision_fingerprint,
            "ruleScore": self.rule_score,
            "executionScore": self.execution_score,
            "overallScore": self.overall_score,
            "ruleRecommendation": self.rule_recommendation,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Trade(id={self.id!r}, pair={self.pair!r}, date={self.date!r})"
