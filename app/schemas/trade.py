"""Trade schemas — the public contract for ``/api/v1/trades`` and the
input shape shared by the AI endpoints (Section 4.2 of the spec).

Every field except ``id`` is optional because journal entries are
staged incrementally in the frontend (an open trade has no
``exit``/``pnl`` yet) — validation of "is this trade complete enough
to score/export" is an engine/ML concern (see ``engines/ml_dataset.py``
and ``validate_row``), not a schema-level one.
"""
from __future__ import annotations

from datetime import date as date_, datetime
from typing import Literal

from pydantic import Field

from app.schemas.chart import SetupInsight
from app.schemas.common import CamelModel


class TradeScreenshot(CamelModel):
    """One screenshot attached to a trade (Sprint 20 Phase 3). ``kind``
    distinguishes the pre-entry chart read from an optional post-exit
    "how it actually played out" shot -- ``url`` is a permanent,
    publicly-fetchable URL (Cloudinary today, see
    ``app/media/image_storage.py``); a trade logged before screenshot
    storage was configured (or logged with no image at all) simply has
    an empty ``screenshots`` list, never a fake/broken URL."""

    url: str
    kind: Literal["entry", "exit"] = "entry"
    uploaded_at: datetime | None = None


class TradeBase(CamelModel):
    """Every journal-entry field, all optional — matches the frontend's
    staged-entry model (Section 3.2: "every column is nullable except
    identity fields")."""

    date: date_ | None = None
    pair: str | None = None
    direction: str | None = None
    asset: str | None = None
    entry: float | None = None
    exit: float | None = Field(default=None, alias="exit")
    sl: float | None = None
    tp: float | None = None
    lots: float | None = None
    pnl: float | None = None
    rr: float | None = None
    h4_trend: str | None = None
    h4_poi_type: str | None = None
    premium_discount: str | None = None
    m15_confirmations: list[str] = Field(default_factory=list)
    session: str | None = None
    news: str | None = None
    confidence: float | None = None
    followed_plan: str | None = None
    rules_followed: str | None = None
    exit_reason: str | None = None
    emotion: str | None = None
    notes: str | None = None
    worked: str | None = None
    failed: str | None = None
    worked_tags: list[str] = Field(default_factory=list)
    failed_tags: list[str] = Field(default_factory=list)
    screenshots: list[TradeScreenshot] = Field(default_factory=list)

    def to_model_kwargs(self) -> dict:
        """Maps this schema's fields onto ``Trade`` ORM attribute names
        (only ``exit`` -> ``exit_price`` differs, to dodge shadowing the
        ``exit()`` builtin on the model). **DB writes only** — every
        ``app/engines/*.py`` pure function expects the camelCase shape
        ``Trade.to_engine_dict()`` produces, not this one; use
        ``to_candidate_dict()`` for those call sites instead (see its
        docstring for why this distinction matters)."""
        data = self.model_dump(by_alias=False, exclude_unset=True)
        if "exit" in data:
            data["exit_price"] = data.pop("exit")
        if "pair" in data and data["pair"]:
            data["pair"] = str(data["pair"]).upper()
        if "screenshots" in data:
            # JSON columns need plain, iso-string-safe values -- model_dump()
            # already recurses TradeScreenshot into plain dicts, but leaves
            # uploaded_at as a real datetime, which most JSON encoders choke
            # on when the ORM eventually serializes this column.
            for shot in data["screenshots"]:
                if isinstance(shot.get("uploaded_at"), (date_, datetime)):
                    shot["uploaded_at"] = shot["uploaded_at"].isoformat()
        return data

    def to_candidate_dict(self) -> dict:
        """Maps this schema onto the same camelCase shape
        ``Trade.to_engine_dict()`` produces for a *persisted* trade
        (``h4Trend``, ``h4PoiType``, ``m15Confirmations``,
        ``followedPlan``, ``exitReason``, ``workedTags``/``failedTags``,
        etc.) — the shape every pure engine function in
        ``app/engines/*.py`` actually reads fields from.

        Found during a Sprint 8 review: ``/ai/analyze``, ``/ai/rule``,
        and ``/ai/execution`` ("check this trade before saving") were
        passing ``to_model_kwargs()``'s *snake_case* output straight
        into ``compute_rule_score()``/``compute_execution_score()``,
        which read ``fields.get("h4Trend")`` etc. Since
        ``to_model_kwargs()`` produces ``h4_trend`` instead, every
        SMC-structure check (H4 trend, POI, premium/discount) and
        several execution checks (worked/failed tags, exit reason,
        followed-plan) silently never matched for these three preview
        endpoints — while the real persisted-save path
        (``TradeService._analyze_and_persist``, which correctly calls
        ``trade.to_engine_dict()`` on the saved ORM row) was unaffected.
        Net effect: the live "preview" score shown before saving a
        trade could differ from the score actually persisted a moment
        later. Use this method, not ``to_model_kwargs()``, whenever a
        not-yet-saved candidate is handed directly to an engine
        function."""
        data = self.model_dump(by_alias=True)
        date_value = data.get("date")
        if isinstance(date_value, (date_, datetime)):
            data["date"] = date_value.isoformat()
        return data


class TradeIn(TradeBase):
    """Request body for ``POST /trades`` — client supplies the id
    (matches the frontend's own UUIDs) so repeated saves upsert."""

    id: str


class TradeUpdate(TradeBase):
    """Request body for ``PATCH /trades/{id}`` — every field optional,
    only supplied keys are updated (``exclude_unset`` in the service)."""


class TradeAnalyzeIn(TradeBase):
    """Request body for ``POST /ai/analyze`` / ``/ai/rule`` /
    ``/ai/execution`` — id is optional since the trade may not exist
    yet (the "check this trade before saving" flow, Section 9.2)."""

    id: str | None = None


class TradeOut(TradeBase):
    """Response shape for a persisted trade — a superset of ``TradeIn``
    with the cached AI score columns and timestamps (Section 4.2)."""

    id: str
    rule_score: int | None = None
    execution_score: int | None = None
    overall_score: int | None = None
    rule_recommendation: str | None = None
    created_at: datetime
    updated_at: datetime


class TradeListResponse(CamelModel):
    items: list[TradeOut]
    next_cursor: str | None = None


class BulkTradeIn(CamelModel):
    items: list[TradeIn]


class BulkFailure(CamelModel):
    id: str
    error: str


class BulkTradeResult(CamelModel):
    inserted: int
    updated: int
    failed: list[BulkFailure] = Field(default_factory=list)


class DeleteAllTradesResult(CamelModel):
    """Sprint 18 -- response for the bulk 'clear all trades' action
    (e.g. starting fresh on a new MT5 account, per the user's own
    request)."""

    deleted_count: int


class TradeLessonSummary(CamelModel):
    """The planned-vs-actual comparison for one already-saved, closed
    trade (see ``app/engines/trade_lesson_engine.py``) -- the same
    engine ``POST /coach/review-trade`` uses, just scoped to a trade
    already in the database instead of one supplied fresh in the
    request body."""

    outcome: str
    has_enough_history: bool
    sample_size: int
    wins: int
    losses: int
    lessons: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class TradeDetailInsight(CamelModel):
    """Response for ``GET /trades/{id}/insight`` (Sprint 20 Phase 3) --
    the "Most Similar Trades" + "what changed vs my plan" sections for
    the trade detail view. ``lesson`` is ``None`` for a still-open trade
    (no exit price yet to compare a plan against)."""

    insight: SetupInsight
    lesson: TradeLessonSummary | None = None
