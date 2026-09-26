from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_models_ready() -> None:
    # Context manager runs production startup, including verified EOG warmup.
    with TestClient(app) as started_client:
        response = started_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "als-bci-4class"
    assert data["model_ready"] is True
    assert data["loaded_layouts"] == ["3ch", "22ch"]
    assert set(data["model_checksums"]) == {"3ch", "22ch"}
    assert data["model_error"] is None
    assert data["eog"]["status"] == "ok"
    assert data["eog"]["mode"] == "REAL_MODEL"


def test_root() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "/docs" in response.json()["docs"]
