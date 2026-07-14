"""ML export audit log + Sprint-7 model registry placeholder.

``MLExport`` records every dataset export so a Sprint 7 training run can
be reproduced exactly. ``MLModel`` is created empty in Sprint 6 — no
rows are written until Sprint 7's ``scripts/train_v1.py`` exists; the
table just needs to be present so the schema doesn't change later.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User


class MLExport(Base):
    """Audit row for one ML dataset export (JSON and/or CSV)."""

    __tablename__ = "ml_exports"
    __table_args__ = (
        # Added post-Sprint-7 audit (see alembic/versions/0002_ml_models_indexes.py):
        # every export-history query filters by user_id; there was no
        # index for it.
        Index("ix_ml_exports_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_version: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="ml_exports")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"MLExport(id={self.id!r}, format={self.format!r}, rows={self.row_count!r})"


class MLModel(Base):
    """Sprint 7 placeholder — trained model registry. Empty in Sprint 6."""

    __tablename__ = "ml_models"
    __table_args__ = (
        # Added post-Sprint-7 audit (see alembic/versions/0002_ml_models_indexes.py).
        # Declared here too (not just in the migration) so
        # Base.metadata.create_all — what the test suite uses — builds
        # the exact same schema alembic upgrade head does; otherwise
        # these constraints would silently never be exercised by any
        # test.
        Index("ix_ml_models_user_id", "user_id"),
        # A trade can't end up with two rows claiming the same version.
        Index("uq_ml_models_user_version", "user_id", "version", unique=True),
        # At most one active model per user — a partial unique index so
        # a race between two concurrent POST /ml/train calls fails
        # loudly (IntegrityError, translated to a 409 — see
        # MLTrainingService.train()) instead of silently leaving two
        # "active" models.
        Index(
            "uq_ml_models_active_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Sprint 17 fix -- Render's free tier has no persistent disk, so a
    # trained joblib artifact written to `file_path` vanishes the next
    # time the service spins down and restarts, even though this DB row
    # (which lives in Postgres, unaffected by container restarts) still
    # says a model is active. Storing the serialized model bytes here
    # too means MLPredictionService can always reload it from the DB as
    # a fallback instead of crashing with FileNotFoundError.
    model_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship(back_populates="ml_models")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"MLModel(id={self.id!r}, version={self.version!r}, active={self.is_active!r})"
