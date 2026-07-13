"""live_snapshots table (Sprint 14 — Live MT5 Feed)

Stores the latest Chart Analysis Engine result pushed from an external
live source (e.g. an MT5 Expert Advisor via WebRequest), keyed by
(user_id, symbol, timeframe), so the website's Chart Analysis Engine
can display fresh data without the user re-pasting candles by hand.

Revision ID: 0003_live_snapshots
Revises: 0002_ml_models_indexes
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_live_snapshots"
down_revision: Union[str, None] = "0002_ml_models_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "live_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("analysis", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("coach", sa.JSON(), nullable=False),
        sa.Column("multi_timeframe", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "symbol", "timeframe", name="uq_live_snapshots_user_symbol_timeframe"
        ),
    )
    op.create_index(
        "ix_live_snapshots_user_symbol_timeframe",
        "live_snapshots",
        ["user_id", "symbol", "timeframe"],
    )


def downgrade() -> None:
    op.drop_index("ix_live_snapshots_user_symbol_timeframe", table_name="live_snapshots")
    op.drop_table("live_snapshots")
