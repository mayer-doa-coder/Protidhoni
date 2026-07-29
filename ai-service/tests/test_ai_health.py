from fastapi.testclient import TestClient

from protidhoni_ai.main import create_app


def test_health_declares_the_configured_model_without_loading_it() -> None:
    body = TestClient(create_app()).get("/health").json()

    assert body["service"] == "ai-service"
    assert body["status"] == "ok"
    assert body["configured_model"] == "csebuetnlp/banglabert"
