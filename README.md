# TradeEdge AI — Backend

Python/FastAPI backend for TradeEdge AI. All AI scoring that used to run
as JavaScript in the browser (rule scoring, execution scoring, reason
generation, weighted similarity search, statistics, strategy health,
setup/mistake analysis, and coach insights) now runs here as pure,
tested Python functions behind a REST API, backed by SQLAlchemy 2.0
(async) + Alembic, with a leakage-safe ML dataset export ready for
Sprint 7 (Machine Learning).

## Requirements

- Python 3.10+ (developed and tested on 3.10.12; the codebase uses no
  3.11/3.12-only syntax, so 3.12+ works too — 3.12+ was the original
  target but only 3.10 was available in the build sandbox)
- SQLite for local dev (default). `DATABASE_URL` is a standard
  SQLAlchemy async URL, so pointing it at PostgreSQL
  (`postgresql+asyncpg://...`) for staging/prod is a one-line config
  change — no code changes required.

## Setup

```bash
cd tradeedge-backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # defaults work as-is for local dev
```

## Database: migrate and seed

```bash
alembic upgrade head        # creates tables + seeds users(id=1)
python scripts/seed_dev.py --with-sample-trades  # optional: also loads 40 sample trades
```

`alembic upgrade head` is required before the API can serve trade data.
`scripts/seed_dev.py` is optional and idempotent — safe to re-run.

## Run

```bash
uvicorn app.main:app --reload
```

Server starts on `http://127.0.0.1:8000`.

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI schema: <http://127.0.0.1:8000/openapi.json>

Every response carries an `X-Request-ID` header, and each request is
logged as structured JSON (`structlog`) to stdout.

## API surface

