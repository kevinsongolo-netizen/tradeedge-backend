"""Chart Analysis Engine (Sprint 10).

Three-level Smart Money Concepts (SMC) analysis, built from two
independent "Level 1" reading paths that both feed the same Level 2
(trade validation) and Level 3 (AI coach explanation) logic:

* ``candle_smc_engine`` — deterministic, math-based SMC detection from
  real OHLC candle data (trend, swing highs/lows, BOS, CHOCH, order
  blocks, FVGs, equal-highs/lows liquidity, premium/discount). Precise
  and provably correct from real numbers.
* ``vision_provider`` — a pluggable interface for reading a chart
  *screenshot* with a vision-capable AI model. Ships with a clearly
  labeled placeholder implementation until a real vision API key is
  configured; swapping in a real provider (Anthropic, OpenAI, ...)
  requires no changes to any other module.

Both paths produce the same ``ChartAnalysis`` shape (see
``app.schemas.chart``), so ``trade_validator`` (Level 2) and
``coach_explainer`` (Level 3) don't know or care which path produced
it — this is the seam that keeps future expansion (MT5 live feed,
TradingView, multi-timeframe, ...) additive rather than a refactor.
"""
