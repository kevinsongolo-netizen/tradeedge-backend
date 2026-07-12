# Handoff — TradeEdge AI Backend (Sprint 8: Assistant + Coach + Explainable AI complete)

## Current state

Sprint 8 builds three of the vision doc's phases on the existing
Sprint 6/7 stack: Phase 5 (Intelligent Trading Assistant / Pre-Trade
Analysis), Phase 6 (Personal Trading Coach deep dive), and Phase 7
(Explainable AI). Pure backend feature work — no new infrastructure,
consistent with the user's chosen scope ("Phases 5-7 ... still pure
backend work on the existing stack — no cloud, no mobile, no payments,
no computer vision").

Along the way, two real bugs pre-dating Sprint 8 were found and fixed
(not introduced by this sprint) — see below.

- **Tests**: 216 passing, 0 failing (130 Sprint 6 + 31 Sprint 7 + 5
  Sprint 7 audit + 50 Sprint 8).
- **Branch**: `sprint-8-assistant`, checked out off `sprint-7-ml`.
  `master` remains the untouched Sprint 6 baseline; `sprint-7-ml` holds
  Sprint 7 + the post-Sprint-7 audit fixes.

## What shipped this pass

### Phase 5 — Pre-Trade Analysis

`POST /api/v1/assistant/pretrade-analysis` (`app/engines/assistant_engine.py`,
`app/services/assistant_service.py`, `app/api/v1/assistant.py`): trade
quality score, win probability, AI confidence, risk level, expected RR,
historical win rate, and a Strong Buy/Buy/Wait/Avoid recommendation.
Falls back to the trade's own rule score when no ML model has ever been
trained, rather than erroring — verified live via uvicorn both before
and after training a model.

### Phase 6 — Personal Trading Coach deep dive

`GET /api/v1/coach/deep-dive` (`app/engines/coach_deep_dive_engine.py`,
extends `app/services/coach_service.py` and `app/api/v1/coach.py`):
structured answers (why losing/winning, biggest mistake, best/worst
setup, worst day, best session, pair to stop trading) built entirely
from Sprint 6's existing statistics/mistake/setup/strategy-health
engines. Verified live against seeded trade data.

### Phase 7 — Explainable AI

`explain_trade()`/`historical_reasons()` in `assistant_engine.py`,
surfaced as `strengths`/`weaknesses`/`historicalReasons` on every
pretrade-analysis response. Rule-based/statistical by design (not a
SHAP decomposition of the ML model's internals) — documented as an
honest tradeoff, not a shortcut.

### Bug fix #1 — candidate dict casing (found during Sprint 8 dev, not user-reported)

`/ai/analyze`, `/ai/rule`, `/ai/execution` (`app/api/v1/ai.py`) and
`/ai/similar` (`app/api/v1/similar.py`) were passing a snake_case dict
into engines expecting camelCase keys — every SMC-structure check (H4
trend, POI, premium/discount, BOS/CHOCH, liquidity sweep) silently
never matched. Measured impact: 66-point rule-score discrepancy (34 vs.
100) and a structurally-opposite trade scoring 100% similarity instead
of the correct 57.3%. The persisted-save path was unaffected. Fixed via
`TradeBase.to_candidate_dict()` (`app/schemas/trade.py`); two regression
tests added. Full detail: `CHANGELOG.md` `[8.0.0]`.

### Bug fix #2 — coach/stats cache invalidation was a silent no-op

`TradeService._invalidate_caches()` calls `coach_cache.invalidate(user_id)`
/ `stats_cache.invalidate(user_id)` with a bare `user_id`, but every
cache entry is keyed by a tuple (e.g. `("deep_dive", user_id)`,
`("summary", user_id)`). The old `invalidate()` did an exact-match
`dict.pop`, which never matched a tuple key — a silent no-op since
Sprint 6. `stats_cache` self-healed via its fingerprint check;
`coach_cache` (plain TTL, no fingerprint) did not — `/coach/insights`
and `/coach/deep-dive` could serve up to 60s of stale data after any
trade write. Found while writing this sprint's own tests (two tests
posting different trade data in sequence got the same cached response).
Fixed in `app/services/cache.py`; regression coverage in
`tests/services/test_cache.py`.