System (outside `/api/v1`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe — also checks Alembic is at head |
| GET | `/version` | App name/version + per-package dependency versions |

Trades (`/api/v1/trades`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/trades` | Create or upsert a trade (runs AI analysis, persists it) |
| GET | `/api/v1/trades` | List trades — cursor pagination, pair/session/date/outcome filters |
| GET | `/api/v1/trades/{id}` | Get one trade |
| PATCH | `/api/v1/trades/{id}` | Partially update a trade |
| DELETE | `/api/v1/trades/{id}` | Delete a trade |
| POST | `/api/v1/trades/bulk` | Bulk upsert (used by the frontend's one-time localStorage migration) |

AI (`/api/v1/ai`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/ai/analyze` | Run full AI analysis on a trade without saving it |
| POST | `/api/v1/ai/rule` | Rule engine only |
| POST | `/api/v1/ai/execution` | Execution engine only |
| GET / PUT | `/api/v1/ai/weights` | Get / override per-user engine weights |
| POST | `/api/v1/ai/similar` | Weighted similar-trade search |

Statistics & coaching:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/stats/summary` | Full performance statistics |
| GET | `/api/v1/stats/charts` | Chart series data |
| GET | `/api/v1/stats/strategy-health` | Strategy health scorecard |
| GET | `/api/v1/stats/setups` | Best-performing setup dimensions |
| GET | `/api/v1/stats/mistakes` | Mistake/habit analysis |
| GET | `/api/v1/coach/insights` | Data-backed coaching insights (no hardcoded advice) |
| GET | `/api/v1/coach/deep-dive` | Sprint 8 — structured Q&A: why losing/winning, best/worst setup, worst day, best session, pair to stop trading |

Intelligent Trading Assistant (Sprint 8 — Vision Phases 5 & 7):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/assistant/pretrade-analysis` | Pre-trade quality score, win probability, risk level, expected RR, Strong Buy/Buy/Wait/Avoid recommendation, plus a plain-language explanation (strengths/weaknesses/historical reasons). Works before any model is trained — falls back to a rule-score-only estimate. |

ML dataset (Sprint 7 prep):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/ml/dataset` | Export the training dataset as JSON |
| GET | `/api/v1/ml/validate` | Validate the dataset without exporting |
| POST | `/api/v1/ml/exports` | Write a JSON + CSV export to `EXPORT_DIR` |

Full request/response schemas are in Swagger UI (`/docs`) — this table
is a map, not a contract.

## Tests

```bash
pytest -v
```

216 tests, all passing: DB/repository tests against a real temp SQLite
file, pure-function engine unit tests (rule, execution, similar,
statistics, strategy health, setup, mistake, coach, ML dataset,
assistant, coach deep-dive), API endpoint tests through FastAPI's
`TestClient` (trades/ai/similar/stats/coach/ml/assistant), and
in-process cache unit tests. See CHANGELOG.md for the breakdown by
sprint (130 Sprint 6 + 31 Sprint 7 + 5 Sprint 7 audit + 50 Sprint 8).

## Configuration

All config comes from environment variables (see `.env.example`):

| Var | Default | Notes |
|---|---|---|
| `APP_ENV` | `dev` | `dev` / `staging` / `prod` — toggles debug logging |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/tradeedge.db` | Any SQLAlchemy async URL |
| `SECRET_KEY` | `dev-only-change-me` | For future JWT signing (Sprint 8 auth) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | `["*"]` | JSON array; restrict in non-dev environments |
| `CORS_ALLOW_CREDENTIALS` | `false` | Only enable together with a non-wildcard `CORS_ORIGINS` — see "Production readiness notes" below |
| `EXPORT_DIR` | `./data/exports` | Where `POST /ml/exports` writes JSON/CSV files |

## Docker

```bash
docker build -t tradeedge-backend .
docker run -p 8000:8000 --env-file .env tradeedge-backend
```

## Project layout

```
app/
  api/v1/        # routers: trades, ai, similar, stats, coach, ml, health
  db/models/      # SQLAlchemy models: User, Trade, AIAnalysis, ScoringWeights, MLExport
  db/repositories/# all SQL lives here — services never touch SQLAlchemy directly
  engines/        # pure-function ports of the 9 JS AI engines (no I/O)
  services/       # orchestrates repositories + engines, owns transactions/caching
  schemas/        # Pydantic v2 request/response models (camelCase over the wire)
alembic/          # migrations (0001_initial creates all tables + seeds users(id=1))
scripts/seed_dev.py
tests/            # db/, engines/, api/
```

## Frontend integration

The existing `index.html` single-page journal is unchanged visually.
`frontend/js/api_client.js` replaces the old in-browser engine calls
with `fetch()` calls into this API; `frontend/js/ai_dashboard.js` is now
UI-orchestration only (no scoring logic). The 9 old engine JS files
(`rule_engine.js`, `execution_engine.js`, etc.) have been retired — their
logic lives in `app/engines/*.py` now.

## Sprint 7 readiness

`GET /api/v1/ml/dataset` and `POST /api/v1/ml/exports` produce a
leakage-safe, flat, snake_case row per trade (historical/rolling
features computed only from chronologically prior trades), matching
the architecture spec's Section 8 column contract exactly — ready to
load straight into a scikit-learn/pandas pipeline with no reshaping.

## Machine Learning (Sprint 7)

Sprint 7 adds a trained ML layer on top of Sprint 6's rule-based
scoring: a model learns from the user's own closed trade history and
predicts the win probability / quality of a trade — logged or
hypothetical — using the same setup fields (pair, session, SMC
structure, AI scores, etc.) plus leakage-safe rolling history features.

### Dataset requirements

A trade is **valid** for training if it has: `id`, `date`, `pair`,
`direction`, `asset`, `entry`, `pnl`, `rr`, `session`, `rule_score`,
`execution_score`, `overall_score`, and `outcome` (Sprint 6's
`ML_REQUIRED_FIELDS`) — in practice, any trade saved through
`POST /trades` with an `exit`/`pnl` already has all of these. At least
**30 valid trades** are required before training is allowed
(`MIN_TRAINING_ROWS` in `app/ml/dataset_validation.py`) — fewer than
that and any reported model quality would be noise, not signal.

Check readiness any time with:

```bash
curl http://127.0.0.1:8000/api/v1/ml/dataset/validation-report
```

This reports total/valid/invalid trade counts, which fields are most
commonly missing, duplicate trade ids, the win/loss/breakeven class
distribution, and whether training is currently allowed
(`readyForTraining` + `reason`). It never trains anything — it's
read-only, safe to poll from a dashboard.

### Features

`app/ml/features.py` turns each trade into: `pair`, `asset`,
`direction`, `session`, `h4_trend`, `h4_poi_type` (POI), `emotion`
(psychology) as one-hot-encoded categoricals; `has_bos`, `has_choch`,
`has_liquidity_sweep`, `planned_rr`, `rule_score`, `execution_score`,
`confidence`, and six leakage-safe rolling history columns (win rate,
avg RR, streak, rule/execution EMA) plus a new `hist_strategy_health_score`
(computed from Sprint 6's Strategy Health engine, using only trades
strictly before the one being scored) as scaled numerics. Encoding and
scaling live inside the persisted scikit-learn `Pipeline`, so the exact
fitted encoders used at training time are automatically reapplied at
prediction time.

Note: **realized** RR (`rr`) is deliberately excluded from the feature
set — only **planned** RR (`planned_rr`, known before the trade closes)
is used, so the model can't "cheat" by learning from a value that's
really just a restatement of the outcome.

### Training process

`POST /api/v1/ml/train` (or `python scripts/train_v1.py`):

1. **Validate** (Phase 1) — refuses to train if the dataset isn't
   ready (422 `INSUFFICIENT_TRAINING_DATA`).
2. **Feature-engineer** (Phase 2) — see above.
3. **Split** (Phase 3) — train/validation/test, stratified on
   win/loss when both classes have enough members.
4. **Train + compare** (Phase 4) — fits Logistic Regression, Random
   Forest, and Gradient Boosting on the training split; scores each on
   the validation split (accuracy, precision, recall, F1, ROC AUC);
   picks the best by ROC AUC (falling back to F1). The winner is then
   refit on train+validation and given a final, honest score on the
   held-out test split it never influenced — that's the number that
   gets persisted and reported. An `overfitWarning` flag fires if
   train-set accuracy beats test-set accuracy by more than 25 points.
5. **Persist** (Phase 6) — the fitted pipeline is saved via `joblib` to
   `MODELS_DIR` (default `./data/models`), versioned `v1`, `v2`, ... per
   user, and registered in the `ml_models` table with the new version
   marked active (previous versions stay on disk, just deactivated).

### API usage

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/ml/dataset/validation-report` | Phase 1 report — safe to call anytime |
| POST | `/api/v1/ml/train` | Train, compare, and persist the best model as the new active version |
| GET | `/api/v1/ml/models` | List every trained version for the current user |
| GET | `/api/v1/ml/models/active` | The currently active (latest) model's info |
| POST | `/api/v1/ml/predict` | Predict win probability / quality for a trade |

`POST /api/v1/ml/predict` example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ml/predict \
  -H "Content-Type: application/json" \
  -d '{
        "pair": "EURUSD", "asset": "Forex", "direction": "buy", "session": "London",
        "h4Trend": "Bullish", "h4PoiType": "Order Block", "hasBos": true,
        "plannedRR": 3.0, "ruleScore": 85, "confidence": 80, "emotion": "Calm"
      }'
# -> {"winProbability":0.62,"predictedQualityScore":62.0,
#     "predictedQualityBucket":"D","modelVersion":"v1","algorithm":"random_forest"}
```

Only the trade's own setup fields go in the request — historical/
rolling features are always computed server-side from the caller's
real trade history, never supplied by the client. Calling `/predict`
before ever training returns 404 `NO_ACTIVE_MODEL`.

### How to retrain

Retraining is just calling `POST /api/v1/ml/train` again (or
`python scripts/train_v1.py`) once more trades have accumulated — each
call creates a new version (`v2`, `v3`, ...), evaluates it fresh, and
atomically activates it if it completes successfully. Old versions'
`.joblib` files are left on disk (`data/models/`) so a previous version
can be inspected or manually restored if a new one performs worse.
There's no schedule built in yet — retraining is on-demand only (see
`TODO.md` for a "Later" note on periodic retraining triggers).

### Limitations (read before trusting predictions)

- Needs at least 30 valid, closed trades — accuracy on a dataset that
  small will be noisy; treat early predictions as directional, not
  precise.
- Single-user, in-process: no cross-user model sharing, and the model
  registry (`ml_models`) is scoped per user by design (Sprint 6/7 have
  no cross-account training set).
- `overfitWarning: true` in a training result means exactly what it
  says — don't trust that version's numbers until retrained on more
  data.

## Intelligent Trading Assistant & Coach (Sprint 8)

Sprint 8 builds three of the vision doc's phases on top of the existing
stack — no new infrastructure, pure backend work reusing Sprint 6/7's
engines and services.

### Phase 5 — Pre-Trade Analysis

`POST /api/v1/assistant/pretrade-analysis` scores a candidate trade
*before* it's logged: trade quality score, win probability, AI
confidence (High/Medium/Low — driven by how much relevant history backs
the analysis, not just the win probability), risk level, expected RR
(expectancy in R-multiples), historical win rate over similar past
trades, and a Strong Buy / Buy / Wait / Avoid recommendation.

Works from day one: if no model has been trained yet (`POST /ml/train`
never called), it falls back to the trade's own rule score as the
quality estimate rather than erroring, with an explicit note in
`historicalReasons`. "Strong Buy" is never returned at Low confidence —
a low-confidence read can suggest Buy or Avoid at the extremes, but
"strong" implies real historical backing that thin data can't provide.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/assistant/pretrade-analysis \
  -H "Content-Type: application/json" \
  -d '{"pair":"EURUSD","direction":"buy","h4Trend":"Bullish","hasBos":true,"plannedRR":2.5,"confidence":80}'
```

### Phase 6 — Personal Trading Coach (deep dive)

`GET /api/v1/coach/deep-dive` answers the vision doc's specific
coaching questions as structured fields — why am I losing, why am I
winning, biggest mistake, best/worst setup, worst day to trade, best
session, which pair to stop trading — built entirely from Sprint 6's
existing `analyze_setups`/`analyze_mistakes`/`compute_strategy_health`
engines. No new statistics; this is a re-packaging layer. Fields fall
back to `null` (with an honest "not enough data yet" message in the
narrative fields) rather than fabricating an answer when a dimension
hasn't cleared the same `count >= 3` confidence threshold `setup_engine.py`
already uses.

### Phase 7 — Explainable AI

Every `/assistant/pretrade-analysis` response includes `strengths`,
`weaknesses`, and `historicalReasons` arrays — plain-language checks of
the same fields a trader would check by eye (H4 trend alignment,
BOS/CHOCH, liquidity sweep, POI, planned RR vs. the trader's own
historical average, stated confidence), independent of whatever the ML
model actually weighted internally. This is a deliberate design choice,
not a placeholder: scikit-learn's RandomForest/GradientBoosting aren't
trivially explainable via their internal weights without something like
SHAP (out of scope for v1, noted in `TODO.md`), so Phase 7 ships as an
honest rule-based/statistical explanation layer instead.

### A bug found along the way

While wiring the Assistant service into `SimilarService.find_similar()`,
a real Sprint-6-era bug turned up: `/ai/rule`, `/ai/execution`,
`/ai/analyze`, and `/ai/similar` were all passing a snake_case dict
into engines that read camelCase keys (`h4Trend`, `h4PoiType`,
`m15Confirmations`, etc.), so every SMC-structure check (H4 trend, POI,
premium/discount, BOS/CHOCH, liquidity sweep) silently never matched in
these "preview" endpoints — up to 66 rule-score points and the
difference between 57% and 100% similarity, depending on the trade.
The persisted-save path was unaffected (it correctly builds its dict a
different way); only these four read-only endpoints were wrong. Fixed
via `TradeBase.to_candidate_dict()`, with two regression tests proving
the fix. See `CHANGELOG.md` `[8.0.0]` for full detail.

A second bug was found writing this sprint's own tests:
`coach_cache.invalidate(user_id)` (called after every trade write) was
a silent no-op — the cache stores tuple keys like `("deep_dive",
user_id)`, and the old `invalidate()` did an exact-match `dict.pop` on
the bare `user_id`, which never matched. `/coach/insights` and
`/coach/deep-dive` could serve up to 60 seconds of stale, pre-trade-write
data. Fixed in `app/services/cache.py`; see `CHANGELOG.md` for detail.

## Production readiness notes (post-Sprint-7 audit)

A full production-readiness audit was done after Sprint 7 shipped.
Fixed during that pass: `POST /ml/train` and `POST /ml/predict` no
longer block the event loop (CPU-bound scikit-learn work now runs via
`asyncio.to_thread`, a real fix for a measured 3.4s-per-request stall);
predicted models are cached in-process instead of being re-deserialized
from disk on every prediction; `ml_models` gained DB-level indexes plus
constraints enforcing "exactly one active model per user" and "no
duplicate version strings", closing a real race condition; a CORS
misconfiguration (`allow_credentials=True` paired with a wildcard
origin) was fixed; the Docker image now runs as a non-root user and
ships a `.dockerignore` (previously `COPY . .` would have pulled in
`.venv`, `.git`, and any local dev SQLite database into the image).
Full detail in `CHANGELOG.md`.

**Known, tracked, not yet fixed** (by design — see `TODO.md` for the
Sprint 8 roadmap):

- **No real authentication.** `X-User-Id` is a plain, unverified
  request header (`app/deps.py`) — any caller can act as any user id.
  Fine for a single-user local deployment; not safe to expose on a
  shared network until Sprint 8 ships real auth.
- **No rate limiting.** `POST /ml/train` in particular is CPU- and
  disk-expensive (writes a new persisted model file every call) and
  has no throttling — a buggy or malicious client could call it in a
  tight loop.
- **SQLite / single-process.** In-process caches (`app/services/cache.py`,
  the model cache in `ml_prediction_service.py`) aren't shared across
  multiple worker processes; fine for one `uvicorn` process, would need
  a shared cache (Redis) to scale horizontally.
