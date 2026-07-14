"""ml_models.model_blob column (Sprint 17 — persist trained model bytes in DB)

Render's free tier has no persistent disk, so the joblib file written
to ``file_path`` by ``POST /ml/train`` is wiped the next time the
service spins down and restarts. This adds a nullable binary column so
the trained model itself survives in Postgres (which does persist
across restarts) as a fallback the prediction service can reload from.

Revision ID: 0004_ml_model_blob
Revises: 0003_live_snapshots
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_ml_model_blob"
down_revision: Union[str, None] = "0003_live_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ml_models",
        sa.Column("model_blob", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ml_models", "model_blob")
