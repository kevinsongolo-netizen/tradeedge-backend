# Changelog

All notable changes to the TradeEdge AI backend are documented in this
file. Sprint 6 turned the project from a frontend-only JS app into a
full Python/FastAPI backend; the entries below are grouped by area
rather than by individual commit, since Sprint 6 shipped as one
coherent body of work.

## [14.0.0] — Sprint 14: Live MT5 Feed

Fourth slice of the Sprint 10 "future expansion" roadmap: a live data
bridge from an MT5 Expert Advisor (via MQL5's WebRequest) into the
Chart Analysis Engine, so it stays auto-filled with fresh candles
without the user re-pasting them, plus free MT5 mobile push
notifications the moment a valid setup forms.

**This is the first schema change since Sprint 9** — see "Database
migration required" below before deploying.

### Added

- `live_snapshots` table (`app/db/models/live_snapshot.py`,
  migration `0003_live_snapshots`) — stores the latest ingested
  Chart Analysis Engine result per (user, symbol, timeframe). One row
  per key; each new ingest overwrites the previous snapshot (a "latest
  live view", not a data warehouse — use Backtesting or the trade
  journal for history).
- `POST /api/v1/live/ingest` — an MT5 EA (or any other live source)
  pushes fresh candles here on every push interval. Runs the exact
  same Level 1/2/3 pipeline as `/chart/full-analysis/candles` (no
  engine code duplicated) and persists the result. Supports
  `?format=plain` — a few `KEY=value` lines instead of JSON, since
  MQL5 has no built-in JSON parser; the EA reads this directly and
  calls `SendNotification()` itself when `STATUS=VALID`.
- `GET /api/v1/live/latest?symbol=&timeframe=` — the website polls
  this to display the latest live analysis. Returns 404 with a clear
  message until the EA has pushed at least one update.
- `tools/mt5/TradeEdgeLiveFeed.mq5` — a ready-to-use MT5 Expert
  Advisor. Attach it to any chart; it pushes that chart's candles (plus
  optional M15 candles for automatic multi-timeframe confirmation,
  reusing Sprint 12's `confirm_with_m15`) to the backend on a timer,
  and sends a free MT5 mobile push notification whenever the backend
  says a setup is VALID (rate-limited so it doesn't repeat the same
  alert more than once per hour by default). Full setup instructions
  are in the file's header comment.
- Frontend: a third "Live feed (from MT5)" mode on the Chart Analysis
  Engine card — enter the same symbol/timeframe the EA is using, click
  to load (or check "Auto-refresh every 30 seconds"), and it renders
  through the exact same four panels as the other two reading paths.

### Database migration required

This sprint adds one new table. After merging this code, run the
existing migration workflow once more against your live Supabase
database (same steps as the original Sprint 6 setup):
`alembic upgrade head` with `DATABASE_URL` pointed at your production
connection string. No existing tables or data are touched.

### Tests

- `tests/api/test_live.py` (6 tests) — ingest/latest round trip,
  upsert-not-duplicate behavior, per-symbol isolation, the plain-text
  response format, and input validation. Uses the same in-memory
  SQLite test database as every other DB-backed test in this project.

## [13.0.0] — Sprint 13: Backtesting Engine

Third slice of the Sprint 10 "future expansion" roadmap: replays the
existing deterministic SMC engine + Level 2 trade validator against
historical candle data to see how the current rules would have
performed. No machine learning — this tests the *existing rules* the
same way a trader would manually review a chart, one candle at a time,
with zero lookahead bias.

### Added

- `app/backtest/backtest_engine.py` — `run_backtest()`. Walks a candle
  series with a rolling lookback window, re-running the real
  `analyze_candles()` + `validate_trade()` at each step exactly as a
  trader would see the chart forming; whenever the rules say VALID, a
  hypothetical trade opens at the *next* candle's open (never the
  current one, to avoid lookahead) and is walked forward candle by
  candle until its stop-loss or take-profit is hit. Aggregates win
  rate, total/average R-multiple, and profit factor. Only one trade is
  "open" at a time, matching how a single trader actually operates.
- `POST /api/v1/backtest/run` — new stateless `backtest` router.
  Accepts up to 2000 candles per run; requires at least 15 to produce
  a meaningful result.
- Frontend: a new "Backtest" card in AI Insights — paste a longer
  candle series, set the lookback window/min R:R/direction filter, and
  get back summary stats plus a scrollable per-trade list.

### Tests

- `tests/backtest/test_backtest_engine.py` (9 tests) — the SL/TP-hit
  simulation logic tested directly, input-validation guardrails, and
  full orchestration (entry/exit lifecycle, stats math) tested by
  mocking the engine's two dependencies so exact win/loss scenarios are
  fully controlled rather than reverse-engineered from real candle
  data.
- `tests/api/test_backtest.py` (2 tests) — one true end-to-end test
  with no mocking (real candle data through the real engine), to
  confirm the whole chain is wired correctly.

## [12.0.0] — Sprint 12: Market Context Filters

