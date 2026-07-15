"""account_margins table (Sprint 18 — margin/floating-loss buffer)

Stores the latest balance/equity/margin reading pushed from the MT5
EA, one row per user (account-level, not per symbol), so the website
can show how close the account is to a margin call / stop-out without
the user needing a fixed stop loss.

Revision ID: 0005_account_margins
Revises: 0004_ml_model_blob
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_account_margins"
down_revision: Union[str, None] = "0004_ml_model_blob"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_margins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("equity", sa.Float(), nullable=False),
        sa.Column("margin", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", name="uq_account_margins_user_id"),
    )


def downgrade() -> None:
    op.drop_table("account_margins")
