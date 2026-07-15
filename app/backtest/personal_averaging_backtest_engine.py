"""Personal Averaging Strategy backtest engine (Sprint 18).

Replays ``app.chart.personal_averaging_strategy.validate_personal_averaging``
over historical Daily + M15 candle data. This strategy has NO fixed
stop loss or take profit (by the user's own design -- see that
module's docstring), so the win-rate/R-multiple model the retired
``h4_m15_backtest_engine.py`` uses doesn't apply here and would
actively mislead: by construction (rule 1 -- "never close in lost"),
every CLOSED cycle in this strategy nets to breakeven or a small
profit, so a naive win-rate would always read ~100% and hide the real
risk entirely.

The real risk in a no-stop-loss averaging strategy is TIME and
FLOATING DRAWDOWN, not win/loss ratio -- so this engine instead reports:

* how many "cycles" (one or two same-size entries, held until they
  net back to the target profit) completed vs. are still stuck open
  at the end of the data,
* how deep the floating loss went before each cycle recovered (max
  adverse excursion, in price units per unit size) -- the real
  analogue of "how close to a margin call did this get",
* how long each cycle took to resolve (in M15 bars),
* how often the 2nd, same-size add-on entry (rule 3) was actually needed.

M15 is the master clock (same convention as the retired H4->M15
engine); Daily bars are re-read fresh at each step from whichever bars
have already fully closed by that point in time, to avoid lookahead.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.chart.candle_smc_engine import MIN_CANDLES_FOR_ANALYSIS, Candle, analyze_candles
from app.chart.personal_averaging_strategy import STRATEGY_NAME, validate_personal_averaging

MIN_DAILY_CANDLES = 2
MIN_M15_CANDLES = MIN_CANDLES_FOR_ANALYSIS + 5
MAX_CANDLES_PER_SERIES = 3000
DEFAULT_LOOKBACK_DAILY = 30
DEFAULT_LOOKBACK_M15 = 100
MAX_ENTRIES_PER_CYCLE = 2  # rule 3: a first entry, plus at most one same-size add-on

DAILY_BAR_DURATION = timedelta(days=1)
M15_BAR_DURATION = timedelta(minutes=15)


def _parse_time(value: Any) -> datetime:
    s = str(value).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"Could not parse candle time '{value}' as an ISO date/time "
            "(e.g. 2024-01-01T00:00:00) -- both Daily and M15 candles need "
            "real, parseable timestamps so this backtest can line them up."
        ) from exc


def _pnl_at_price(direction: str, entries: list[tuple[float, float]], price: float) -> float:
    if direction == "buy":
        return sum(size * (price - entry) for entry, size in entries)
    return sum(size * (entry - price) for entry, size in entries)


def _exit_price_for_target(direction: str, entries: list[tuple[float, float]], target: float) -> float:
    total_size = sum(size for _, size in entries)
    weighted_entry_sum = sum(price * size for price, size in entries)
    if direction == "buy":
        return (target + weighted_entry_sum) / total_size
    return (weighted_entry_sum - target) / total_size


def run_backtest_personal_averaging(
    daily_candles: list[dict[str, Any]],
    m15_candles: list[dict[str, Any]],
    *,
    lookback_window_daily: int = DEFAULT_LOOKBACK_DAILY,
    lookback_window_m15: int = DEFAULT_LOOKBACK_M15,
    target_net_profit_per_unit: float = 0.0,
) -> dict[str, Any]:
    if len(daily_candles) < MIN_DAILY_CANDLES:
        raise ValueError(f"Need at least {MIN_DAILY_CANDLES} Daily candles for a meaningful backtest -- got {len(daily_candles)}.")
    if len(m15_candles) < MIN_M15_CANDLES:
        raise ValueError(f"Need at least {MIN_M15_CANDLES} M15 candles for a meaningful backtest -- got {len(m15_candles)}.")
    if len(daily_candles) > MAX_CANDLES_PER_SERIES or len(m15_candles) > MAX_CANDLES_PER_SERIES:
        raise ValueError(f"Too many candles -- max {MAX_CANDLES_PER_SERIES} per series per backtest run.")
    if lookback_window_m15 < MIN_CANDLES_FOR_ANALYSIS:
        raise ValueError(f"M15 lookback window must be at least {MIN_CANDLES_FOR_ANALYSIS}.")

    daily_sorted = sorted(daily_candles, key=lambda c: _parse_time(c["time"]))
    m15_sorted = sorted(m15_candles, key=lambda c: _parse_time(c["time"]))
    daily_close_times = [_parse_time(c["time"]) + DAILY_BAR_DURATION for c in daily_sorted]
    m15_close_times = [_parse_time(c["time"]) + M15_BAR_DURATION for c in m15_sorted]

    cycles: list[dict[str, Any]] = []
    n = len(m15_sorted)
    daily_cursor = 0
    active: dict[str, Any] | None = None  # direction, entries=[(price,size,idx,time)], mae, last_entry_index

    i = MIN_CANDLES_FOR_ANALYSIS - 1
    while i < n:
        bar = m15_sorted[i]
        m15_now = m15_close_times[i]

        # -- 1. Exit check for an already-open cycle, using THIS bar's
        # range -- but never on the same bar an entry was just placed
        # (that would be lookahead: we can't know a bar's own high/low
        # relative to a fill established at that bar's open until
        # after the fact in a real trade, so the first bar eligible to
        # exit is the one AFTER the most recent entry).
        if active is not None and i > active["last_entry_index"]:
            direction = active["direction"]
            entries = [(p, s) for p, s, _, _ in active["entries"]]
            best_price = bar["high"] if direction == "buy" else bar["low"]
            worst_price = bar["low"] if direction == "buy" else bar["high"]
            best_pnl = _pnl_at_price(direction, entries, best_price)
            worst_pnl = _pnl_at_price(direction, entries, worst_price)
            active["mae"] = min(active["mae"], worst_pnl)

            if best_pnl >= target_net_profit_per_unit:
                exit_price = _exit_price_for_target(direction, entries, target_net_profit_per_unit)
                lo, hi = min(bar["low"], bar["high"]), max(bar["low"], bar["high"])
                exit_price = min(max(exit_price, lo), hi)
                net_pnl = _pnl_at_price(direction, entries, exit_price)
                cycles.append(
                    {
                        "direction": direction,
                        "entries": [{"price": p, "time": t} for p, _, _, t in active["entries"]],
                        "add_on_used": len(active["entries"]) > 1,
                        "exit_time": bar["time"],
                        "exit_price": exit_price,
                        "net_pnl_per_unit": round(net_pnl, 6),
                        "max_adverse_excursion": round(active["mae"], 6),
                        "bars_held": i - active["entries"][0][2],
                        "outcome": "CLOSED",
                    }
                )
                active = None

        # -- 2. Signal check: only meaningful if there's a next bar to
        # actually place a fill on (no lookahead -- entries always fill
        # at the NEXT bar's open, never the signal bar's own price).
        if i + 1 < n:
            while daily_cursor < len(daily_sorted) and daily_close_times[daily_cursor] <= m15_now:
                daily_cursor += 1

            if daily_cursor >= 1:
                daily_window = daily_sorted[max(0, daily_cursor - lookback_window_daily) : daily_cursor]
                m15_window = m15_sorted[max(0, i + 1 - lookback_window_m15) : i + 1]

                try:
                    daily_smc_candles = [Candle(**c) for c in daily_window]
                    m15_smc = analyze_candles(m15_window)
                except ValueError:
                    daily_smc_candles, m15_smc = None, None

                if daily_smc_candles is not None and m15_smc is not None:
                    open_trade_in_loss = False
                    if active is not None:
                        entries = [(p, s) for p, s, _, _ in active["entries"]]
                        pnl_now = _pnl_at_price(active["direction"], entries, bar["close"])
                        open_trade_in_loss = pnl_now < 0

                    validation = validate_personal_averaging(daily_smc_candles, m15_smc, open_trade_in_loss=open_trade_in_loss)

                    entry_index = i + 1
                    entry_candle = m15_sorted[entry_index]

                    if active is None and validation["tradeStatus"] == "VALID" and validation["recommendation"] == "TAKE":
                        active = {
                            "direction": validation["direction"],
                            "entries": [(entry_candle["open"], 1.0, entry_index, entry_candle["time"])],
                            "mae": 0.0,
                            "last_entry_index": entry_index,
                        }
                    elif (
                        active is not None
                        and len(active["entries"]) < MAX_ENTRIES_PER_CYCLE
                        and open_trade_in_loss
                        and validation["tradeStatus"] == "VALID"
                        and validation["recommendation"] == "ADD"
                        and validation["direction"] == active["direction"]
                    ):
                        active["entries"].append((entry_candle["open"], 1.0, entry_index, entry_candle["time"]))
                        active["last_entry_index"] = entry_index

        i += 1

    if active is not None:
        entries = [(p, s) for p, s, _, _ in active["entries"]]
        last_close = m15_sorted[-1]["close"]
        net_pnl = _pnl_at_price(active["direction"], entries, last_close)
        cycles.append(
            {
                "direction": active["direction"],
                "entries": [{"price": p, "time": t} for p, _, _, t in active["entries"]],
                "add_on_used": len(active["entries"]) > 1,
                "exit_time": None,
                "exit_price": None,
                "net_pnl_per_unit": round(net_pnl, 6),
                "max_adverse_excursion": round(active["mae"], 6),
                "bars_held": (n - 1) - active["entries"][0][2],
                "outcome": "OPEN",
            }
        )

    closed = [c for c in cycles if c["outcome"] == "CLOSED"]
    still_open = [c for c in cycles if c["outcome"] == "OPEN"]
    add_on_used_count = sum(1 for c in cycles if c["add_on_used"])
    add_on_rate_pct = round((add_on_used_count / len(cycles)) * 100, 1) if cycles else 0.0
    avg_bars_held = round(sum(c["bars_held"] for c in closed) / len(closed), 1) if closed else None
    worst_mae = round(min((c["max_adverse_excursion"] for c in cycles), default=0.0), 6) if cycles else None

    notes: list[str] = [
        "This strategy has no fixed stop loss or take profit by design (rule 1: "
        "\"never close in lost\") -- every CLOSED cycle below nets to breakeven or "
        "a small profit, so win rate is not a meaningful risk measure here. Look at "
        "\"max adverse excursion\" (how deep the floating loss went before recovering) "
        "and \"cycles still open\" (never recovered within this data) for the real risk picture."
    ]
    if not cycles:
        notes.append("No cycles were opened within this candle range -- try more data, or wider lookback windows.")
    if still_open:
        notes.append(
            f"{len(still_open)} cycle(s) never recovered to breakeven within this data -- "
            "in live trading that's exactly the scenario the margin buffer warning exists for."
        )

    return {
        "strategy": STRATEGY_NAME,
        "total_trades": len(closed),
        "wins": len(closed),  # by design: every CLOSED cycle is breakeven-or-better
        "losses": 0,
        "open_trades": len(still_open),
        "win_rate": 100.0 if closed else 0.0,
        "total_r_multiple": 0.0,
        "average_r_multiple": 0.0,
        "profit_factor": None,
        "trades": [],  # not applicable -- see cycles_detail
        "notes": notes,
        "cycles_total": len(cycles),
        "cycles_closed": len(closed),
        "cycles_open": len(still_open),
        "add_on_rate_pct": add_on_rate_pct,
        "avg_bars_held": avg_bars_held,
        "max_adverse_excursion": worst_mae,
        "cycles_detail": cycles,
    }