Second slice of the Sprint 10 "future expansion" roadmap: trading
session auto-detection, multi-timeframe confirmation, and a real
news/economic calendar filter (pluggable, same pattern as the vision
provider).

### Added

- `app/engines/session_engine.py` — pure trading-session detector
  (`detect_session()`). Given a UTC timestamp (defaults to now),
  returns the active session(s) (Asian/London/New York), whether it's
  the London/NY overlap, and a single "primary session" label.
- `POST /api/v1/tools/session-detect` — new endpoint on the Sprint 11
  `tools` router.
- `app/chart/multi_timeframe.py` — `confirm_with_m15()` derives the
  M15 confirmation flags (`hasM15Bos`/`hasM15Choch`/
  `hasM15EntryConfirmation`) Level 2 trade validation already accepts
  from a *real* M15 `ChartAnalysis`, instead of requiring the user to
  self-report them via checkboxes. `POST /api/v1/chart/full-analysis/
  candles` now accepts an optional `m15Candles` field — when supplied,
  the derived flags are OR'd with any manually-checked ones (manual
  checkboxes remain a valid fallback) and a `multiTimeframe` block is
  returned alongside `analysis`/`validation`/`coach`.
- `app/news/` (new package) — pluggable economic-calendar provider,
  mirroring `app/chart/vision_provider.py`'s design exactly:
  `PlaceholderCalendarProvider` (clearly-labeled example events, active
  by default) and `FinnhubCalendarProvider` (real data via Finnhub's
  free tier, activated the moment `FINNHUB_API_KEY` is set — zero other
  code changes). `app/news/news_filter_engine.py` is a pure function
  that checks a list of events against a planned trade time/buffer/
  currency filter and flags high-impact news nearby.
- `POST /api/v1/news/check-calendar` — new stateless `news` router.
- Frontend: an M15 candle textarea in the Chart Analysis Engine's
  candle-data mode (optional) with a new "Multi-Timeframe Confirmation"
  results panel, and a new "Session & News Check" card in AI Insights
  (session auto-detect button + a planned-trade-time news check form).

### Tests

- `tests/engines/test_session_engine.py` (7 tests), `tests/api/
  test_tools_session.py` (2 tests), `tests/chart/test_multi_timeframe.py`
  (6 tests), `tests/api/test_chart_multi_timeframe.py` (2 tests),
  `tests/news/test_news_filter_engine.py` (8 tests), `tests/news/
  test_calendar_provider.py` (5 tests, network mocked — no real Finnhub
  calls in CI), `tests/api/test_news.py` (2 tests). 32 new tests total.

### Note on Finnhub's economic calendar API

`FinnhubCalendarProvider`'s parsing is defensive (every field read
with a fallback) and wraps any unexpected response shape as a clear
`CalendarProviderError` rather than surfacing wrong data, since
Finnhub's exact free-tier response fields weren't independently
verifiable at the time this was written. Worth a quick sanity check
against a real response the first time a key is added.

## [11.0.0] — Sprint 11: Trade Management Tools

First slice of the "future expansion" roadmap flagged in Sprint 10:
position sizing, one-click journaling straight from a Chart Analysis
result, and AI review-after-close. All three are stateless additions
that reuse existing engines/schemas rather than touching Chart
Analysis Engine internals — proof the Sprint 10 architecture supports
exactly the kind of additive growth it was designed for.

### Added

- `app/engines/position_size_engine.py` — pure, deterministic
  risk-based position size calculator (`calculate_position_size()`).
  Works for any instrument (forex, indices, metals, crypto) via a
  broker-agnostic `value_per_point_per_lot` input rather than assuming
  a fixed contract size. Computes recommended lots (rounded down to
  the lot step so risk is never exceeded), actual risk amount,
  potential profit/R:R when a take-profit is supplied, and warns on
  a >3% single-trade risk or a stop distance too tight for the
  supplied risk/lot-step combination.
- `app/engines/trade_review_engine.py` — pure "AI review-after-close"
  engine (`build_trade_review()`). Takes one closed trade (the same
  shape the journal already collects) and returns a structured,
  plain-language review — outcome, what worked, what went wrong, and
  one specific lesson — built entirely from fields already captured
  when the trade was logged (rules-followed, worked/failed tags, exit
  reason, R:R, H4 trend/POI). Never just labels a trade win/loss.
- `POST /api/v1/tools/position-size` — new stateless `tools` router.
- `POST /api/v1/coach/review-trade` — added to the existing coach
  router. Accepts a whole trade in the body (synced or not), so it
  works immediately without requiring the trade to already exist in
  the database.
- Frontend: a "Position Size Calculator" card in AI Insights (with a
  "Use these levels" shortcut that pulls suggested entry/SL/TP
  straight from a Chart Analysis result), a "Save this trade to
  journal" button on Chart Analysis results that pre-fills the
  existing Log Trade modal, and a "Get AI Review" button inside that
  same modal once an exit price is entered.

### Tests

- `tests/engines/test_position_size_engine.py` (18 tests) and
  `tests/engines/test_trade_review_engine.py` (7 tests) — pure-engine
  unit tests.
