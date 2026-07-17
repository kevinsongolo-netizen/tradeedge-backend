"""Simplify live_snapshots to price-only (Sprint 20 — screenshot-first workflow)

The old rule-based strategy engine that produced analysis/validation/
coach on every MT5 push is retired (see app/_legacy/) -- the Live Feed's
job going forward is just to track the latest live price per (user,
symbol, timeframe) so the repurposed Scanner can compare it against the
trader's own logged open trades (Trade rows with no exit price yet).

analysis/validation/coach/multi_timeframe are made nullable rather than
dropped outright -- any already-ingested rows on a live Render database
stay readable (old EA builds may still be pushing the old shape for a
short window during rollout) instead of erroring, but nothing new is
ever written to them.

Revision ID: 0006_live_snapshots_price_only
Revises: 0005_account_margins
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_live_snapshots_price_only"
down_revision: Union[str, None] = "0005_account_margins"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("live_snapshots") as batch_op:
        batch_op.alter_column("analysis", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("validation", existing_type=sa.JSON(), nullable=True)
        batch_op.alter_column("coach", existing_type=sa.JSON(), nullable=True)
        batch_op.add_column(sa.Column("price", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("bid", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ask", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("live_snapshots") as batch_op:
        batch_op.drop_column("ask")
        batch_op.drop_column("bid")
        batch_op.drop_column("price")
        batch_op.alter_column("analysis", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("validation", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("coach", existing_type=sa.JSON(), nullable=False)
