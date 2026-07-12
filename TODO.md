# TODO — TradeEdge AI Backend

Tracks build progress against the Sprint 6 Architecture Specification.

## Done (Sprint 6)

- [x] DB layer — async SQLAlchemy models (User, Trade, AIAnalysis,
      ScoringWeights, MLExport/MLModel), repository pattern, Alembic
      `0001_initial` migration (seeds `users(id=1)`), `scripts/seed_dev.py`
- [x] Pydantic v2 schema layer (`app/schemas/*`) — camelCase over the
      wire via `CamelModel`, plain snake_case `MlRow` for the ML contract
- [x] All 9 JS engines ported to Python (`app/engines/*`), behavior
      preserved and covered by unit tests
- [x] Services layer (`app/services/*`) — transactions, caching
      (`FingerprintCache`, TTL cache), orchestration
- [x] API routers — trades (full CRUD + bulk upsert), ai (analyze/rule/
      execution/weights/similar), stats (summary/charts/strategy-health/
      setups/mistakes), coach (insights), ml (dataset/validate/exports),
      health (healthz/readyz/version) — 24 endpoints total
- [x] Frontend integration — `js/api_client.js` added, `js/ai_dashboard.js`
      reduced to UI orchestration, `index.html` call sites converted to
      async/await, old engine JS files retired
- [x] Tests — 130 passing (61 engine, 20 repository, 49 API), 0 failures
- [x] Documentation — README, CHANGELOG, TODO, HANDOFF (this pass)

## Done (Sprint 7 — Machine Learning v1)

- [x] Phase 1 — dataset validation report (`app/ml/dataset_validation.py`,
      `GET /ml/dataset/validation-report`)
- [x] Phase 2 — feature engineering pipeline (`app/ml/features.py`),
      including the new `hist_strategy_health_score` feature
- [x] Phase 3/4 — train/val/test split + Logistic Regression / Random
      Forest / Gradient Boosting comparison + auto-selection
      (`app/ml/train.py`)
- [x] Phase 5 — prediction API (`POST /ml/predict`, win probability +
      quality score/bucket, using the user's real trade history for
      rolling features)
- [x] Phase 6 — joblib persistence + versioning (`app/ml/persistence.py`,
      `ml_models` table, `POST /ml/train` / `GET /ml/models*`)
- [x] Phase 7 — docs (this pass) + `scripts/train_v1.py` CLI
- [x] 31 new tests, 161 total passing (audit pass added 5 more -> 166; see below)

## Done (post-Sprint-7 production readiness audit)

- [x] Fixed: training/prediction blocking the event loop (`asyncio.to_thread`)
- [x] Fixed: model reloaded from disk on every prediction (in-process cache)
- [x] Fixed: no DB-level "one active model per user" / unique-version
      guarantee (migration `0002_ml_models_indexes` + matching
      `__table_args__`)
