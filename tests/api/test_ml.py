"""ML dataset API tests — ``/api/v1/ml/*`` (Sections 4.7, 8)."""

TRADE = {
    "id": "ml-1", "date": "2026-01-01", "pair": "EURUSD", "direction": "buy", "asset": "Forex",
    "entry": 1.08, "exit": 1.09, "sl": 1.075, "tp": 1.10, "pnl": 60.0, "rr": 2.0, "session": "London",
    "confidence": 80, "exitReason": "Take Profit Hit",
}


def test_ml_validate_reports_quality(client):
    client.post("/api/v1/trades", json=TRADE)
    resp = client.get("/api/v1/ml/validate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["qualityScore"] == 100


def test_ml_dataset_json_uses_snake_case_columns(client):
    client.post("/api/v1/trades", json=TRADE)
    resp = client.get("/api/v1/ml/dataset", params={"format": "json"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert "rule_score" in rows[0]
    assert "ruleScore" not in rows[0]


def test_ml_dataset_csv_has_correct_content_type(client):
    client.post("/api/v1/trades", json=TRADE)
    resp = client.get("/api/v1/ml/dataset", params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert resp.text.splitlines()[0].startswith("id,user_id,date")


def test_ml_export_writes_files_and_returns_summary(client):
    client.post("/api/v1/trades", json=TRADE)
    resp = client.post("/api/v1/ml/exports", json={"format": "both"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rowCount"] == 1
    assert len(body["files"]) == 2
    import os
    for f in body["files"]:
        assert os.path.exists(f["path"])


def test_ml_validate_empty_journal(client):
    resp = client.get("/api/v1/ml/validate")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
