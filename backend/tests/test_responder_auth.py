from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from protidhoni_api.auth import require_responder_token
from protidhoni_api.config import get_settings


def _protected_client() -> TestClient:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_responder_token)])
    async def protected() -> dict[str, bool]:
        return {"authorized": True}

    return TestClient(app)


def test_responder_auth_denies_access_when_server_token_is_unset(monkeypatch) -> None:
    monkeypatch.delenv("PROTIDHONI_RESPONDER_TOKEN", raising=False)
    get_settings.cache_clear()
    try:
        response = _protected_client().get(
            "/protected", headers={"X-Responder-Token": "attacker-supplied"}
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503


def test_responder_auth_denies_weak_server_tokens(monkeypatch) -> None:
    for token in ("too-short", " x" * 16):
        monkeypatch.setenv("PROTIDHONI_RESPONDER_TOKEN", token)
        get_settings.cache_clear()
        response = _protected_client().get(
            "/protected", headers={"X-Responder-Token": token}
        )
        assert response.status_code == 503
    get_settings.cache_clear()


def test_responder_auth_denies_missing_and_incorrect_tokens(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_RESPONDER_TOKEN", "correct-responder-token-value-1234")
    get_settings.cache_clear()
    try:
        with _protected_client() as client:
            missing = client.get("/protected")
            incorrect = client.get(
                "/protected", headers={"X-Responder-Token": "incorrect-token-value"}
            )
    finally:
        get_settings.cache_clear()

    assert missing.status_code == 401
    assert incorrect.status_code == 401
    assert missing.headers["www-authenticate"] == "ApiKey"


def test_responder_auth_accepts_only_the_configured_token(monkeypatch) -> None:
    token = "correct-responder-token-value-1234"
    monkeypatch.setenv("PROTIDHONI_RESPONDER_TOKEN", token)
    get_settings.cache_clear()
    try:
        response = _protected_client().get(
            "/protected", headers={"X-Responder-Token": token}
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json() == {"authorized": True}
