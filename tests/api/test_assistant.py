"""Assistant API tests — ``POST /api/v1/assistant/pretrade-analysis``.

v3 (Sprint 18) — rebuilt for the Personal Averaging Strategy: it now
takes Daily+M15 candles (same shape as Chart Analysis Engine) and runs
the ONE official Personal Averaging Strategy instead of the retired
H4->M15 POI engine. ``validate_personal_averaging`` is monkeypatched
(same strategy ``tests/backtest/test_personal_averaging_backtest_engine.py``
uses) so these tests control VALID/ADD vs. WAIT deterministically
without hand-constructing real market structure -- the candle arrays
only need to be long enough to satisfy ``analyze_candles``'s own
minimum-length check.
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
    "dailyCandles": _CANDLES_PAYLOAD,
    "m15Candles": _CANDLES_PAYLOAD,
}


def _fake_valid(**overrides):
    result = {
        "tradeStatus": "VALID",
        "direction": "buy",
        "confidence": 100,
        "reasonsPassed": ["Daily candle is Bullish -- only BUY setups apply today"],
        "reasonsFailed": [],
        "ruleChecks": [
            {"rule": "Daily Bias", "status": "PASSED", "detail": "bullish"},
            {"rule": "M15 Order Block/FVG", "status": "PASSED", "detail": "touched"},
            {"rule": "Entry Timing (near end of zone)", "status": "PASSED", "detail": "near end"},
            {"rule": "Add-On Entry (2nd position)", "status": "NOT_CHECKED", "detail": "n/a"},
        ],
        "suggestedEntry": 1.1000,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "TAKE",
        "strategy": "Personal Averaging Strategy (Daily Bias + M15 POI, no fixed SL/TP)",
        "dailyBias": "BUY",
        "addOnSignal": False,
        "breakEvenPrice": None,
    }
    result.update(overrides)
    return result


def _fake_wait():
    return {
        "tradeStatus": "INVALID",
        "direction": None,
        "confidence": 0,
        "reasonsPassed": [],
        "reasonsFailed": ["No daily candle supplied -- can't determine daily bias"],
        "ruleChecks": [
            {"rule": "Daily Bias", "status": "FAILED", "detail": "no daily candle"},
            {"rule": "M15 Order Block/FVG", "status": "NOT_CHECKED", "detail": "n/a"},
            {"rule": "Entry Timing (near end of zone)", "status": "NOT_CHECKED", "detail": "n/a"},
            {"rule": "Add-On Entry (2nd position)", "status": "NOT_CHECKED", "detail": "n/a"},
        ],
        "suggestedEntry": None,
        "stopLoss": None,
        "takeProfit": None,
        "riskReward": None,
        "recommendation": "WAIT",
        "strategy": "Personal Averaging Strategy (Daily Bias + M15 POI, no fixed SL/TP)",
        "dailyBias": None,
        "addOnSignal": False,
        "breakEvenPrice": None,
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
    monkeypatch.setattr(assistant_service, "validate_personal_averaging", lambda daily, m15, open_trade_in_loss=False: _fake_wait())
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "INVALID"
    assert body["recommendation"] == "WAIT"
    assert body["direction"] is None
    assert len(body["ruleChecks"]) == 4
    assert body["ruleChecks"][0]["rule"] == "Daily Bias"
    assert body["ruleChecks"][0]["status"] == "FAILED"
    assert body["mlAvailable"] is False
    assert body["winProbability"] is None
    assert any("no ml or history lookup" in r.lower() for r in body["historicalReasons"])


def test_pretrade_valid_before_any_model_trained(client, monkeypatch):
    """Must be useful on day one — before ``/ml/train`` has ever been
    called, a VALID setup still gets a rule/history-based estimate
    rather than an error."""
    monkeypatch.setattr(assistant_service, "validate_personal_averaging", lambda daily, m15, open_trade_in_loss=False: _fake_valid())
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "VALID"
    assert body["recommendation"] == "TAKE"
    assert body["direction"] == "buy"
    assert body["suggestedEntry"] == 1.1000
    assert body["dailyBias"] == "BUY"
    assert body["addOnSignal"] is False
    assert body["mlAvailable"] is False
    assert body["mlRecommendation"] in ("Strong Buy", "Buy", "Wait", "Avoid")
    assert body["mlRecommendation"] != "Strong Buy"  # never Strong Buy at Low confidence
    assert any("No trained ML model yet" in r for r in body["historicalReasons"])
    assert any("official strategy passed" in s for s in body["strengths"])
    # The old trend/BOS/CHOCH-based commentary must be gone.
    assert not any("BOS" in s or "CHOCH" in s for s in body["strengths"] + body["weaknesses"])


def test_pretrade_add_on_signal_flows_through(client, monkeypatch):
    monkeypatch.setattr(
        assistant_service,
        "validate_personal_averaging",
        lambda daily, m15, open_trade_in_loss=False: _fake_valid(recommendation="ADD", addOnSignal=True),
    )
    resp = client.post(
        "/api/v1/assistant/pretrade-analysis",
        json={**_REQUEST, "openTradeInLoss": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tradeStatus"] == "VALID"
    assert body["recommendation"] == "ADD"
    assert body["addOnSignal"] is True


def test_pretrade_valid_after_training_uses_ml(client, monkeypatch):
    monkeypatch.setattr(assistant_service, "validate_personal_averaging", lambda daily, m15, open_trade_in_loss=False: _fake_valid())
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


def test_pretrade_analysis_missing_daily_candles_is_422(client):
    body = {**_REQUEST}
    del body["dailyCandles"]
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=body)
    assert resp.status_code == 422


# ---------- Live Feed path (no candle paste needed) ----------

import app.services.chart_service as chart_service  # noqa: E402


def _seed_live_snapshot(client, symbol, timeframe, validation):
    """Seeds a live_snapshots row via the real ingest endpoint, with
    validate_personal_averaging patched (same monkeypatch strategy used
    above) so we control VALID vs WAIT without needing real market
    structure."""
    import app.services.chart_service as cs

    orig = cs.validate_personal_averaging
    cs.validate_personal_averaging = lambda daily, m15, open_trade_in_loss=False: validation
    try:
        resp = client.post(
            "/api/v1/live/ingest",
            json={"symbol": symbol, "timeframe": timeframe, "candles": _CANDLES_PAYLOAD},
        )
        assert resp.status_code == 200, resp.text
    finally:
        cs.validate_personal_averaging = orig


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
