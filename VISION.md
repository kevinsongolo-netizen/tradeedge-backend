# TradeEdge AI — Complete Project Vision

## Vision

TradeEdge AI is not just a trading journal.

It is an intelligent trading assistant that learns from my own trading
history, understands my strategy, identifies my strengths and
weaknesses, predicts the quality of my future trades, coaches me to
become a consistently profitable trader, and continuously improves
through Machine Learning.

The goal is not to predict the market.
The goal is to predict my own trading performance and help me make
better trading decisions.

## Phase 1 — Trading Journal

**Purpose:** Build the best trading journal possible.

**Features:** Multi-account support, Import MT5 history, Manual trade
entry, Trade editing, Notes, Rules, Checklist, Review, Screenshots,
Attachments, Search, Filters, Dashboard.

**Status:** ✅ Completed

## Phase 2 — Rule-Based AI

**Purpose:** Teach the software my trading strategy.

**Features:** Rule Engine, Execution Engine, Trade Score, Execution
Score, Overall Score, AI Coach, Similar Trades, Mistake Detection,
Strategy Health, Setup Health, Statistics, Historical Analysis.

**Status:** ✅ Completed

## Phase 3 — Backend

**Purpose:** Move everything to a professional backend.

**Technologies:** FastAPI, SQLite, SQLAlchemy, Alembic, REST API,
Repository Pattern, Testing, Logging, Documentation.

**Status:** ✅ Completed

## Phase 4 — Machine Learning

**Purpose:** Teach the AI using my own journal.

**Pipeline:** Trade → Journal → Dataset → Validation → Feature
Engineering → Training → Prediction → Feedback → Retraining

**Features:** Dataset Validation, Feature Engineering, Training
Pipeline, Prediction API, Model Comparison, Model Versioning,
Automatic Retraining.

**Status:** ✅ Completed (Version 1)

## Phase 5 — Intelligent Trading Assistant

**Purpose:** Help me BEFORE I enter a trade. Instead of only reviewing
trades after they happen, the AI becomes my trading partner.

**Features:** Pre-Trade Analysis, Trade Quality Score, Win Probability,
Confidence, Risk Level, Expected RR, Historical Win Rate, AI
Recommendation.

**Recommendation types:** Strong Buy, Buy, Wait, Avoid — each with an
explanation of WHY (strengths, weaknesses, historical reasons).

**Status:** ✅ Completed (Version 1) — `POST /api/v1/assistant/pretrade-analysis`
(`app/engines/assistant_engine.py`, Sprint 8). Degrades gracefully to a
rule-score-only estimate before a model has ever been trained (Phase 4
doesn't have to be "done" first). Explanation output is Phase 7 (below),
delivered as part of the same response.

## Phase 6 — Personal Trading Coach

**Purpose:** Discover patterns in my behavior.

**The AI should answer:** Why am I losing? Why am I winning? What is
my biggest mistake? Which setup makes me the most money? Which setup
loses the most? Which day should I avoid trading? Which session is
best? Which pair should I stop trading?

**Features:** Automatic coaching, Mistake analysis, Habit detection,
Psychology analysis, Strength analysis, Weakness analysis, Improvement
suggestions.

**Status:** ✅ Completed (Version 1) — `GET /api/v1/coach/deep-dive`
(`app/engines/coach_deep_dive_engine.py`, Sprint 8). Answers every
question listed above as a structured field, built entirely from
Sprint 6's existing statistics/mistake/setup/strategy-health engines —
no new statistical computation, just re-packaging into Q&A form.

## Phase 7 — Explainable AI

**Purpose:** Never give a prediction without explaining it.

**Example:**
```
Trade Quality: 91%
Win Probability: 84%

Reasons:
✓ Strong H4 Trend
✓ London Session
✓ High Confidence
✓ Strong Order Block
✓ BOS Confirmed

Weaknesses:
• RR slightly below average
• No Liquidity Sweep
```

**Status:** ✅ Completed (Version 1) — `explain_trade()` and
`historical_reasons()` in `app/engines/assistant_engine.py` (Sprint 8),
surfaced as `strengths`/`weaknesses`/`historicalReasons` on
`POST /assistant/pretrade-analysis`. Deliberately rule-based/statistical
rather than a SHAP-style decomposition of the ML model's internals
(scikit-learn's RandomForest/GradientBoosting aren't trivially
explainable that way without extra tooling out of scope for v1) — an
honest, documented design choice, not a shortcut.

## Phase 8 — Computer Vision

**Purpose:** Understand charts automatically.

User uploads a TradingView screenshot. AI detects: Order Blocks, FVG,
Liquidity, BOS, CHOCH, Premium, Discount, Trend, POI. Then compares
with historical trades.

**Status:** 🚧 Future

## Phase 9 — Advanced Machine Learning

**Purpose:** Continuously improve predictions.

**Models:** Logistic Regression, Random Forest, Gradient Boosting,
XGBoost, LightGBM, CatBoost, Neural Networks (future). Automatically
compare every model. Keep the best model.

**Status:** 🚧 Future

## Phase 10 — Continuous Learning

**Purpose:** The AI never stops learning.

Every new trade → Dataset updates → Model retrains → Predictions
improve → Trading improves.

**Status:** 🚧 Future

## Phase 11 — Cloud Platform

**Purpose:** Use TradeEdge everywhere.

**Features:** Login, Accounts, Cloud Database, Sync, Desktop, Android,
iPhone, Web.

**Status:** 🚧 Future

## Phase 12 — Enterprise

**Purpose:** Allow other traders to use TradeEdge AI.

**Features:** Subscriptions, Payments, Admin Dashboard, Analytics, User
Management, API Keys, Community, Shared Strategies.

**Status:** 🚧 Future

## Final Goal

TradeEdge AI should become my personal trading mentor. Before every
trade it should answer: Is this a good trade? Have I taken this setup
before? What happened last time? How similar is it? What mistakes am I
repeating? What is my probability of success? Should I take this
trade?

The AI should know my trading better than I do. It should learn from
every trade I make and become smarter over time.

The goal is not to replace me as a trader. The goal is to make me the
best trader I can become by combining disciplined journaling, data
analysis, and machine learning into one intelligent system.

## 🌟 Ultimate Vision (Version 2)

```
You upload your TradingView chart.
↓
AI automatically detects:
✓ Market Trend
✓ Order Blocks
✓ Fair Value Gaps
✓ BOS
✓ CHOCH
✓ Liquidity Sweeps
✓ Premium/Discount
✓ Market Structure
↓
AI compares the setup against every trade you've ever taken.
↓
It says:
"This setup matches 94% of your previous winning GOLD trades.
Historical win rate: 82%
Expected RR: 3.4
Confidence: High
Recommendation: TAKE"
↓
After the trade closes, the AI automatically learns from the result
and updates its knowledge.
```

Not just a trading journal or a machine learning project — a personal
AI trading coach that evolves with you over the years and becomes
uniquely tailored to your trading style.

---

*This document is the north star for TradeEdge AI. Before starting any
new sprint, check it against this vision to avoid feature creep. Update
phase statuses here as work completes.*