- `tests/api/test_tools.py` and `tests/api/test_coach_review_trade.py`
  — endpoint-level tests, including validation-error paths.

## [10.0.0] — Sprint 10: Chart Analysis Engine

A new, independent module for Smart Money Concepts (SMC) chart
analysis, built with two Level-1 "reading" paths that both feed the
same Level 2/3 logic — see `app/chart/__init__.py` for the full
architecture rationale.

### Added

- `app/chart/candle_smc_engine.py` — deterministic SMC detection from
  real OHLC candle data: fractal swing highs/lows, trend inference,
  BOS/CHOCH structural-break detection, order blocks, fair value gaps
  (with mitigation tracking), equal-highs/equal-lows liquidity, and a
  premium/discount read. Pure functions, no I/O, unit-tested against
  hand-constructed candle series with known ground truth.
- `app/chart/vision_provider.py` — pluggable vision AI interface for
  reading a chart *screenshot*. Ships with `PlaceholderVisionProvider`
  (clearly-labeled mock output, active whenever no vision API key is
  configured) and `AnthropicVisionProvider` (real Claude vision
  analysis, activated automatically the moment `ANTHROPIC_API_KEY` is
  set — no other code changes needed). `get_vision_provider()` is the
  single factory/switch point.
- `app/chart/normalize.py` — adapts either Level-1 path's raw output
  into one canonical `ChartAnalysis` shape, so Level 2/3 never need to
  know which path produced their input.
- `app/chart/trade_validator.py` (Level 2) — validates a `ChartAnalysis`
  against SMC trading rules (H4 trend alignment, valid Point of
  Interest, lower-timeframe confirmation, minimum 1:2 Risk:Reward) and
  returns VALID/INVALID with itemized pass/fail reasons plus a
  suggested entry/stop-loss/take-profit when the analysis came from
  real candle data.
- `app/chart/coach_explainer.py` (Level 3) — turns the Level 1 + 2
  result into a plain-language explanation (never just "Buy"/"Sell" —
  always the reasoning) and a 7-component confidence breakdown (trend
  alignment, POI/liquidity/BOS/CHOCH/FVG quality, R:R quality) rolled
  up into an overall 0-100 score.
- `app/schemas/chart.py` and `app/api/v1/chart.py` — `/api/v1/chart/*`
  endpoints: `analyze-candles`, `analyze-image`, `validate`, `coach`,
  and combined `full-analysis/candles` / `full-analysis/image` for the
  common one-round-trip case.
- `app/services/chart_service.py` — orchestrates the above; no
  database dependency in this first cut (chart analyses are stateless
  by design — persistence for trade journaling / AI review-after-close
  is a tracked future addition, not a refactor).
- `anthropic` (soft dependency — only imported when a vision API key is
  configured) and `python-multipart` (required by FastAPI's
  `UploadFile`/`Form` for the image-upload endpoints) added to
  `requirements.txt`.
- 34 new tests across `tests/chart/` (candle engine, trade validator,
  coach explainer, vision provider factory/placeholder/error-wrapping)
  and `tests/api/test_chart.py` (all six endpoints, including the
  "no API key configured" placeholder path and input-validation
  rejections).

### Design notes for future expansion (see spec's "Future Expansion" list)

The two-Level-1-paths-into-one-canonical-shape architecture means MT5
live feed, TradingView integration, multi-timeframe analysis, and a
future ML confidence model can each be added as one more producer of
`ChartAnalysis` (or one more consumer of it, for a trained model) —
Level 2 and Level 3 do not change. Session detection, an economic-
calendar/news filter, position sizing, and trade journaling on top of
a chart analysis are all additive services layered on top of this
module, not changes to it.

## [8.0.0] — Sprint 8: Intelligent Trading Assistant, Coach, Explainable AI

Builds Vision Phases 5-7 on the existing Sprint 6/7 stack. Pure backend
work — no new infrastructure, no cloud/mobile/payments/computer-vision
(those are later vision phases, tracked in `TODO.md`).

### Added — Phase 5: Pre-Trade Analysis

- `app/engines/assistant_engine.py` — pure-function `analyze_pretrade()`:
  combines an optional ML prediction (Sprint 7) with historical
  similar-trade context (Sprint 6's `similar_engine.py`) into a trade
  quality score, win probability, AI confidence (High/Medium/Low, driven
  by how much relevant history backs the read, not the raw win
  probability), risk level, expected RR (win-probability-weighted
  expectancy in R-multiples), and a Strong Buy / Buy / Wait / Avoid
  recommendation. Never returns "Strong Buy" at Low confidence.
- Falls back gracefully to the trade's own rule score when no model has
  ever been trained (`NoActiveModelError` -> `ml_result=None`) — Phase 5
  doesn't require Sprint 7 to be "done" first.
- `app/schemas/assistant.py` (`PreTradeAnalysisResult`),
  `app/services/assistant_service.py` (`AssistantService`, orchestrates
  `MLPredictionService` + `SimilarService`), `app/api/v1/assistant.py`
  (`POST /api/v1/assistant/pretrade-analysis`).
- Live-verified via a real uvicorn server + seeded trades, both before
  and after training a model.

### Added — Phase 6: Personal Trading Coach (deep dive)

- `app/engines/coach_deep_dive_engine.py` — `build_deep_dive()` answers
  the vision doc's specific questions (why losing/winning, biggest
  mistake, best/worst setup, worst day to trade, best session, pair to
  stop trading) as structured fields, built entirely from Sprint 6's
  existing `analyze_setups()`/`analyze_mistakes()`/
  `compute_strategy_health()` — no new statistical computation.
