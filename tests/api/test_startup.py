"""Step 2 acceptance test: the app actually starts.

``tests/conftest.py``'s ``client`` fixture builds a plain
``TestClient(app)`` without entering it as a context manager, which
means individual requests never trigger the ASGI ``lifespan`` protocol
(startup/shutdown) — that's why ``test_health.py`` didn't need a working
DB to pass. This test does the opposite: it enters ``TestClient`` as a
context manager, which *does* run ``app.main.lifespan`` end-to-end,
including the new ``check_database_connection()`` call. If the DB
weren't reachable, this would raise instead of yielding a client.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_app_starts_and_healthz_responds():
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
