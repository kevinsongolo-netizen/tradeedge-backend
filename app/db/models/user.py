"""User model.

Sprint 6 ships with no auth wall (see Section 12 of the architecture
spec): a single row ``users(id=1, email='local@tradeedge.ai')`` is
seeded by the initial migration and used as the implicit "current
user" everywhere. The column set is already shaped for Sprint 8's JWT
auth so turning it on later is additive, not a schema rewrite.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.ai_analysis import AIAnalysis
    from app.db.models.live_snapshot import LiveSnapshot
    from app.db.models.ml_export import MLExport, MLModel
    from app.db.models.trade import Trade
    from app.db.models.weights import ScoringWeights


class User(Base):
    """A TradeEdge user. Single seeded row (id=1) until Sprint 8 auth."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    trades: Mapped[list["Trade"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    scoring_weights: Mapped["ScoringWeights | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    ml_exports: Mapped[list["MLExport"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    ml_models: Mapped[list["MLModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    live_snapshots: Mapped[list["LiveSnapshot"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"User(id={self.id!r}, email={self.email!r})"
