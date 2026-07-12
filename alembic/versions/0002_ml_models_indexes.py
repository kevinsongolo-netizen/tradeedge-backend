"""ml_models/ml_exports indexes + data-integrity constraints

Found during the post-Sprint-7 production readiness audit:

* ``ml_models`` and ``ml_exports`` had no index on ``user_id`` at all
  (every query — including the hot ``get_active()`` lookup used by
  every ``/ml/predict`` call — was a full table scan). Harmless at
  today's scale (a handful of rows per user) but wrong to ship as-is.
* Nothing in the schema stopped two concurrent ``POST /ml/train``
  requests for the same user from both computing the same "next
  version" string and inserting two rows with the same
  ``(user_id, version)``, or from leaving two rows both marked
  ``is_active=True``. The application code (``MLModelRepository.
  insert_and_activate``) already deactivates every other row in the
  same transaction, but nothing enforced that invariant at the
  database level, so a race condition could silently corrupt the
  "exactly one active model per user" guarantee the rest of the app
  depends on.

This migration adds the missing indexes and two constraints:

* ``uq_ml_models_user_version`` — a trade can't end up with two model
  rows claiming the same version string.
* ``uq_ml_models_active_per_user`` — a partial unique index (only over
  rows where ``is_active`` is true) so the database itself refuses a
  second active row for the same user, in either SQLite or Postgres.

Revision ID: 0002_ml_models_indexes
Revises: 0001_initial
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_ml_models_indexes"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_ml_models_user_id", "ml_models", ["user_id"], unique=False)
    op.create_index("ix_ml_exports_user_id", "ml_exports", ["user_id"], unique=False)

    # A unique constraint would need SQLite's "batch mode" table-rebuild
    # (ALTER-ADD-CONSTRAINT isn't supported on SQLite); a plain unique
    # index enforces the exact same guarantee on every dialect without it.
    op.create_index(
        "uq_ml_models_user_version", "ml_models", ["user_id", "version"], unique=True
    )

    # Partial unique index: at most one active model per user. Works on
    # both SQLite (>=3.8) and PostgreSQL; Index() picks the right DDL
    # for whichever dialect Alembic is running against.
    op.create_index(
        "uq_ml_models_active_per_user",
        "ml_models",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index("uq_ml_models_active_per_user", table_name="ml_models")
    op.drop_index("uq_ml_models_user_version", table_name="ml_models")
    op.drop_index("ix_ml_exports_user_id", table_name="ml_exports")
    op.drop_index("ix_ml_models_user_id", table_name="ml_models")
