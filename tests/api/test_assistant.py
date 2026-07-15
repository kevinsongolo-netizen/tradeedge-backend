"""Assistant API tests — ``POST /api/v1/assistant/pretrade-analysis``.

v2 — rebuilt for the rebuilt Pre-Trade Check: it now takes real H4+M15
candles (same shape as Chart Analysis Engine) and runs the ONE
official H4->M15 POI strategy instead of a manual BOS/CHOCH/trend
checklist. ``validate_h4_m15_ob`` is monkeypatched (same strategy
``tests/backtest/test_h4_m15_backtest_engine.py`` uses) so these tests
control VALID vs. WAIT deterministically without hand-constructing
real market structure -- the candle arrays only need to be long enough
to satisfy ``analyze_candles``'s own minimum-length check.
"""
import random

import app.services.assistant_service as assistant_service

from tests.chart.test_candle_smc_engine import _BULLISH_ROWS

PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
SESSIONS = ["London", "New York", "Asian"]

_CANDLES_PAYLOAD = [
    {"time": str(i), "open": o, "high": h, "low": l, "close": c}
    for i, (o, h, l, c) in enumerate(_BULLISH_ROWS)
]

_REQUEST = {
    "pair": "EURUSD",
    "asset": "Forex",
    "session": "London",
    "h4Candles": _CANDLES_PAYLOAD,
    "m15Candles": _CANDLES_PAYLOAD,
}


def _fake_valid(**overrides):
    result = {
        "tradeStatus": "VALID",
        "direction": "buy",
        "confidence": 100,
        "reasonsPassed": ["✓ Price touched an H4 Bullish Order Block (1.09000-1.09500)"],
        "reasonsFailed": [],
        "ruleChecks": [
            {"rule": "H4 Order Block/FVG", "status": "PASSED", "detail": "touched"},
            {"rule": "M15 Order Block/FVG", "status": "PASSED", "detail": "touched"},
            {"rule": "POI Alignment", "status": "PASSED", "detail": "aligned"},
            {"rule": "Entry / SL / TP", "status": "PASSED", "detail": "target found"},
        ],
        "suggestedEntry": 1.1000,
        "stopLoss": 1.0950,
        "takeProfit": 1.1150,
        "riskReward": 3.0,
        "recommendation": "TAKE",
    }
    result.update(overrides)
    return result


def _fake_wait():
    return {
        "tradeStatus": "INVALID",
        "direction": None,
        "confidence": 0,
        "reasonsPassed": [],
        "reasonsFailed": ["✗ Price has not touched or reacted from a valid H4 Order Block or Fair Value Gap"],
        "ruleChecks": [
            {"rule": "H4 Order Block/FVG", "status": "FAILED", "detail": "not touched"},
            {"rule": "M15 Order Block/FVG", "status": "NOT_CHECKED", "detail": "n/a"},
            {"rule": "POI Alignment", "status": "NOT_CHECKED", "detail": "n/a"},
            {"rule": "Entry / SL / TP", "status": "NOT_CHECKED", "detail": "n/a"},
        ],
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
    }


def _seed_trades(client, n=35, seed=21):
    """Same seeding strategy as ``tests/api/test_ml_train.py`` — real
    trades through the full API so rule/execution scores come from the
    actual engines, with a healthy win/loss mix for training."""
    rng = random.Random(seed)
    for i in range(n):
        win = rng.random() < 0.55
        pnl = 60.0 if win else -50.0
        rr = 3.0 if win else 1.0
        trade = {
            "id": f"seed-{i}",
            "date": f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d}",
            "pair": rng.choice(PAIRS),
            "direction": rng.choice(["buy", "sell"]),
            "asset": "Forex",
            "entry": 1.1000,
            "exit": 1.1150 if win else 1.0950,
            "sl": 1.0950,
            "tp": 1.1150,
            "pnl": pnl,
            "rr": rr,
            "session": rng.choice(SESSIONS),
            "h4Trend": rng.choice(["Bullish", "Bearish", "Ranging"]),
            "h4PoiType": "Order Block",
            "m15Confirmations": ["BOS"] if win else [],
            "confidence": rng.randint(50, 95),
            "exitReason": "Take Profit Hit" if win else "Stop Loss Hit",
            "emotion": "Calm" if win else "Anxious",
            "followedPlan": "Yes",
            "rulesFollowed": "all",
        }
        resp = client.post("/api/v1/trades", json=trade)
        assert resp.status_code == 201, resp.text


