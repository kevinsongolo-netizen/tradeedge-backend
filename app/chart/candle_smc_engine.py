"""Deterministic Smart Money Concepts (SMC) detection from real OHLC
candle data (Chart Analysis Engine — Level 1, "price data" path).

Every function here is a pure function of a candle list — no I/O, no
randomness, no AI calls. Given the same candles, the output is always
identical, which is what makes this path more reliable than reading a
screenshot: a swing high either is or isn't higher than its neighbours,
there's no "estimating" involved.

Terminology (fractal/ICT-style, matching the rest of the app's SMC
vocabulary already used in ``app/engines/rule_engine.py`` etc.):

* Swing high/low — a local extreme confirmed by ``fractal_n`` candles
  on each side (default 2, i.e. a standard 5-candle fractal).
* Trend — inferred from the sequence of the last few confirmed swings:
  higher highs + higher lows = Bullish, lower highs + lower lows =
  Bearish, anything mixed = Ranging.
* BOS (Break of Structure) — a close beyond the most recent swing
  high/low *in the direction of the prevailing trend* (continuation).
* CHOCH (Change of Character) — the first close beyond a swing point
  *against* the prevailing trend (early reversal signal).
* Order block — the last opposite-colored candle immediately before
  the impulsive move that produced a BOS/CHOCH.
* FVG (Fair Value Gap) — a 3-candle imbalance: candle[i-1].high <
  candle[i+1].low (bullish gap) or candle[i-1].low > candle[i+1].high
  (bearish gap).
* Equal highs/lows — two or more swing points within ``eq_tolerance_pct``
  of each other, read as resting liquidity.
* Premium/Discount — where current price sits within the most recent
  swing-low..swing-high range (below the 50% midpoint = Discount,
  above = Premium).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candle:
    """One OHLC bar. ``time`` is any opaque label (ISO string, index,
    epoch, ...) — this engine never parses or compares it, only echoes
    it back in output for the caller's own display/sorting."""

    time: str
    open: float
    high: float
    low: float
    close: float

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open


@dataclass
class SwingPoint:
    index: int
    time: str
    price: float
    kind: str  # "high" | "low"


@dataclass
class OrderBlock:
    index: int
    time: str
    kind: str  # "bullish" | "bearish"
    high: float
    low: float
    mitigated: bool = False


@dataclass
class FairValueGap:
    start_index: int
    end_index: int
    kind: str  # "bullish" | "bearish"
    top: float
    bottom: float
    mitigated: bool = False


@dataclass
class StructureEvent:
    index: int
    time: str
    kind: str  # "BOS" | "CHOCH"
    direction: str  # "bullish" | "bearish"


@dataclass
class SmcAnalysis:
    trend: str  # "Bullish" | "Bearish" | "Ranging"
    structure: str  # same vocabulary as trend, for the "Market Structure" field
    current_price: float
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fair_value_gaps: list[FairValueGap] = field(default_factory=list)
    structure_events: list[StructureEvent] = field(default_factory=list)
    equal_highs: list[list[SwingPoint]] = field(default_factory=list)
    equal_lows: list[list[SwingPoint]] = field(default_factory=list)
    premium_discount: str = "Equilibrium"  # "Premium" | "Discount" | "Equilibrium"
    price_in_order_block: OrderBlock | None = None
    latest_event: StructureEvent | None = None
    nearest_unmitigated_ob_bullish: OrderBlock | None = None
    nearest_unmitigated_ob_bearish: OrderBlock | None = None
    nearest_unmitigated_fvg_bullish: FairValueGap | None = None
    nearest_unmitigated_fvg_bearish: FairValueGap | None = None
    bias: str = "NONE"  # "BUY" | "SELL" | "NONE"


MIN_CANDLES_FOR_ANALYSIS = 10


def find_swing_points(candles: list[Candle], fractal_n: int = 2) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Standard fractal swing detection: candle[i] is a swing high if
    its high is strictly greater than the ``fractal_n`` candles on
    each side (swing low is the mirror image on lows)."""
    highs: list[SwingPoint] = []
    lows: list[SwingPoint] = []
    n = len(candles)
    for i in range(fractal_n, n - fractal_n):
        window = candles[i - fractal_n : i + fractal_n + 1]
        c = candles[i]
        if c.high == max(w.high for w in window) and list(w.high for w in window).count(c.high) == 1:
            highs.append(SwingPoint(index=i, time=c.time, price=c.high, kind="high"))
        if c.low == min(w.low for w in window) and list(w.low for w in window).count(c.low) == 1:
            lows.append(SwingPoint(index=i, time=c.time, price=c.low, kind="low"))
    return highs, lows


def infer_trend(swing_highs: list[SwingPoint], swing_lows: list[SwingPoint]) -> str:
    """Higher highs + higher lows (last two of each) = Bullish; lower
    highs + lower lows = Bearish; anything else (including too little
    data) = Ranging. Deliberately conservative — "Ranging" is the safe
    default when the evidence doesn't clearly point one way."""
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "Ranging"
    higher_highs = swing_highs[-1].price > swing_highs[-2].price
    higher_lows = swing_lows[-1].price > swing_lows[-2].price
    lower_highs = swing_highs[-1].price < swing_highs[-2].price
    lower_lows = swing_lows[-1].price < swing_lows[-2].price
    if higher_highs and higher_lows:
        return "Bullish"
    if lower_highs and lower_lows:
        return "Bearish"
    return "Ranging"


