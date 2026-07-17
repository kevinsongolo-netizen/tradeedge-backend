"""Backtesting engine (Sprint 13). Pure function, no I/O — see
``app/backtest/__init__.py`` for the architecture note.
"""
from __future__ import annotations

from typing import Any

from app.chart import normalize
from app.chart.candle_smc_engine import MIN_CANDLES_FOR_ANALYSIS, analyze_candles
from app._legacy.chart.trade_validator import validate_trade
from app.schemas.chart import ChartAnalysis

MIN_TOTAL_CANDLES = MIN_CANDLES_FOR_ANALYSIS + 5
MAX_TOTAL_CANDLES = 2000
DEFAULT_LOOKBACK_WINDOW = 100


def _simulate_trade_outcome(
    candles: list[dict[str, Any]],
    entry_index: int,
    direction: str,
    stop_loss: float,
    take_profit: float,
) -> dict[str, Any]:
    """Walks forward from ``entry_index + 1`` checking whether SL or
    TP is hit first. If a single candle's range covers both, SL is
    assumed hit first — a conservative simplification, since intra-
    candle sequencing isn't knowable from OHLC data alone."""
    for j in range(entry_index + 1, len(candles)):
        c = candles[j]
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


def run_backtest(
    candles: list[dict[str, Any]],
    *,
    lookback_window: int = DEFAULT_LOOKBACK_WINDOW,
    min_rr: float = 2.0,
    direction: str | None = None,
) -> dict[str, Any]:
    if len(candles) < MIN_TOTAL_CANDLES:
        raise ValueError(
            f"Need at least {MIN_TOTAL_CANDLES} candles to run a meaningful backtest — got {len(candles)}."
        )
    if len(candles) > MAX_TOTAL_CANDLES:
        raise ValueError(f"Too many candles — max {MAX_TOTAL_CANDLES} per backtest run.")
    if lookback_window < MIN_CANDLES_FOR_ANALYSIS:
        raise ValueError(f"lookback_window must be at least {MIN_CANDLES_FOR_ANALYSIS}.")

    trades: list[dict[str, Any]] = []
    i = MIN_CANDLES_FOR_ANALYSIS - 1
    n = len(candles)

    while i < n - 1:  # need at least one candle after i to enter on
        window_start = max(0, i + 1 - lookback_window)
        window = candles[window_start : i + 1]
        try:
            smc = analyze_candles(window)
        except ValueError:
            i += 1
            continue

        analysis_dict = normalize.from_candle_analysis(smc)
        analysis = ChartAnalysis(**analysis_dict)
        validation = validate_trade(analysis, direction=direction, min_rr=min_rr)

        if (
            validation["tradeStatus"] == "VALID"
            and validation["suggestedEntry"] is not None
            and validation["stopLoss"] is not None
            and validation["takeProfit"] is not None
        ):
            entry_index = i + 1  # enter at next candle's open — no lookahead
            entry_candle = candles[entry_index]
            resolved_direction = validation["direction"]
            entry = entry_candle["open"]

            # Preserve the suggested risk distance and reward distance,
            # re-anchored to the *actual* fill price (the next candle's
            # real open) rather than the analysis's theoretical midpoint
            # entry — a more realistic simulated fill.
            risk = abs(validation["suggestedEntry"] - validation["stopLoss"])
            reward = abs(validation["takeProfit"] - validation["suggestedEntry"])
            if resolved_direction == "buy":
                stop_loss = entry - risk
                take_profit = entry + reward
            else:
                stop_loss = entry + risk
                take_profit = entry - reward

            outcome = _simulate_trade_outcome(candles, entry_index, resolved_direction, stop_loss, take_profit)
            r_multiple = None
            if outcome["outcome"] == "WIN":
                r_multiple = (reward / risk) if risk else None
            elif outcome["outcome"] == "LOSS":
                r_multiple = -1.0

            trades.append(
                {
                    "entry_index": entry_index,
                    "entry_time": entry_candle["time"],
                    "direction": resolved_direction,
                    "entry": entry,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "exit_time": outcome["exit_time"],
                    "exit_price": outcome["exit_price"],
                    "outcome": outcome["outcome"],
                    "r_multiple": r_multiple,
                }
            )
            # One trade open at a time — matches how a single trader
            # would actually operate. Resume scanning from the exit.
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
            "No trades were both taken and resolved within this candle range — "
            "try more data or a wider lookback window."
        )
    if open_trades:
        notes.append(f"{len(open_trades)} trade(s) were still open at the end of the data (excluded from win rate).")
    if closed_trades and gross_loss_r == 0:
        notes.append("No losing trades in this sample — profit factor is undefined (shown as null), not infinite.")

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
