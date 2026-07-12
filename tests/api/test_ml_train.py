"""API tests — Sprint 7's ``/api/v1/ml/train``, ``/ml/models*``,
``/ml/predict``, and ``/ml/dataset/validation-report``.

Does not touch (or re-test) Sprint 6's ``/ml/dataset``, ``/ml/validate``,
``/ml/exports`` — those are covered by ``tests/api/test_ml.py``.
"""
import random

PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
SESSIONS = ["London", "New York", "Asian"]


def _seed_trades(client, n=35, seed=11):
    """Posts ``n`` real trades through the full API (so each gets a
    real rule_score/execution_score from the actual AI engines, not a
    stub), with a healthy mix of wins and losses so training has both
    classes to learn from."""
    rng = random.Random(seed)
    for i in range(n):
        win = rng.random() < 0.55
        entry = 1.1000
        sl = 1.0950
        tp = 1.1150
        exit_price = tp if win else sl
        pnl = 60.0 if win else -50.0
        rr = 3.0 if win else 1.0  # rr is a positive realized R-multiple magnitude; sign of pnl carries win/loss
        trade = {
            "id": f"seed-{i}",
            "date": f"2026-0{(i % 6) + 1}-{(i % 27) + 1:02d}",
            "pair": rng.choice(PAIRS),
            "direction": rng.choice(["buy", "sell"]),
            "asset": "Forex",
            "entry": entry,
            "exit": exit_price,
            "sl": sl,
            "tp": tp,
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


def test_validation_report_not_ready_when_empty(client):
    resp = client.get("/api/v1/ml/dataset/validation-report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalTrades"] == 0
    assert body["readyForTraining"] is False
    assert body["reason"] is not None


def test_validation_report_ready_after_enough_trades(client):
    _seed_trades(client, n=35)
    resp = client.get("/api/v1/ml/dataset/validation-report")
    body = resp.json()
    assert body["totalTrades"] == 35
    assert body["validTrades"] == 35
    assert body["readyForTraining"] is True
    assert body["classDistribution"]["wins"] + body["classDistribution"]["losses"] == 35


def test_train_fails_with_422_when_not_enough_data(client):
    _seed_trades(client, n=5)
    resp = client.post("/api/v1/ml/train", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "INSUFFICIENT_TRAINING_DATA"


def test_train_succeeds_and_persists_v1(client):
    _seed_trades(client, n=35)
    resp = client.post("/api/v1/ml/train", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "v1"
    assert body["algorithm"] in {"logistic_regression", "random_forest", "gradient_boosting"}
    assert body["rowsUsed"] == 35
    assert set(body["candidates"].keys()) == {
        "logistic_regression", "random_forest", "gradient_boosting"
    }
    assert "accuracy" in body["testMetrics"]
    assert isinstance(body["overfitWarning"], bool)


def test_train_twice_creates_v2_and_deactivates_v1(client):
    _seed_trades(client, n=35)
    first = client.post("/api/v1/ml/train", json={})
    second = client.post("/api/v1/ml/train", json={})
    assert first.json()["version"] == "v1"
    assert second.json()["version"] == "v2"

    models = client.get("/api/v1/ml/models").json()
    versions = {m["version"]: m["isActive"] for m in models}
    assert versions["v1"] is False
    assert versions["v2"] is True


def test_models_endpoint_empty_before_training(client):
    resp = client.get("/api/v1/ml/models")
    assert resp.status_code == 200
    assert resp.json() == []


def test_active_model_404_before_training(client):
    resp = client.get("/api/v1/ml/models/active")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_active_model_after_training(client):
    _seed_trades(client, n=35)
    client.post("/api/v1/ml/train", json={})
    resp = client.get("/api/v1/ml/models/active")
    assert resp.status_code == 200
    body = resp.json()
    assert body["isActive"] is True
    assert body["version"] == "v1"


def test_predict_404_before_any_training(client):
    resp = client.post("/api/v1/ml/predict", json={"pair": "EURUSD"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NO_ACTIVE_MODEL"


def test_predict_returns_probability_and_bucket_after_training(client):
    _seed_trades(client, n=35)
    client.post("/api/v1/ml/train", json={})
    resp = client.post(
        "/api/v1/ml/predict",
        json={
            "pair": "EURUSD", "asset": "Forex", "direction": "buy", "session": "London",
            "h4Trend": "Bullish", "h4PoiType": "Order Block", "hasBos": True,
            "plannedRR": 3.0, "ruleScore": 85, "confidence": 80, "emotion": "Calm",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert 0.0 <= body["winProbability"] <= 1.0
    assert 0.0 <= body["predictedQualityScore"] <= 100.0
    assert body["predictedQualityBucket"] in {"A", "B", "C", "D"}
    assert body["modelVersion"] == "v1"


def test_predict_with_minimal_fields_does_not_crash(client):
    """A prediction request can omit almost everything (e.g. scoring a
    trade idea before most SMC fields are filled in) — missing values
    must be imputed, never a 500."""
    _seed_trades(client, n=35)
    client.post("/api/v1/ml/train", json={})
    resp = client.post("/api/v1/ml/predict", json={"pair": "GBPUSD"})
    assert resp.status_code == 200