def find_structure_events(
    candles: list[Candle],
    swing_highs: list[SwingPoint],
    swing_lows: list[SwingPoint],
    trend: str,
) -> list[StructureEvent]:
    """Walks forward through candles; whenever a close breaks the most
    recently confirmed swing high/low, that's a structural break. It's
    a BOS if the break direction matches ``trend`` (continuation), a
    CHOCH if it's the opposite (early reversal signal)."""
    events: list[StructureEvent] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    high_iter = iter(swing_highs)
    low_iter = iter(swing_lows)
    next_high = next(high_iter, None)
    next_low = next(low_iter, None)

    for i, c in enumerate(candles):
        # Advance to the most recent *confirmed* swing before this candle.
        while next_high is not None and next_high.index < i:
            last_high = next_high
            next_high = next(high_iter, None)
        while next_low is not None and next_low.index < i:
            last_low = next_low
            next_low = next(low_iter, None)

        if last_high is not None and c.close > last_high.price:
            direction = "bullish"
            kind = "BOS" if trend == "Bullish" else "CHOCH"
            events.append(StructureEvent(index=i, time=c.time, kind=kind, direction=direction))
            last_high = None  # consumed — wait for the next confirmed swing
        if last_low is not None and c.close < last_low.price:
            direction = "bearish"
            kind = "BOS" if trend == "Bearish" else "CHOCH"
            events.append(StructureEvent(index=i, time=c.time, kind=kind, direction=direction))
            last_low = None
    return events


def find_order_blocks(candles: list[Candle], structure_events: list[StructureEvent]) -> list[OrderBlock]:
    """For each structural break, the order block is the last
    opposite-colored candle before the break's originating impulse —
    approximated here as the last opposite-colored candle in the
    lookback window immediately preceding the event candle."""
    blocks: list[OrderBlock] = []
    for event in structure_events:
        lookback_start = max(0, event.index - 10)
        ob_candle = None
        ob_index = None
        for j in range(event.index - 1, lookback_start - 1, -1):
            candidate = candles[j]
            if event.direction == "bullish" and candidate.is_bearish:
                ob_candle = candidate
                ob_index = j
                break
            if event.direction == "bearish" and candidate.is_bullish:
                ob_candle = candidate
                ob_index = j
                break
        if ob_candle is not None:
            kind = "bullish" if event.direction == "bullish" else "bearish"
            blocks.append(
                OrderBlock(
                    index=ob_index,
                    time=ob_candle.time,
                    kind=kind,
                    high=ob_candle.high,
                    low=ob_candle.low,
                )
            )
    return blocks


def find_fair_value_gaps(candles: list[Candle]) -> list[FairValueGap]:
    """3-candle imbalance check across the whole series."""
    gaps: list[FairValueGap] = []
    for i in range(1, len(candles) - 1):
        left, right = candles[i - 1], candles[i + 1]
        if left.high < right.low:
            gaps.append(FairValueGap(start_index=i - 1, end_index=i + 1, kind="bullish", top=right.low, bottom=left.high))
        elif left.low > right.high:
            gaps.append(FairValueGap(start_index=i - 1, end_index=i + 1, kind="bearish", top=left.low, bottom=right.high))
    return gaps


def mark_mitigations(candles: list[Candle], order_blocks: list[OrderBlock], fvgs: list[FairValueGap]) -> None:
    """A zone is "mitigated" once price has traded back into it after
    it formed — mutates the passed-in lists in place."""
    for ob in order_blocks:
        for c in candles[ob.index + 1 :]:
            if c.low <= ob.high and c.high >= ob.low:
                ob.mitigated = True
                break
    for gap in fvgs:
        for c in candles[gap.end_index + 1 :]:
            if c.low <= gap.top and c.high >= gap.bottom:
                gap.mitigated = True
                break


