"""Trade fingerprint fields (Sprint 20 Phase 4)

The trader asked for every screenshot to become a "complete trade
fingerprint" -- not just the handful of fields the similarity/lesson
engines read, but everything the vision model could detect, plus real
open/close timestamps so "time in trade" can eventually be computed.

* ``timeframe`` / ``order_type`` -- read by the vision provider today
  (SetupExtraction.timeframe / .order_type) but never persisted to the
  trade itself; only ever shown live in the Chart Analysis Engine
  extraction display.
* ``entered_at`` / ``closed_at`` -- real timestamps (not just the
  existing ``date`` column, which has no time-of-day). Nullable and
  backfilled with nothing for existing rows -- there is no honest way
  to reconstruct a real timestamp for a trade that was never recorded
  with one, so old rows simply won't have a "time in trade" figure
  until re-logged. Populated going forward: entered_at when a trade is
  first saved, closed_at the moment an exit price is first set (either
  from the journal UI or the MT5 auto-journal EA, which is being
  updated alongside this to send a real datetime instead of a plain
  YYYY-MM-DD).
* ``vision_fingerprint`` -- the complete raw vision-provider read (see
  app/chart/vision_provider.py's VISION_ANALYSIS_SCHEMA_HINT), stored
  verbatim as JSON. Every structured column above (h4_trend,
  h4_poi_type, premium_discount, m15_confirmations, ...) is a curated
  *subset* of this for the engines that need fast, typed access --
  this column is the trader's explicit ask to never silently discard
  "any other SMC information Claude can detect" just because today's
  schema doesn't have a dedicated column for it yet.

Revision ID: 0007_trade_fingerprint
Revises: 0006_live_snapshots_price_only
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_trade_fingerprint"
down_revision: Union[str, None] = "0006_live_snapshots_price_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.add_column(sa.Column("timeframe", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("order_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("entered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("vision_fingerprint", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch_op:
        batch_op.drop_column("vision_fingerprint")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("entered_at")
        batch_op.drop_column("order_type")
        batch_op.drop_column("timeframe")
