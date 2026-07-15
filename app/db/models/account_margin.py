"""AccountMargin model (Sprint 18 — margin/floating-loss buffer).

Stores the most recently ingested account-level balance/equity/margin
reading, one row per user (there's no per-symbol key here — margin is
an account-wide number, unlike ``LiveSnapshot`` which is keyed per
symbol/timeframe). Each new ingest overwrites the previous row for
that user, same "latest live view" pattern as live_snapshots.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class AccountMargin(Base):
    __tablename__ = "account_margins"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_account_margins_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    balance: Mapped[float] = mapped_column(Float, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    margin: Mapped[float] = mapped_column(Float, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="account_margin", uselist=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"AccountMargin(user_id={self.user_id!r}, equity={self.equity!r}, margin={self.margin!r})"
