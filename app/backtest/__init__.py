"""Backtesting engine (Sprint 13 — Backtesting).

Replays the existing deterministic SMC engine + Level 2 trade
validator (``app/chart/candle_smc_engine.py``, ``app/chart/
trade_validator.py``) candle-by-candle over historical OHLC data,
exactly as a trader would see it forming in real time — no lookahead.
This tests the *existing rules*, not a learned model; there is no
machine learning here (see the ML confidence model roadmap item for
that, which needs far more labeled trade history than exists yet).
"""