- [x] Fixed: `add_hist_strategy_health()` mutated caller data
- [x] Fixed: duplicated quality-bucket thresholds (now reuses Sprint 6's)
- [x] Fixed: CORS `allow_credentials=True` + wildcard origin
- [x] Fixed: Docker ran as root, no `.dockerignore`
- [x] 5 new regression tests, 166 total passing

## Done (Sprint 8 — Intelligent Trading Assistant, Coach, Explainable AI)

- [x] Phase 5 — Pre-Trade Analysis (`app/engines/assistant_engine.py`,
      `POST /api/v1/assistant/pretrade-analysis`) — quality score, win
      probability, AI confidence, risk level, expected RR, historical
      win rate, Strong Buy/Buy/Wait/Avoid recommendation. Degrades
      gracefully before any model is trained.
- [x] Phase 6 — Personal Trading Coach deep dive
      (`app/engines/coach_deep_dive_engine.py`,
      `GET /api/v1/coach/deep-dive`) — why losing/winning, biggest
      mistake, best/worst setup, worst day, best session, pair to stop
      trading. Re-packages Sprint 6's existing stats/setup/mistake/
      health engines, no new statistical computation.
- [x] Phase 7 — Explainable AI (`explain_trade()`/`historical_reasons()`
      in `assistant_engine.py`) — strengths/weaknesses/historical
      reasons on every pretrade-analysis response. Rule-based/
      statistical by design, not a SHAP decomposition of the ML model.
- [x] Found + fixed: `/ai/analyze`, `/ai/rule`, `/ai/execution`,
      `/ai/similar` were silently ignoring every SMC-structure field
      (snake_case/camelCase candidate-dict mismatch) — see CHANGELOG
      `[8.0.0]` for measured impact and the fix
      (`TradeBase.to_candidate_dict()`).
- [x] Found + fixed: `coach_cache`/`stats_cache` `invalidate(user_id)`
      was a silent no-op (tuple-keyed cache, bare-user_id pop never
      matched) — `/coach/insights`/`/coach/deep-dive` could serve up to
      60s of stale data after a trade write. Fixed in
      `app/services/cache.py`.
- [x] Found + fixed: `CoachDeepDive` schema was missing the `version`
      field the engine already returned (silently dropped by Pydantic).
- [x] 50 new tests, 216 total passing, 0 failures.

## Next (post-v1 ML improvements)

- [ ] Periodic/automatic retraining trigger (e.g. every N new trades,
      or a scheduled job) — v1 is on-demand only (`POST /ml/train`)
- [ ] Track prediction accuracy over time (log each `/ml/predict` call
      against the eventual real outcome once the trade closes, to
      measure real-world calibration, not just held-out test metrics)
- [ ] Consider a regression target (predicted PnL/R-multiple) alongside
      the current binary win/loss classifier
- [ ] Model comparison/rollback UI (list versions is already there via
      `GET /ml/models`; no endpoint yet to reactivate an older version)
- [ ] Cross-validation instead of a single train/val split for model
      selection, once dataset sizes are large enough to afford it

## Later (noted in the architecture spec / vision doc, out of scope so far)

- [ ] Real auth (JWT via `SECRET_KEY`, currently a single-user
      `DEFAULT_USER_ID = 1` stand-in in `app/deps.py`; the Sprint 7
      audit confirmed this is the single biggest production-readiness
      gap — anyone can act as any user id via the `X-User-Id` header).
      Not part of Sprint 8 (which covered vision Phases 5-7, all pure
      backend feature work, not infrastructure).
- [ ] Rate limiting / request throttling, especially on `POST /ml/train`
      (CPU + disk cost per call, currently uncapped) — found in the audit
- [ ] Retention/cleanup policy for `data/exports/` and `data/models/` —
      both grow forever with no pruning of old versions — found in the audit
- [ ] PostgreSQL in production (`DATABASE_URL` swap only — no code
      changes anticipated, but not yet verified against real Postgres)
- [ ] Verify the full test suite on Python 3.12+ (only 3.10 was
      available in the build sandbox — see CHANGELOG "Known deviations")
- [ ] Frontend UI for the Sprint 7 ML endpoints (train/predict/validation
      report) — the capability exists in the API only; found in the audit
- [ ] Frontend UI for Sprint 8's Assistant/Coach endpoints
      (pretrade-analysis, coach deep-dive) — API only so far
- [ ] Vision Phase 8 — Computer Vision (chart-upload analysis): a
      multi-month effort (image pipeline, OCR/CV model, new infra);
      explicitly out of scope until the user chooses to prioritize it
- [ ] Vision Phase 9 — Advanced ML (XGBoost/LightGBM/CatBoost, feature
      importance/SHAP-based explainability) — natural next step after
      Phase 7's rule-based explanations, if/when justified by more data
- [ ] Vision Phases 10-12 — Continuous Learning, Cloud Platform,
      Enterprise — later-stage, multi-month efforts per the vision doc,
      not started

## Known environment note

This project was built and tested in a sandbox with only Python 3.10
available (spec called for 3.12+). All 216 tests pass on 3.10 (130 from
Sprint 6 + 31 from Sprint 7 + 5 from the post-Sprint-7 audit + 50 from
Sprint 8). No 3.11/3.12-only syntax is used, so 3.12+ is expected to
work unchanged — recommend confirming with one full `pytest -v` run
before relying on it.
