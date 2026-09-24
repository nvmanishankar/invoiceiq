from fastapi.testclient import TestClient

from app.main import app


def test_health_and_autoseed():
    with TestClient(app) as client:  # runs lifespan: create tables + seed
        r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