### Bug fix #3 — CoachDeepDive schema dropping the version field

`build_deep_dive()` returns a `version` key that `CoachDeepDive` didn't
declare, so Pydantic's `extra='ignore'` silently dropped it before the
response ever reached the client. Added `version: str` to the schema.

## Explicitly not touched this sprint (tracked, by design — see TODO.md)

- **No real authentication** — still the single biggest
  production-readiness gap (`X-User-Id` unverified header). Not in
  scope for Sprint 8 (which the user explicitly scoped to Phases 5-7,
  pure feature work, not infrastructure).
- **No rate limiting**, especially on `POST /ml/train`.
- **No retention policy** for `data/exports/`/`data/models/`.
- **Zero frontend UI** for any Sprint 7 or Sprint 8 endpoint — every
  new capability (assistant, coach deep-dive) exists in the API only.
- **Vision Phases 8-12** (Computer Vision, Advanced ML/XGBoost, Continuous
  Learning, Cloud Platform, Enterprise) — later-stage, multi-month
  efforts, not started; see `TODO.md` and `VISION.md`.

## Files touched this pass

New: `VISION.md` (the user's Project Vision doc, Phases 1-12),
`app/engines/assistant_engine.py`, `app/schemas/assistant.py`,
`app/services/assistant_service.py`, `app/api/v1/assistant.py`,
`app/engines/coach_deep_dive_engine.py`,
`tests/engines/test_assistant_engine.py`,
`tests/engines/test_coach_deep_dive_engine.py`,
`tests/api/test_assistant.py`, `tests/services/test_cache.py`.

Modified: `app/schemas/trade.py` (`to_candidate_dict()`),
`app/api/v1/ai.py` + `app/api/v1/similar.py` (candidate-dict fix),
`app/schemas/coach.py` (`DimensionStat`/`MistakeSummary`/`CoachDeepDive`
+ the `version` field fix), `app/services/coach_service.py`
(`deep_dive()`), `app/api/v1/coach.py` (`GET /coach/deep-dive`),
`app/api/router.py` (registered the assistant router),
`app/services/cache.py` (invalidation fix), `tests/api/test_ai.py`,
`tests/api/test_similar.py`, `tests/api/test_coach.py`.

No behavior of any pre-existing Sprint 6/7 endpoint changed except
where it was already wrong (the two bug fixes above) — everything else
is additive.

## Next task

Whatever the user prioritizes next from the vision doc's remaining
phases (`VISION.md`) — most likely either: (a) real authentication
(still the top production-readiness gap, tracked since the Sprint 7
audit), or (b) frontend UI for Sprint 7/8's API-only capabilities
(ML train/predict, assistant pretrade-analysis, coach deep-dive), or
(c) Vision Phase 9 (Advanced ML / XGBoost / SHAP-based explainability)
as a natural evolution of Phase 7's current rule-based explanations.
See `TODO.md` "Later" section for the full list — do not start any of
these without confirming scope with the user first, the same way
Sprint 8's scope was confirmed before building.

## Verifying this handoff

```bash
cd tradeedge-backend
git log --oneline   # latest commits: Sprint 8 tests, then Phase 5+6, then the candidate-dict fix
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
pytest -v                     # expect: 216 passed
python scripts/seed_dev.py --with-sample-trades
python scripts/train_v1.py
uvicorn app.main:app --reload
# then: curl -X POST http://127.0.0.1:8000/api/v1/assistant/pretrade-analysis -d '{"pair":"EURUSD","direction":"buy"}' -H "Content-Type: application/json"
#       curl http://127.0.0.1:8000/api/v1/coach/deep-dive
```
