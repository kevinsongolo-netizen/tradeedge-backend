"""Drop redundant live_snapshots index (Sprint 22 stability audit)

``live_snapshots`` has carried two separate indexes over the exact same
three columns since Sprint 14 (migration 0003):

* ``uq_live_snapshots_user_symbol_timeframe`` -- the real constraint
  (one row per user/symbol/timeframe), which Postgres/SQLite already
  back with an implicit unique index for lookups.
* ``ix_live_snapshots_user_symbol_timeframe`` -- a second, plain index
  over identical columns, created right after it in the same
  migration. Fully redundant: every query this index could serve is
  already served by the unique constraint's own index.

Found during the Sprint 22 stability audit via an autogenerate schema
diff against the current models (``LiveSnapshot`` only declares the
``UniqueConstraint``, not this index) -- the model and the migrated
schema had quietly drifted apart since Sprint 14. Functionally harmless
(queries still worked), but it doubles the index-maintenance cost on
every single write to this table, which is the highest-write-frequency
table in the app (every MT5 EA price push). Dropping it is pure
cleanup: no query relies on it specifically, and the unique constraint
keeps providing the same lookup performance afterward.

Revision ID: 0008_drop_redundant_index
Revises: 0007_trade_fingerprint

NOTE: revision id kept short deliberately -- alembic_version.version_num
is VARCHAR(32) on Postgres (unlike SQLite, which doesn't enforce column
length at all, which is exactly why the original 39-character id
"0008_drop_redundant_live_snapshot_index" passed local testing against
a fresh SQLite db but failed on deploy against the real Postgres
database with StringDataRightTruncationError. Every other revision id
in this project is comfortably under 32 chars -- this one just wasn't.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_drop_redundant_index"
down_revision: Union[str, None] = "0007_trade_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_live_snapshots_user_symbol_timeframe", table_name="live_snapshots")


def downgrade() -> None:
    op.create_index(
        "ix_live_snapshots_user_symbol_timeframe",
        "live_snapshots",
        ["user_id", "symbol", "timeframe"],
    )
