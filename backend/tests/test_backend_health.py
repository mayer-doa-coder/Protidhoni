import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from protidhoni_api.config import get_settings
from protidhoni_api.main import create_app


def test_health_is_safe_and_versioned() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "backend",
        "status": "ok",
        "version": "0.1.0",
        # Null rather than absent when the SMS/USSD gateway is unconfigured, so
        # the dashboard can distinguish "no gateway on this deployment" from
        # "older backend that does not publish the field at all".
        "gateway_pubkey_hash": None,
    }


def test_health_publishes_the_gateway_identity_when_configured(monkeypatch) -> None:
    seed = secrets.token_bytes(32)
    monkeypatch.setenv(
        "PROTIDHONI_GATEWAY_PRIVATE_KEY",
        base64.urlsafe_b64encode(seed).rstrip(b"=").decode("ascii"),
    )
    get_settings.cache_clear()
    try:
        response = TestClient(create_app()).get("/health")
    finally:
        get_settings.cache_clear()

    public_key = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()
    expected_hash = (
        base64.urlsafe_b64encode(hashlib.sha256(public_key).digest()).rstrip(b"=").decode("ascii")
    )
    assert response.status_code == 200
    assert response.json()["gateway_pubkey_hash"] == expected_hash


def test_health_never_leaks_the_gateway_private_key(monkeypatch) -> None:
    seed_b64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", seed_b64)
    get_settings.cache_clear()
    try:
        body = TestClient(create_app()).get("/health").text
    finally:
        get_settings.cache_clear()

    assert seed_b64 not in body