- `app/schemas/coach.py` — added `DimensionStat`, `MistakeSummary`,
  `CoachDeepDive`. `app/services/coach_service.py` — added `deep_dive()`
  using the existing `coach_cache` TTL pattern.
  `GET /api/v1/coach/deep-dive` in `app/api/v1/coach.py`.
- Live-verified via a real uvicorn server + seeded trades: narrative
  fields, dimension stats (best/worst setup, worst day, best session),
  and the pair-to-stop-trading warning threshold (`count >= 3` and
  negative expectancy) all checked against real data.

### Added — Phase 7: Explainable AI

- `explain_trade()` and `historical_reasons()` in `assistant_engine.py`,
  surfaced as `strengths`/`weaknesses`/`historicalReasons` on every
  `/assistant/pretrade-analysis` response. Independently checks the same
  setup fields a trader would check by eye (H4 trend alignment,
  BOS/CHOCH, liquidity sweep, POI, planned RR vs. historical average,
  stated confidence) rather than decomposing the ML model's internal
  weights (SHAP-style explainability is out of scope for v1, noted in
  `TODO.md`) — an honest, documented design choice.

### Fixed — candidate dict casing bug (found during Sprint 8 development)

- `/api/v1/ai/analyze`, `/api/v1/ai/rule`, `/api/v1/ai/execution`
  (`app/api/v1/ai.py`) and `/api/v1/ai/similar` (`app/api/v1/similar.py`)
  were calling `TradeBase.to_model_kwargs()` (snake_case, meant for DB
  writes) before handing the candidate to engines that read camelCase
  keys (`h4Trend`, `h4PoiType`, `premiumDiscount`, `m15Confirmations`,
  `workedTags`, `failedTags`). Every SMC-structure check (H4 trend, POI,
  premium/discount, BOS/CHOCH, liquidity sweep) silently never matched
  in these four endpoints.
  - Measured impact: a fully rule-compliant candidate scored 34/100
    instead of 100/100 via `/ai/rule` (66-point discrepancy); a
    structurally-opposite trade scored 100% similarity instead of the
    correct 57.3% via `/ai/similar` (would have looked like a perfect
    historical match when it wasn't one at all).
  - Root cause: the persisted-save path (`TradeService._analyze_and_persist`)
    was unaffected — it correctly calls the already-saved ORM row's
    `Trade.to_engine_dict()`. Only the "check without saving" preview
    endpoints and similarity search were broken.
  - Fix: added `TradeBase.to_candidate_dict()` (`app/schemas/trade.py`) —
    camelCase, engine-shaped, with ISO date formatting — and updated the
    four call sites. Two regression tests added
    (`tests/api/test_ai.py::test_rule_preview_matches_persisted_score`,
    `tests/api/test_similar.py::test_similar_candidate_structure_fields_actually_affect_score`).

### Fixed — coach/stats cache invalidation was a silent no-op

- `TradeService._invalidate_caches()` calls
  `coach_cache.invalidate(user_id)` and `stats_cache.invalidate(user_id)`
  with a bare `user_id` after every trade write, but every entry these
  caches actually store is keyed by a tuple — e.g. `("insights",
  user_id, limit)`, `("deep_dive", user_id)`, `("summary", user_id)`.
  The old `invalidate()` did an exact `dict.pop(key, None)`, which never
  matched those tuple keys.
  - `stats_cache` (`FingerprintCache`) self-healed on the next read
    because its fingerprint changes whenever trade data changes, so this
    was latent/masked there.
  - `coach_cache` (plain `TTLCache`, no fingerprint) had no such safety
    net: `/coach/insights` and `/coach/deep-dive` could silently serve
    up to 60 seconds of pre-trade-write data after any trade was logged,
    created, or updated.
  - Found while writing this sprint's own deep-dive tests (two tests
    creating different trade data in sequence, within the 60s TTL
    window, got the same cached response).
  - Fix: `app/services/cache.py` — both `invalidate()` methods now drop
    every stored key whose second tuple element matches the given
    `user_id`, instead of doing an exact-key pop. Regression coverage in
    `tests/services/test_cache.py` (3 tests, new file).

### Fixed — CoachDeepDive schema silently dropping the version field

- `build_deep_dive()` returns a `version` key, but
  `app/schemas/coach.py`'s `CoachDeepDive` didn't declare a `version`
  field — Pydantic's default `extra='ignore'` silently dropped it
  before it ever reached the API response. Added `version: str` to the
  schema.

### Added — tests

