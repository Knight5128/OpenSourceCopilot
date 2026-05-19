from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import app


class _StubKGService:
    async def safe_stats(self):
        return {"nodes": {"Repo": 2}, "edges": {"AFFECTS": 3}, "degraded": False}

    async def safe_subgraph(self, center: str, hops: int, limit: int):
        return {
            "nodes": [{"id": "1", "label": "Repo", "key": center, "props": {"stars": 10}}],
            "edges": [{"id": "2", "source": "1", "target": "1", "type": "CALLS", "props": {}}],
            "degraded": False,
        }

    async def close(self) -> None:
        return None


class _DegradedKGService:
    async def safe_stats(self):
        return {"nodes": {}, "edges": {}, "degraded": True}

    async def safe_subgraph(self, center: str, hops: int, limit: int):
        return {"nodes": [], "edges": [], "degraded": True}

    async def close(self) -> None:
        return None


def test_kg_endpoints_return_data(monkeypatch) -> None:
    from backend.app import api as api_module

    monkeypatch.setattr(api_module, "get_kg_service", lambda: _StubKGService())
    client = TestClient(app)

    stats = client.get("/api/v1/kg/stats")
    assert stats.status_code == 200
    assert stats.json()["nodes"]["Repo"] == 2

    subgraph = client.get("/api/v1/kg/subgraph", params={"center": "owner/repo", "hops": 1})
    assert subgraph.status_code == 200
    assert subgraph.json()["nodes"][0]["key"] == "owner/repo"


def test_kg_endpoints_return_degraded_when_unavailable(monkeypatch) -> None:
    from backend.app import api as api_module

    monkeypatch.setattr(api_module, "get_kg_service", lambda: _DegradedKGService())
    client = TestClient(app)

    stats = client.get("/api/v1/kg/stats")
    assert stats.status_code == 200
    assert stats.json()["degraded"] is True

    subgraph = client.get("/api/v1/kg/subgraph", params={"center": "owner/repo"})
    assert subgraph.status_code == 200
    assert subgraph.json()["degraded"] is True
