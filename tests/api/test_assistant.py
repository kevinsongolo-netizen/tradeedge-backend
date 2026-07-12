"""Assistant API tests — ``POST /api/v1/assistant/pretrade-analysis``
(Sprint 8 Phases 5 & 7)."""
import random

PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
SESSIONS = ["London", "New York", "Asian"]


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


_CANDIDATE = {
    "pair": "EURUSD",
    "asset": "Forex",
    "direction": "buy",
    "session": "London",
    "h4Trend": "Bullish",
    "h4PoiType": "Order Block",
    "hasBos": True,
    "hasChoch": True,
    "hasLiquiditySweep": True,
    "plannedRR": 2.5,
    "ruleScore": 82,
    "confidence": 80,
}


def test_pretrade_analysis_before_any_model_trained(client):
    """Phase 5 must be useful on day one — before ``/ml/train`` has
    ever been called, the endpoint should degrade to a rule-score-only
    estimate rather than error."""
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_CANDIDATE)
    assert resp.status_code == 200
    body = resp.json()

    assert body["mlAvailable"] is False
    assert body["tradeQualityScore"] == 82
    assert body["winProbability"] is None
    assert body["modelVersion"] is None
    assert body["algorithm"] is None
    assert body["recommendation"] in ("Strong Buy", "Buy", "Wait", "Avoid")
    assert body["recommendation"] != "Strong Buy"  # never Strong Buy at Low confidence
    assert any("No trained ML model yet" in r for r in body["historicalReasons"])
    # Phase 7 explanation fields:
    assert isinstance(body["strengths"], list) and len(body["strengths"]) > 0
    assert isinstance(body["weaknesses"], list)


def test_pretrade_analysis_after_training_uses_ml(client):
    _seed_trades(client)
    train_resp = client.post("/api/v1/ml/train", json={})
    assert train_resp.status_code == 200, train_resp.text

    resp = client.post("/api/v1/assistant/pretrade-analysis", json=_CANDIDATE)
    assert resp.status_code == 200
    body = resp.json()

    assert body["mlAvailable"] is True
    assert body["winProbability"] is not None
    assert 0.0 <= body["winProbability"] <= 1.0
    assert body["modelVersion"] == "v1"
    assert body["algorithm"]
    assert not any("No trained ML model yet" in r for r in body["historicalReasons"])


def test_pretrade_analysis_counter_trend_candidate_shows_weaknesses(client):
    counter_trend = {
        "pair": "EURUSD",
        "direction": "sell",
        "h4Trend": "Bullish",
        "hasBos": False,
        "hasChoch": False,
        "hasLiquiditySweep": False,
        "plannedRR": 1.0,
        "ruleScore": 20,
        "confidence": 15,
    }
    resp = client.post("/api/v1/assistant/pretrade-analysis", json=counter_trend)
    assert resp.status_code == 200
    body = resp.json()
    assert any("counter to the H4" in w for w in body["weaknesses"])
    assert body["recommendation"] == "Avoid"


def test_pretrade_analysis_missing_pair_is_422(client):
    resp = client.post("/api/v1/assistant/pretrade-analysis", json={"direction": "buy"})
    assert resp.status_code == 422