- `tests/engines/test_assistant_engine.py` (24 tests):
  `classify_ai_confidence`, `classify_risk_level`, `compute_expected_rr`,
  `recommend`, `explain_trade`, `historical_reasons`, and full
  `analyze_pretrade()` composition (with and without an ML result).
- `tests/engines/test_coach_deep_dive_engine.py` (14 tests):
  `_worst_confident_row`, `_why_losing`, `_why_winning`,
  `build_deep_dive()` (full data, no-pair-warning cases, empty-history
  fallback).
- `tests/api/test_assistant.py` (4 tests): pretrade-analysis before/
  after training, counter-trend weakness detection, 422 on missing
  required field.
- `tests/api/test_coach.py`: +3 tests for `GET /coach/deep-dive`.
- `tests/services/test_cache.py` (3 tests, new file): cache invalidation
  regression coverage.
- 50 new tests this sprint; 216 total passing, 0 failures (130 Sprint 6
  + 31 Sprint 7 + 5 Sprint 7 audit + 50 Sprint 8).

## [6.0.0] — Sprint 6: Python/FastAPI Backend

### Added — Database layer

- Async SQLAlchemy 2.0 models: `User`, `Trade`, `AIAnalysis` (versioned
  scoring history, append-only), `ScoringWeights` (per-user engine
  weight overrides), `MLExport`/`MLModel` (dataset export audit log).
  All registered in `app/db/models/__init__.py` so Alembic autogenerate
  and `Base.metadata.create_all` (test fixtures) both see the full
  schema.
- Repository pattern (`app/db/repositories/*.py`) — all SQL lives here;
  services never touch SQLAlchemy directly. `TradeRepository` supports
  cursor-based pagination (base64-encoded cursor) with pair/session/
  date/outcome filters, upsert, cached-score updates, and
  `max_updated_at` (used for cache-key invalidation).
- Alembic wired for async engines (`alembic/env.py` uses
  `async_engine_from_config`); `0001_initial` migration creates every
  table and seeds `users(id=1)` via `op.bulk_insert`.
- `scripts/seed_dev.py` — seeds the default user and, optionally, 40
  generated sample trades through the real `TradeService` (so seeded
  trades get real AI analysis, not fixture stubs).

### Added — AI engines (ported from JS, Section 6 of the architecture spec)

Nine pure-function engines ported 1:1 from the frontend's JS, preserving
scoring behavior exactly (verified via parity-style unit tests):
`rule_engine.py`, `execution_engine.py`, `reason_engine.py`,
`similar_engine.py`, `statistics_engine.py`, `strategy_health_engine.py`,
`setup_engine.py`, `mistake_engine.py`, `coach_engine.py`. Plus a new
`ml_dataset.py` (no JS equivalent — built for Sprint 7).

- `similar_engine.py` implements both the new weighted-v1 algorithm
  (Gaussian similarity for continuous features — RR, confidence, lot
  size via log10 ratio, entry proximity; binary equality for
  categorical features; ordinal ranking for news impact; normalized
  weights summing to 100, with per-match feature `contributions`) and
  `search_similar_legacy()` (the old binary-matching algorithm), so
  existing UI expectations aren't broken mid-migration.
- `ml_dataset.py` builds leakage-safe historical/rolling features
  (`hist_win_rate_all`, `hist_win_rate_pair`, `hist_avg_rr_all`,
  `hist_streak_dir`, EMA of rule/execution scores) computed only from
  chronologically prior trades — never from future data.
- `coach_engine.py` generates insights purely from calculated
  statistics; no hardcoded advice strings.

### Added — Services, caching, API

- Service layer (`app/services/*.py`) orchestrates repositories +
  engines inside transactions. `TradeService._analyze_and_persist()` is
  the core save flow: runs `AIService.analyze_trade`, persists the
  `AIAnalysis` row, updates cached score columns on `Trade`, invalidates
  stats/coach caches.
- In-process caching: `FingerprintCache` (keyed on user id + trade count
  + max `updated_at` + active filters) for statistics, and a 60s
  `TTLCache` for coach insights — no external Redis dependency.
- 21 REST endpoints across trades, ai, similar, stats, coach, and ml
  routers, mounted under `/api/v1`, plus `/healthz`, `/readyz` (now
  checks Alembic is at head), `/version` (per-package dependency
  versions). Full list in `README.md`.
- Pydantic v2 schemas with a `CamelModel` base (`alias_generator=to_camel`)
  so JSON matches the existing JS frontend's shape; the ML dataset
  schema (`MlRow`) is deliberately plain snake_case, matching the
  architecture spec's Section 8 contract verbatim.
- Global exception-handling middleware (`app/errors.py`) — consistent
  JSON error envelope across the whole API.
