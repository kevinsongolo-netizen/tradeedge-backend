"""LiveSnapshot model (Sprint 14 — Live MT5 Feed; simplified Sprint 20).

Stores the latest live price pushed from an external source (e.g. an
MT5 Expert Advisor via WebRequest), keyed by (user_id, symbol,
timeframe), so the repurposed Scanner can compare live price against
the trader's own logged open trades' SL/TP without a rule engine in
the loop. One row per (user, symbol, timeframe) -- each new ingest
overwrites the previous snapshot (a "latest live view", not a data
warehouse; use the trade journal for historical analysis).

``analysis``/``validation``/``coach``/``multi_timeframe`` are the
retired rule-engine result columns (Sprint 10-18) -- kept, nullable,
purely so any row ingested by an old EA build during rollout doesn't
error on read; nothing new is ever written to them.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, UniqueConstraint
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

    # Sprint 20 -- the live price a Scanner alert compares against a
    # trade's SL/TP. bid/ask are optional (an EA may only send a mid/
    # close price); price is whichever the EA considers "current".
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Retired rule-engine columns (Sprint 10-18) -- see module docstring.
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    coach: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
