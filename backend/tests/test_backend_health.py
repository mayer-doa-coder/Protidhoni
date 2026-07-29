from fastapi.testclient import TestClient

from protidhoni_api.main import create_app


def test_health_is_safe_and_versioned() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "backend", "status": "ok", "version": "0.1.0"}
