"""H4 -> M15 dual-timeframe backtesting engine (v2 -- replays the
user's own H4->M15 Point-of-Interest strategy, not the Classic Bias
one the original single-timeframe ``backtest_engine.py`` still
replays; that module is kept fully intact and untouched for later
reuse -- see its own docstring).

Unlike the original engine (one candle series, one lookback window),
this one keeps TWO clocks in sync: the H4 series (the higher-timeframe
POI context) and the M15 series (the actual touch/entry trigger, and
the resolution used to simulate exits). M15 is walked bar-by-bar as
the "master clock" -- exactly how a trader actually watches the
market -- with the H4 context re-read fresh at each step from whichever
H4 bars have already FULLY CLOSED by that point in time, to avoid any
lookahead into H4 price action that hasn't happened yet.

Assumptions (stated explicitly since they matter for correctness):
* Each candle's ``time`` is its OPEN/start timestamp (not its close),
  matching how the rest of the app already treats candle data.
* H4 bars are exactly 4 hours long, M15 bars exactly 15 minutes --
  true by definition for these two timeframes.
* Both candle series need real, parseable ISO date/time strings (e.g.
  ``2024-01-01T00:00:00``) so the two series can be aligned -- unlike
  the single-timeframe engine, this one can't treat ``time`` as an
  opaque label, since it has to know which H4 bar was "current" at any
  given M15 moment.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.chart.candle_smc_engine import MIN_CANDLES_FOR_ANALYSIS, analyze_candles
from app._legacy.chart.htf_ltf_ob_strategy import validate_h4_m15_ob

MIN_H4_CANDLES = MIN_CANDLES_FOR_ANALYSIS
MIN_M15_CANDLES = MIN_CANDLES_FOR_ANALYSIS + 5
MAX_CANDLES_PER_SERIES = 3000
DEFAULT_LOOKBACK_H4 = 100
DEFAULT_LOOKBACK_M15 = 100

H4_BAR_DURATION = timedelta(hours=4)
M15_BAR_DURATION = timedelta(minutes=15)


def _parse_time(value: Any) -> datetime:
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Could not parse candle time '{value}' as an ISO date/time "
            "(e.g. 2024-01-01T00:00:00) -- both H4 and M15 candles need "
            "real, parseable timestamps so this backtest can line them up."
        ) from exc


def _simulate_exit(
    m15_candles: list[dict[str, Any]], entry_index: int, direction: str, stop_loss: float, take_profit: float
) -> dict[str, Any]:
    """Same conservative simplification as the original engine: if a
    single M15 candle's range covers both SL and TP, SL is assumed hit
    first (intra-candle sequencing isn't knowable from OHLC alone)."""
    for j in range(entry_index + 1, len(m15_candles)):
        c = m15_candles[j]
        high, low = c["high"], c["low"]
        if direction == "buy":
            hit_sl = low <= stop_loss
            hit_tp = high >= take_profit
        else:
            hit_sl = high >= stop_loss
            hit_tp = low <= take_profit
        if hit_sl:
            return {"outcome": "LOSS", "exit_index": j, "exit_time": c["time"], "exit_price": stop_loss}
        if hit_tp:
            return {"outcome": "WIN", "exit_index": j, "exit_time": c["time"], "exit_price": take_profit}
    return {"outcome": "OPEN", "exit_index": None, "exit_time": None, "exit_price": None}


def run_backtest_h4_m15(
    h4_candles: list[dict[str, Any]],
    m15_candles: list[dict[str, Any]],
    *,
    lookback_window_h4: int = DEFAULT_LOOKBACK_H4,
    lookback_window_m15: int = DEFAULT_LOOKBACK_M15,
) -> dict[str, Any]:
    if len(h4_candles) < MIN_H4_CANDLES:
        raise ValueError(f"Need at least {MIN_H4_CANDLES} H4 candles for a meaningful backtest -- got {len(h4_candles)}.")
    if len(m15_candles) < MIN_M15_CANDLES:
        raise ValueError(f"Need at least {MIN_M15_CANDLES} M15 candles for a meaningful backtest -- got {len(m15_candles)}.")
    if len(h4_candles) > MAX_CANDLES_PER_SERIES or len(m15_candles) > MAX_CANDLES_PER_SERIES:
        raise ValueError(f"Too many candles -- max {MAX_CANDLES_PER_SERIES} per series per backtest run.")
    if lookback_window_h4 < MIN_CANDLES_FOR_ANALYSIS or lookback_window_m15 < MIN_CANDLES_FOR_ANALYSIS:
        raise ValueError(f"Lookback windows must be at least {MIN_CANDLES_FOR_ANALYSIS}.")

    h4_sorted = sorted(h4_candles, key=lambda c: _parse_time(c["time"]))
    m15_sorted = sorted(m15_candles, key=lambda c: _parse_time(c["time"]))
    h4_close_times = [_parse_time(c["time"]) + H4_BAR_DURATION for c in h4_sorted]
    m15_close_times = [_parse_time(c["time"]) + M15_BAR_DURATION for c in m15_sorted]

    trades: list[dict[str, Any]] = []
    n = len(m15_sorted)
    i = MIN_CANDLES_FOR_ANALYSIS - 1
    h4_cursor = 0  # count of H4 bars fully closed so far

    while i < n - 1:  # need at least one M15 candle after i to enter on
        m15_now = m15_close_times[i]  # this M15 bar is only "known" once IT closes

        # Advance to every H4 bar that has fully closed by that same
        # moment -- never use an H4 bar before its own close time.
        while h4_cursor < len(h4_sorted) and h4_close_times[h4_cursor] <= m15_now:
            h4_cursor += 1

        if h4_cursor < MIN_CANDLES_FOR_ANALYSIS:
            i += 1
            continue  # not enough closed H4 history yet at this point in time

        h4_window = h4_sorted[max(0, h4_cursor - lookback_window_h4) : h4_cursor]
        m15_window = m15_sorted[max(0, i + 1 - lookback_window_m15) : i + 1]

        try:
            h4_smc = analyze_candles(h4_window)
            m15_smc = analyze_candles(m15_window)
        except ValueError:
            i += 1
            continue

        validation = validate_h4_m15_ob(h4_smc, m15_smc)

        if (
            validation["tradeStatus"] == "VALID"
            and validation["suggestedEntry"] is not None
            and validation["stopLoss"] is not None
            and validation["takeProfit"] is not None
        ):
            entry_index = i + 1  # enter at next M15 candle's open -- no lookahead
            entry_candle = m15_sorted[entry_index]
            direction = validation["direction"]
            entry = entry_candle["open"]

            # Preserve the suggested risk/reward distances, re-anchored
            # to the actual fill price rather than the theoretical
            # midpoint entry -- a more realistic simulated fill.
            risk = abs(validation["suggestedEntry"] - validation["stopLoss"])
            reward = abs(validation["takeProfit"] - validation["suggestedEntry"])
            if direction == "buy":
                stop_loss = entry - risk
                take_profit = entry + reward
            else:
                stop_loss = entry + risk
                take_profit = entry - reward

            outcome = _simulate_exit(m15_sorted, entry_index, direction, stop_loss, take_profit)
            r_multiple = None
            if outcome["outcome"] == "WIN":
                r_multiple = (reward / risk) if risk else None
            elif outcome["outcome"] == "LOSS":
                r_multiple = -1.0

            trades.append(
                {
                    "entry_index": entry_index,
                    "entry_time": entry_candle["time"],
                    "direction": direction,
                    "entry": entry,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "exit_time": outcome["exit_time"],
                    "exit_price": outcome["exit_price"],
                    "outcome": outcome["outcome"],
                    "r_multiple": r_multiple,
                }
            )
            # One trade open at a time -- resume scanning from the exit.
            i = outcome["exit_index"] if outcome["exit_index"] is not None else n
            continue

        i += 1

    closed_trades = [t for t in trades if t["outcome"] in ("WIN", "LOSS")]
    wins = [t for t in closed_trades if t["outcome"] == "WIN"]
    losses = [t for t in closed_trades if t["outcome"] == "LOSS"]
    open_trades = [t for t in trades if t["outcome"] == "OPEN"]

    total_closed = len(closed_trades)
    win_rate = round((len(wins) / total_closed) * 100, 1) if total_closed else 0.0
    total_r = sum(t["r_multiple"] for t in closed_trades if t["r_multiple"] is not None)
    average_r = round(total_r / total_closed, 2) if total_closed else 0.0
    gross_win_r = sum(t["r_multiple"] for t in wins if t["r_multiple"] is not None)
    gross_loss_r = abs(sum(t["r_multiple"] for t in losses if t["r_multiple"] is not None))
    profit_factor = round(gross_win_r / gross_loss_r, 2) if gross_loss_r > 0 else None

    notes: list[str] = []
    if not closed_trades:
        notes.append(
            "No trades were both taken and resolved within this candle range -- "
            "try more data, or wider lookback windows."
        )
    if open_trades:
        notes.append(f"{len(open_trades)} trade(s) were still open at the end of the data (excluded from win rate).")
    if closed_trades and gross_loss_r == 0:
        notes.append("No losing trades in this sample -- profit factor is undefined (shown as null), not infinite.")

    return {
        "total_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "open_trades": len(open_trades),
        "win_rate": win_rate,
        "total_r_multiple": round(total_r, 2),
        "average_r_multiple": average_r,
        "profit_factor": profit_factor,
        "trades": trades,
        "notes": notes,
    }
