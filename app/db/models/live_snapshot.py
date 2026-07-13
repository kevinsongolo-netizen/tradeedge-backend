"""LiveSnapshot model (Sprint 14 — Live MT5 Feed).

Stores the most recent Chart Analysis Engine result ingested from an
external live source (e.g. an MT5 Expert Advisor via WebRequest), keyed
by (user_id, symbol, timeframe), so the website can display fresh data
without the user re-pasting candles by hand. One row per (user,
symbol, timeframe) — each new ingest overwrites the previous snapshot
for that key rather than accumulating history (this is a "latest live
view", not a data warehouse; use the Backtesting engine or the trade
journal for historical analysis).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class LiveSnapshot(Base):
    __tablename__ = "live_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "symbol", "timeframe", name="uq_live_snapshots_user_symbol_timeframe"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)

    analysis: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, nullable=False)
    coach: Mapped[dict] = mapped_column(JSON, nullable=False)
    multi_timeframe: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="live_snapshots")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"LiveSnapshot(user_id={self.user_id!r}, symbol={self.symbol!r}, timeframe={self.timeframe!r})"
