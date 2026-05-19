"""Smoke test for the FastAPI app."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_index() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "OpenSourceCopilot"
