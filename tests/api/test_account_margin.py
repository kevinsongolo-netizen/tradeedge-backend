"""API tests for the Sprint 18 margin/floating-loss buffer
(``/api/v1/account-margin/*``)."""


def test_latest_returns_404_before_any_ingest(client):
    resp = client.get("/api/v1/account-margin/latest")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_ingest_then_latest_safe_status(client):
    ingest_resp = client.post(
        "/api/v1/account-margin/ingest",
        json={"balance": 1000.0, "equity": 1000.0, "margin": 100.0},
    )
    assert ingest_resp.status_code == 200, ingest_resp.text
    body = ingest_resp.json()
    assert body["marginLevelPct"] == 1000.0  # equity/margin*100
    assert body["status"] == "SAFE"
    assert body["floatingPnl"] == 0.0

    latest_resp = client.get("/api/v1/account-margin/latest")
    assert latest_resp.status_code == 200, latest_resp.text
    assert latest_resp.json()["status"] == "SAFE"


def test_ingest_upserts_single_row_per_user(client):
    client.post("/api/v1/account-margin/ingest", json={"balance": 1000.0, "equity": 1000.0, "margin": 100.0})
    client.post("/api/v1/account-margin/ingest", json={"balance": 1000.0, "equity": 900.0, "margin": 100.0})
    resp = client.get("/api/v1/account-margin/latest")
    body = resp.json()
    assert body["equity"] == 900.0
    assert body["floatingPnl"] == -100.0


def test_no_open_positions_when_margin_zero(client):
    resp = client.post(
        "/api/v1/account-margin/ingest",
        json={"balance": 1000.0, "equity": 1000.0, "margin": 0.0},
    )
    body = resp.json()
    assert body["status"] == "NO_POSITIONS"
    assert body["marginLevelPct"] is None
    assert body["bufferToMarginCallPct"] is None


def test_warning_status_between_stop_out_and_margin_call():
    # margin_level = equity/margin*100 -- pick a value between 20 and 50.
    pass


def test_warning_and_danger_status_thresholds(client):
    # margin_level_pct = 1000/1000*100 = 100 -> too safe; craft values
    # that land between thresholds instead.
    resp = client.post(
        "/api/v1/account-margin/ingest",
        json={"balance": 1000.0, "equity": 350.0, "margin": 1000.0},  # margin_level = 35% -> WARNING
    )
    body = resp.json()
    assert body["marginLevelPct"] == 35.0
    assert body["status"] == "WARNING"
    assert body["bufferToMarginCallPct"] == -15.0  # 35 - 50
    assert body["bufferToStopOutPct"] == 15.0  # 35 - 20

    resp2 = client.post(
        "/api/v1/account-margin/ingest",
        json={"balance": 1000.0, "equity": 150.0, "margin": 1000.0},  # margin_level = 15% -> DANGER
    )
    body2 = resp2.json()
    assert body2["marginLevelPct"] == 15.0
    assert body2["status"] == "DANGER"
    assert body2["bufferToStopOutPct"] == -5.0


def test_plain_format_returns_key_value_lines(client):
    resp = client.post(
        "/api/v1/account-margin/ingest?format=plain",
        json={"balance": 1000.0, "equity": 1000.0, "margin": 100.0},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "STATUS=SAFE" in text
    assert "MARGIN_LEVEL_PCT=1000.0" in text


def test_custom_thresholds_override_defaults(client):
    resp = client.post(
        "/api/v1/account-margin/ingest",
        json={
            "balance": 1000.0,
            "equity": 300.0,
            "margin": 1000.0,  # margin_level = 30%
            "marginCallLevelPct": 40.0,
            "stopOutLevelPct": 10.0,
        },
    )
    body = resp.json()
    assert body["marginCallLevelPct"] == 40.0
    assert body["stopOutLevelPct"] == 10.0
    assert body["status"] == "WARNING"  # 30 is between 10 and 40
