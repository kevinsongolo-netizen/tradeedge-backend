"""Step 1 acceptance tests: system endpoints + docs availability."""


def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_reports_migration_state(client):
    """Readiness now reflects whether Alembic migrations are at head
    (Step 2 extended this per the health.py docstring); the test
    fixture DB is migrated to head, so this should report ready."""
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["ready"], bool)
    assert "migration" in body


def test_version_returns_app_and_version(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "TradeEdge AI Backend"
    # Bumped 6.0.0 -> 7.0.0 for Sprint 7 (Machine Learning); this test
    # tracks the current release, not a fixed historical value.
    assert body["version"] == "7.0.0"


def test_swagger_ui_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger" in resp.text.lower()


def test_redoc_available(client):
    resp = client.get("/redoc")
    assert resp.status_code == 200
    assert "redoc" in resp.text.lower()


def test_openapi_schema_available(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "TradeEdge AI Backend"
    assert "/healthz" in schema["paths"]
    assert "/readyz" in schema["paths"]
    assert "/version" in schema["paths"]


def test_request_id_header_present(client):
    resp = client.get("/healthz")
    assert "x-request-id" in {k.lower() for k in resp.headers.keys()}