def test_pretrade_wait_skips_ml_and_history_entirely(client, monkeypatch):
    """Rule #5: when the strategy itself says WAIT, ML/history are
    never even queried -- the strategy's own decision is the only
    thing that matters, and nothing computes a probability for a setup
    that doesn't qualify."""
    monkeypatch.setattr(assistant_service, "validate_h4_m15_ob", lambda h4, m15: _fake_wait())
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "INVALID"
    assert body["recommendation"] == "WAIT"
    assert body["direction"] is None
    assert len(body["ruleChecks"]) == 4
    assert body["ruleChecks"][0]["rule"] == "H4 Order Block/FVG"
    assert body["ruleChecks"][0]["status"] == "FAILED"
    assert body["mlAvailable"] is False
    assert body["winProbability"] is None
    assert any("no ml or history lookup" in r.lower() for r in body["historicalReasons"])


def test_pretrade_valid_before_any_model_trained(client, monkeypatch):
    """Must be useful on day one — before ``/ml/train`` has ever been
    called, a VALID setup still gets a rule/history-based estimate
    rather than an error."""
    monkeypatch.setattr(assistant_service, "validate_h4_m15_ob", lambda h4, m15: _fake_valid())
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "VALID"
    assert body["recommendation"] == "TAKE"
    assert body["direction"] == "buy"
    assert body["suggestedEntry"] == 1.1000
    assert body["mlAvailable"] is False
    assert body["mlRecommendation"] in ("Strong Buy", "Buy", "Wait", "Avoid")
    assert body["mlRecommendation"] != "Strong Buy"  # never Strong Buy at Low confidence
    assert any("No trained ML model yet" in r for r in body["historicalReasons"])
    assert any("official strategy passed" in s for s in body["strengths"])
    # The old trend/BOS/CHOCH-based commentary must be gone.
    assert not any("BOS" in s or "CHOCH" in s for s in body["strengths"] + body["weaknesses"])


def test_pretrade_valid_after_training_uses_ml(client, monkeypatch):
    monkeypatch.setattr(assistant_service, "validate_h4_m15_ob", lambda h4, m15: _fake_valid())
    _seed_trades(client)
    train_resp = client.post("/api/v1/ml/train", json={})
    assert train_resp.status_code == 200, train_resp.text

    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "VALID"
    assert body["mlAvailable"] is True
    assert body["winProbability"] is not None
    assert 0.0 <= body["winProbability"] <= 1.0
    assert body["modelVersion"] == "v1"
    assert body["algorithm"]
    assert not any("No trained ML model yet" in r for r in body["historicalReasons"])


def test_pretrade_analysis_missing_pair_is_422(client):
    body = {**_REQUEST}
    del body["pair"]
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=body)
    assert resp.status_code == 422


def test_pretrade_analysis_missing_m15_candles_is_422(client):
    body = {**_REQUEST}
    del body["m15Candles"]
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=body)
    assert resp.status_code == 422


# ---------- Live Feed path (no candle paste needed) ----------

import app.services.chart_service as chart_service  # noqa: E402


def _seed_live_snapshot(client, symbol, timeframe, validation):
    """Seeds a live_snapshots row via the real ingest endpoint, with
    validate_h4_m15_ob patched (same monkeypatch strategy used above)
    so we control VALID vs WAIT without needing real market structure."""
    import app.services.chart_service as cs

    orig = cs.validate_h4_m15_ob
    cs.validate_h4_m15_ob = lambda h4, m15: validation
    try:
        resp = client.post(
            "/api/v1/live/ingest",
            json={"symbol": symbol, "timeframe": timeframe, "candles": _CANDLES_PAYLOAD},
        )
        assert resp.status_code == 200, resp.text
    finally:
        cs.validate_h4_m15_ob = orig


def test_pretrade_live_no_data_yet_is_404(client):
    resp = client.post(
        "/api/v1/assistant/pretrade-analysis-live",
        json={"pair": "EURUSD", "symbol": "EURUSD", "timeframe": "H4"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_pretrade_live_wait_skips_ml(client):
    _seed_live_snapshot(client, "EURUSD", "H4", _fake_wait())
    resp = client.post(
        "/api/v1/assistant/pretrade-analysis-live",
        json={"pair": "EURUSD", "symbol": "EURUSD", "timeframe": "H4"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "INVALID"
    assert body["recommendation"] == "WAIT"
    assert body["mlAvailable"] is False
    assert len(body["ruleChecks"]) == 4


def test_pretrade_live_valid_uses_stored_validation(client):
    _seed_live_snapshot(client, "GBPUSD", "H4", _fake_valid())
    resp = client.post(
        "/api/v1/assistant/pretrade-analysis-live",
        json={"pair": "GBPUSD", "session": "London", "symbol": "GBPUSD", "timeframe": "H4"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "VALID"
    assert body["recommendation"] == "TAKE"
    assert body["direction"] == "buy"
    assert body["suggestedEntry"] == 1.1000
    assert any("official strategy passed" in s for s in body["strengths"])
