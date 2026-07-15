"""API tests for the Sprint 14 Live MT5 Feed (``/api/v1/live/*``).
Reuses the hand-verified bullish candle series from
``tests/chart/test_candle_smc_engine.py`` so the expected trend is
known ground truth, not a guess."""
from tests.chart.test_candle_smc_engine import _BULLISH_ROWS

_CANDLES_PAYLOAD = [
    {"time": str(i), "open": o, "high": h, "low": l, "close": c}
    for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
]


def test_latest_returns_404_before_any_ingest(client):
    resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ingest_then_latest_round_trip(client):
    ingest_resp = client.post(
        "/api/v1/live/ingest",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    ingest_body = ingest_resp.json()
    assert ingest_body["analysis"]["trend"] == "Bullish"

    latest_resp = client.get("/api/v1/live/latest", params={"symbol": "EURUSD", "timeframe": "H4"})
    assert latest_resp.status_code == 200, latest_resp.text
    latest_body = latest_resp.json()
    assert latest_body["symbol"] == "EURUSD"
    assert latest_body["timeframe"] == "H4"
    assert latest_body["analysis"]["trend"] == "Bullish"
    assert "updatedAt" in latest_body


def test_ingest_upserts_same_symbol_timeframe(client):
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "GBPUSD", "timeframe": "M15", "candles": _CANDLES_PAYLOAD},
    )
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "GBPUSD", "timeframe": "M15", "candles": _CANDLES_PAYLOAD},
    )
    resp = client.get("/api/v1/live/latest", params={"symbol": "GBPUSD", "timeframe": "M15"})
    assert resp.status_code == 200, resp.text


def test_different_symbols_are_independent(client):
    client.post(
        "/api/v1/live/ingest",
        json={"symbol": "BTCUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD},
    )
    resp = client.get("/api/v1/live/latest", params={"symbol": "ETHUSD", "timeframe": "H4"})
    assert resp.status_code == 404, resp.text


def test_ingest_plain_format_for_mt5_ea(client):
    resp = client.post(
        "/api/v1/live/ingest?format=plain",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD, "plannedRr": 3.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "STATUS=" in text
    assert "RECOMMENDATION=" in text
    assert "HEADLINE=" in text
    assert "CONFIDENCE=" in text


def test_ingest_rejects_too_few_candles(client):
    resp = client.post(
        "/api/v1/live/ingest",
        json={"symbol": "EURUSD", "timeframe": "H4", "candles": _CANDLES_PAYLOAD[:3]},
    )
    assert resp.status_code == 422, resp.text


def test_latest_survives_old_shaped_stored_coach_confidence(client):
    """Regression test for a real production bug: live_snapshots rows
    persist the ``coach`` dict as raw JSON, so a row ingested before
    ConfidenceBreakdown's fields were renamed (old trendAlignment/
    poiQuality/liquidityQuality/bosQuality/chochQuality/fvgQuality/
    rrQuality shape -- see app/chart/coach_explainer.py's history)
    would otherwise 500 on every read until the EA happened to push a
    fresh update for that exact symbol/timeframe. Simulates that old
    row directly against the DB (bypassing ingest, which always writes
    the current shape) and confirms /live/latest degrades gracefully
    instead of crashing."""
    import asyncio

    from app.db.database import get_sessionmaker
    from app.db.repositories.live_snapshot_repo import LiveSnapshotRepository

    async def _seed_old_shaped_row():
        session_factory = get_sessionmaker()
        async with session_factory() as session:
            repo = LiveSnapshotRepository(session)
            await repo.upsert(
                1,
                "OLDSHAPE",
                "H4",
                {
                    "analysis": {
                        "source": "candles", "trend": "Bullish", "structure": "Bullish",
                        "currentPriceContext": "test", "liquidity": "test", "latestEvent": None,
                        "fvgStatus": None, "premiumDiscount": "Discount", "bias": "BUY",
                        "confidence": 80, "zones": [], "entryZone": None, "notes": [], "isPlaceholder": False,
                    },
                    "validation": {
                        "tradeStatus": "INVALID", "direction": None, "confidence": 0,
                        "reasonsPassed": [], "reasonsFailed": ["old data"],
                        "suggestedEntry": None, "stopLoss": None, "takeProfit": None,
                        "riskReward": None, "recommendation": "WAIT",
                        # NOTE: no "ruleChecks" key at all -- pre-dates that field too.
                    },
                    "coach": {
                        "headline": "NO TRADE",
                        "explanation": ["old narration"],
                        "confidence": {
                            "trendAlignment": 90, "poiQuality": 70, "liquidityQuality": 85,
                            "bosQuality": 40, "chochQuality": 20, "fvgQuality": 70, "rrQuality": 30,
                            "overall": 58,
                        },
                        "recommendation": "WAIT",
                    },
                    "multi_timeframe": None,
                },
            )
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_seed_old_shaped_row())

    resp = client.get("/api/v1/live/latest", params={"symbol": "OLDSHAPE", "timeframe": "H4"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["validation"]["ruleChecks"] == []
    breakdown = body["coach"]["confidence"]
    assert breakdown["dailyBias"] == 0
    assert breakdown["m15Poi"] == 0
    assert breakdown["entryTiming"] == 0
    assert breakdown["addOn"] == 0
    # "overall" wasn't renamed between old and new shapes, so the old
    # stored value survives untouched -- only the truly-renamed fields
    # fall back to their 0 default.
    assert breakdown["overall"] == 58