EQ_TOLERANCE_PCT = 0.0008  # ~0.08% — small enough to mean "practically equal", not "nearby"


def find_equal_levels(points: list[SwingPoint]) -> list[list[SwingPoint]]:
    """Groups swing points that sit within ``EQ_TOLERANCE_PCT`` of each
    other — read as resting liquidity (equal highs above price, equal
    lows below)."""
    groups: list[list[SwingPoint]] = []
    used: set[int] = set()
    for i, p in enumerate(points):
        if i in used:
            continue
        group = [p]
        for j in range(i + 1, len(points)):
            if j in used:
                continue
            q = points[j]
            if abs(q.price - p.price) / max(abs(p.price), 1e-9) <= EQ_TOLERANCE_PCT:
                group.append(q)
                used.add(j)
        if len(group) >= 2:
            groups.append(group)
            used.add(i)
    return groups


def analyze_candles(raw_candles: list[dict]) -> SmcAnalysis:
    """Main entry point: takes a list of ``{time, open, high, low,
    close}`` dicts (already parsed/validated by the caller — see
    ``app.schemas.chart.Candle``) and returns a fully-populated
    ``SmcAnalysis``.

    Raises ``ValueError`` if there isn't enough data for a meaningful
    read — this is a plain Python engine, it knows nothing about HTTP,
    per the app's error-handling convention (routers/services translate
    this into a proper API error)."""
    if len(raw_candles) < MIN_CANDLES_FOR_ANALYSIS:
        raise ValueError(
            f"Need at least {MIN_CANDLES_FOR_ANALYSIS} candles for a meaningful read, got {len(raw_candles)}."
        )

    candles = [Candle(**c) for c in raw_candles]
    swing_highs, swing_lows = find_swing_points(candles)
    trend = infer_trend(swing_highs, swing_lows)
    events = find_structure_events(candles, swing_highs, swing_lows, trend)
    order_blocks = find_order_blocks(candles, events)
    fvgs = find_fair_value_gaps(candles)
    mark_mitigations(candles, order_blocks, fvgs)
    equal_highs = find_equal_levels(swing_highs)
    equal_lows = find_equal_levels(swing_lows)

    current = candles[-1].close
    recent_low = swing_lows[-1].price if swing_lows else min(c.low for c in candles)
    recent_high = swing_highs[-1].price if swing_highs else max(c.high for c in candles)
    if recent_high > recent_low:
        position_pct = (current - recent_low) / (recent_high - recent_low)
        premium_discount = "Premium" if position_pct > 0.55 else "Discount" if position_pct < 0.45 else "Equilibrium"
    else:
        premium_discount = "Equilibrium"

    price_in_ob = None
    for ob in reversed(order_blocks):
        if not ob.mitigated and ob.low <= current <= ob.high:
            price_in_ob = ob
            break

    latest_event = events[-1] if events else None

    def _nearest_unmitigated(items, kind_attr, wanted_kind):
        candidates = [x for x in items if getattr(x, kind_attr) == wanted_kind and not x.mitigated]
        return candidates[-1] if candidates else None

    nearest_ob_bull = _nearest_unmitigated(order_blocks, "kind", "bullish")
    nearest_ob_bear = _nearest_unmitigated(order_blocks, "kind", "bearish")
    nearest_fvg_bull = _nearest_unmitigated(fvgs, "kind", "bullish")
    nearest_fvg_bear = _nearest_unmitigated(fvgs, "kind", "bearish")

    # Bias: trend direction, but only "confirmed" by a same-direction
    # BOS/CHOCH and a discount (for buys) / premium (for sells) read —
    # otherwise NONE rather than guessing.
    bias = "NONE"
    if latest_event is not None:
        if latest_event.direction == "bullish" and premium_discount in ("Discount", "Equilibrium"):
            bias = "BUY"
        elif latest_event.direction == "bearish" and premium_discount in ("Premium", "Equilibrium"):
            bias = "SELL"

    return SmcAnalysis(
        trend=trend,
        structure=trend,
        current_price=current,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        order_blocks=order_blocks,
        fair_value_gaps=fvgs,
        structure_events=events,
        equal_highs=equal_highs,
        equal_lows=equal_lows,
        premium_discount=premium_discount,
        price_in_order_block=price_in_ob,
        latest_event=latest_event,
        nearest_unmitigated_ob_bullish=nearest_ob_bull,
        nearest_unmitigated_ob_bearish=nearest_ob_bear,
        nearest_unmitigated_fvg_bullish=nearest_fvg_bull,
        nearest_unmitigated_fvg_bearish=nearest_fvg_bear,
        bias=bias,
    )