- `structlog` JSON request logging via a plain ASGI middleware (see
  "Fixed" below for why it isn't `BaseHTTPMiddleware`).

### Added — Frontend integration

- New `frontend/js/api_client.js` — `fetch()`-based client
  (`TradeEdgeAPI.analyzeTrade/getStatistics/getDashboardData/
  getChartData/getCoachViewModel/syncTrade/deleteTrade/
  ensureBackendSynced`, plus dataset export helpers) replacing the old
  synchronous in-browser engine calls.
- `frontend/js/ai_dashboard.js` reduced to UI orchestration only —
  `computeAiDashboardData()` now requires pre-calculated
  statistics/setup/mistakes/strategyHealth from the backend instead of
  falling back to local JS engines.
- `index.html`: all call sites that used to call local engines
  synchronously (`saveJournalEntry`, `findSimilarTrades`,
  `refreshRuleScorePreview`, `refreshTradeAnalysis`, `renderAIDashboard`,
  `renderAICharts`, `renderAICoach`, `confirmImport`, etc.) converted to
  `async`/`await` calls into `TradeEdgeAPI`. UI markup and layout are
  unchanged.
- The 9 old engine JS files (`rule_engine.js`, `execution_engine.js`,
  `reason_engine.js`, `similar_trade_engine.js`, `setup_engine.js`,
  `mistake_engine.js`, `statistics_engine.js`,
  `strategy_health_engine.js`, `coach_engine.js`, `ml_dataset.js`) are
  retired — no longer loaded by `index.html`.

### Added — Tests

130 tests, all passing: 61 engine unit tests, 20 repository tests
(against a real temp-file SQLite database via the async engine), 49 API
endpoint tests (`FastAPI TestClient`). Test isolation via
`tests/conftest.py` setting `DATABASE_URL`/`EXPORT_DIR`/`APP_ENV` at
module import time (before `app` is imported) plus autouse fixtures that
wipe and reseed the schema per test.

### Fixed

- **pytest / `TestClient` hang.** `RequestLoggingMiddleware` was
  originally a `starlette.middleware.base.BaseHTTPMiddleware` subclass.
  `BaseHTTPMiddleware` runs the downstream app in a separate `anyio`
  task and hands the response back over an in-memory stream, which can
  deadlock when driven synchronously — exactly what
  `fastapi.testclient.TestClient` does. Rewritten as a plain ASGI
  middleware (`__call__(self, scope, receive, send)`) with no extra task
  or stream in between. Behavior (per-request UUID, `request.received`/
  `request.completed`/`request.failed` logs, `X-Request-ID` header) is
  unchanged.
- **`SimilarSearchResult` missing fields.** Live smoke testing surfaced
  validation errors for a missing per-match `outcome` field and missing
  top-level `confidence`/`weightsSnapshot` fields on the legacy search
  path. Fixed in both `search_similar()` and `search_similar_legacy()`.
- **`averageRR` alias mismatch.** Pydantic's auto-camelCase produced
  `averageRr`, not the `averageRR` the frontend expects. Fixed with
  explicit `Field(alias="averageRR")` overrides in `SimilarSearchResult`,
  `GroupStats`, and `SetupGroupStat`.
- **ML dataset column casing.** Initially built with camelCase columns;
  the architecture spec's Section 8 requires snake_case
  (`user_id`, `has_bos`, `day_of_week`, etc.). Rewrote
  `ML_COLUMN_ORDER` and all dict keys to snake_case, switched `MlRow` to
  a plain (non-camel) `BaseModel`.
- **Bulk upsert validation vs. partial-success semantics.** A malformed
  row in `POST /trades/bulk` is rejected by Pydantic (422) before it
  ever reaches the service's per-row try/except, so a single bad row
  can't silently corrupt a batch — but a batch of otherwise-valid
  inserts/updates still partially succeeds. Covered by
  `test_bulk_upsert_mixed_insert_and_update`.

### Known deviations from the original spec

- **Python 3.10, not 3.12+.** Only Python 3.10 was available in the
  build sandbox. The codebase avoids 3.11/3.12-only syntax, so running
  on 3.12+ is expected to work unchanged, but this hasn't been verified
  in this environment. Recommend running the test suite once on 3.12+
  before treating that combination as confirmed.

## [7.0.0] — Sprint 7: Machine Learning (v1)

Built on a new `sprint-7-ml` branch off the Sprint 6 baseline; no
Sprint 6 file was changed except the two bug fixes noted below and
purely additive wiring (new router registration, a version bump, one
new settings key).

### Added — Phase 1: Dataset validation

- `app/ml/dataset_validation.py` (new) — `generate_validation_report()`:
  total/valid/invalid trade counts, a missing-field breakdown (parsed
  from Sprint 6's per-row `validation_errors`), duplicate-id detection,
  win/loss/breakeven class distribution, and a `readyForTraining` gate
  requiring at least 30 valid trades (`MIN_TRAINING_ROWS`).
- `GET /api/v1/ml/dataset/validation-report` (new endpoint, new router
  file `app/api/v1/ml_train.py`) — read-only, never trains anything.

### Added — Phase 2: Feature engineering

- `app/ml/features.py` (new): `CATEGORICAL_FEATURES` (pair, asset,
  direction, session, h4_trend, h4_poi_type, emotion) and
  `NUMERIC_FEATURES` (BOS/CHOCH/liquidity-sweep flags, planned RR, rule
  score, execution score, confidence, six leakage-safe rolling history
  columns already in Sprint 6's dataset, plus one new one:
  `hist_strategy_health_score`).
- `hist_strategy_health_score` reuses Sprint 6's
  `compute_strategy_health()` engine unmodified — computed from only
  the trades strictly before the one being scored.
- `historical_features_for_candidate()` computes the six Sprint-6
  rolling columns for a **not-yet-logged** trade by appending one
  synthetic, far-future-dated row to the user's real history and
  running it through Sprint 6's own `build_dataset()` — reusing the
  exact training-time formulas rather than re-deriving them, so
  training and prediction can never drift out of sync.
- `build_preprocessor()` — a scikit-learn `ColumnTransformer`
  (one-hot + median-impute for categoricals, median-impute + scale for
  numerics) persisted *inside* the model pipeline (Phase 6), so the
  same fitted encoders are automatically reused at prediction time.

### Added — Phase 3/4: Training + model comparison

- `app/ml/train.py` (new): `split_dataset()` (stratified train/
  validation/test split, falling back to a plain split if a class has
  too few members); `train_and_compare()` trains Logistic Regression,
  Random Forest, and Gradient Boosting (all regularized/shallow —
  `class_weight="balanced"`, capped tree depth — since personal trading
  journals are small datasets), scores each on validation
  (accuracy/precision/recall/F1/ROC AUC), picks the best by ROC AUC
  (F1 fallback), refits the winner on train+validation, and reports
  final metrics on a held-out test split. Flags `overfitWarning` if
  train accuracy beats test accuracy by more than 25 points.
  `InsufficientDataError` (a `ValidationError` subclass — 422) guards
  against training on fewer than 15 rows even after Phase 1's 30-row
  gate (defense in depth for direct callers of `train_and_compare()`).

### Added — Phase 5/6: Prediction API + model persistence

- `app/ml/persistence.py` (new) — `save_model()`/`load_model()` via
  `joblib`; `next_version()` (simple incrementing `v1`, `v2`, ...).
- `app/db/repositories/ml_model_repo.py` (new) — reads/writes Sprint
  6's `ml_models` table (created empty in Sprint 6 specifically for
  this). `insert_and_activate()` deactivates every other version for
  the user in the same transaction, so exactly one version is active.
- `app/services/ml_training_service.py`, `ml_prediction_service.py`
  (new) — orchestrate Phase 1–6 and prediction respectively.
- New endpoints: `POST /api/v1/ml/train`, `GET /api/v1/ml/models`,
  `GET /api/v1/ml/models/active`, `POST /api/v1/ml/predict`.
- `scripts/train_v1.py` (new) — CLI entry point calling the exact same
  `MLTrainingService.train()` the API uses (referenced by Sprint 6's
  `app/db/models/ml_export.py` docstring as the file that would
  eventually populate `ml_models`).
- `app/config.py` — new `models_dir` setting (default `./data/models`),
  `.env.example` updated to match.
- `app/config.py` — `app_version` bumped `6.0.0` -> `7.0.0`;
  `app/api/v1/health.py`'s `/version` engines dict gained
  `"mlTraining": "7.0"`.
- `requirements.txt` — added `numpy`, `pandas`, `scikit-learn`, `joblib`.

### Fixed (Sprint 6 bugs, per "fix bugs only" scope)

- **`scripts/seed_dev.py --with-sample-trades` crashed.** Passed the
  raw camelCase fixture dict straight to
  `TradeService.create_trade()`, which expects `Trade`-model kwargs
  (snake_case, a real `date` object, `exit_price` not `exit`) — exactly
  what `TradeIn(**trade).to_model_kwargs()` produces and exactly what
  the real `POST /trades` router does before calling the same service
  method. Failed with `SQLite Date type only accepts Python date
  objects` because `date` was still a string. Only the
  `--with-sample-trades` path was affected (never previously exercised
  end-to-end); user-only seeding was unaffected. Fixed by routing
  through `TradeIn(**trade).to_model_kwargs()` like the router does.
- **`tests/api/test_health.py::test_version_returns_app_and_version`**
  asserted a hardcoded `"6.0.0"` — updated to `"7.0.0"` to track the
  current release rather than freeze a historical value (not a
  behavior bug, just a test that needed to move with the version bump).

### Added — Tests

31 new tests, all passing (161 total across Sprint 6 + 7, 0 failures):
`tests/ml/test_dataset_validation.py` (6), `tests/ml/test_features.py`
(9), `tests/ml/test_train.py` (5), `tests/api/test_ml_train.py` (11
end-to-end API tests: validation report, train, retrain/versioning,
model listing, predict, and every error path — insufficient data, no
active model). `tests/conftest.py` gained a `MODELS_DIR` temp-dir env
var (mirroring the existing `EXPORT_DIR` pattern) for test isolation.

### Known limitations

- Trains best with 30+ valid trades; below that, `readyForTraining` is
  `false` and training is refused outright rather than producing a
  misleadingly precise-looking model.
- No scheduled/automatic retraining yet — `POST /ml/train` is on-demand
  only (see `TODO.md`).
- Single active model per user at a time; no A/B comparison of two
  active versions yet.

## [7.1.0] — Post-Sprint-7 production readiness audit

A full independent audit (architecture, DB design, API design, the ML
pipeline, security, performance, error handling, tests, docs, code
duplication, tech debt, scalability) was performed treating the
Sprint 6 + 7 code as someone else's PR, not assuming any prior work was
correct. Six real issues were found and fixed; the rest are documented
below as tracked, known limitations.

### Fixed

- **`POST /ml/train` and `POST /ml/predict` blocked the event loop.**
  `train_and_compare()` (fits 3 scikit-learn models) and `joblib.load()`
  are genuinely CPU-bound/blocking, but were called directly inside
  `async def` service methods with no offloading — measured at 3.4s of
  wall-clock time on a 40-row dataset spent entirely on the single
  event-loop thread, during which literally no other request (including
  `/healthz`) could be served. Fixed by wrapping both in
  `asyncio.to_thread()`. Verified two ways: a new unit test
  (`tests/ml/test_audit_fixes.py::test_train_and_compare_offloaded_does_not_block_event_loop`)
  and a live check — 10 concurrent `/healthz` requests fired during a
  real 3.7s training run all returned in single-digit milliseconds
  instead of queuing behind it.
  Files: `app/services/ml_training_service.py`, `ml_prediction_service.py`.
- **Model reloaded from disk on every single prediction.** `joblib.load()`
  ran on every `/ml/predict` call even though the active model rarely
  changes. Added an in-process cache keyed by `(user_id, file_path)` —
  training a new version naturally produces a cache miss (new file
  path), so nothing needs explicit invalidation.
  File: `app/services/ml_prediction_service.py`.
- **No DB-level guarantee of "one active model per user."** Two
  concurrent `POST /ml/train` calls for the same user could both
  compute the same "next version" string and/or both end up marked
  active — the application code already deactivated other rows in the
  same transaction, but nothing enforced it at the database level.
  Added (migration `0002_ml_models_indexes`, mirrored in
  `app/db/models/ml_export.py`'s `__table_args__` so
  `Base.metadata.create_all` — what the test suite uses — builds the
  identical schema `alembic upgrade head` does): a unique index on
  `(user_id, version)`, a partial unique index enforcing at most one
  `is_active=True` row per user, and plain indexes on
  `ml_models.user_id`/`ml_exports.user_id` (previously full-table-scanned
  on every lookup). `MLTrainingService.train()` now catches the
  resulting `IntegrityError` and surfaces a clean 409 instead of a raw
  500. Verified with two new repository-level tests proving the
  constraints actually fire.
- **`add_hist_strategy_health()` mutated its caller's data.** Silently
  added a key to the dicts inside the list the caller passed in, rather
  than returning new rows — a surprising side effect for a function
  that reads as pure from the call site. Fixed to build new dicts;
  added a regression test.
  File: `app/ml/features.py`.
- **Duplicated quality-bucket thresholds.** `app/services/ml_prediction_service.py`
  re-declared the same 90/80/70 letter-grade cutoffs Sprint 6's
  `app/engines/ml_dataset.py::_quality_bucket()` already implements,
  instead of importing it. Now imports and reuses the one
  implementation.
- **CORS misconfiguration.** `app/main.py` paired `allow_origins=["*"]`
  with `allow_credentials=True` — browsers forbid that combination, so
  `CORSMiddleware` was silently echoing back whatever `Origin` header
  each request sent instead of enforcing an allowlist. This app
  authenticates via a plain header (`X-User-Id`), never cookies, so it
  never needed `allow_credentials=True`. Added a `cors_allow_credentials`
  setting, defaulting to `False`.
- **Docker image ran as root, with no `.dockerignore`.** Added a
  non-root `USER` in the Dockerfile (owns only `/app/data`, the one
  path the app writes to) and a `.dockerignore` — previously `COPY . .`
  would have copied `.venv/`, `.git/`, and any local dev SQLite database
  straight into the image.

### Added — Tests

5 new regression tests (`tests/ml/test_audit_fixes.py`), one per fix
above (mutation, both DB constraints, cache behavior, event-loop
non-blocking). 166 tests total, 0 failures.

### Documented, not fixed (tracked for Sprint 8 — see TODO.md)

- No real authentication — `X-User-Id` header is unverified (by design
  through Sprint 7; Sprint 8 scope).
- No rate limiting on `POST /ml/train` (CPU + disk cost per call, no
  throttling).
- In-process caches (stats/coach fingerprint caches, the new model
  cache) don't survive a restart and aren't shared across multiple
  worker processes.
- `hist_strategy_health_score` computation is O(n²) in the number of a
  user's trades (recomputes Strategy Health from scratch for every
  prefix) — fine at personal-journal scale (hundreds to low thousands
  of trades), would need an incremental version at much larger scale.
- No retention/cleanup policy for `data/exports/` or `data/models/` —
  every export and every trained model version accumulates on disk
  forever.
- Frontend has zero UI for any Sprint 7 endpoint
  (`/ml/train`, `/ml/predict`, `/ml/dataset/validation-report`) — the
  capability exists in the API only.
