import pytest
from fastapi.testclient import TestClient

from protidhoni_api.config import get_settings
from protidhoni_api.main import create_app


def test_dashboard_origin_can_preflight_privileged_request(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_CORS_ORIGINS", "https://responders.example")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.options(
                "/reports/00000000-0000-0000-0000-000000000000",
                headers={
                    "Origin": "https://responders.example",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "X-Responder-Token, Content-Type",
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://responders.example"
    assert "X-Responder-Token" in response.headers["access-control-allow-headers"]


def test_unlisted_dashboard_origin_is_not_allowed(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_CORS_ORIGINS", "https://responders.example")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            response = client.options(
                "/instructions",
                headers={
                    "Origin": "https://attacker.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "X-Responder-Token",
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    "origins",
    ["*", "https://user:password@responders.example", "https://responders.example/path"],
)
def test_unsafe_cors_configuration_fails_closed(monkeypatch, origins) -> None:
    monkeypatch.setenv("PROTIDHONI_CORS_ORIGINS", origins)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="PROTIDHONI_CORS_ORIGINS"):
            create_app()
    finally:
        get_settings.cache_clear()
