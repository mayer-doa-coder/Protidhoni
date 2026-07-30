"""Gateway HTTP behavior, security boundaries, idempotency, and minimisation."""

import base64
import json
import secrets
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from protidhoni_api import db as db_module
from protidhoni_api import gateway_routes as gateway_module
from protidhoni_api import ingestion as ingestion_module
from protidhoni_api.config import get_settings
from protidhoni_api.crypto import verify_report_signature
from protidhoni_api.gateway_webhook import (
    SIMULATOR_SIGNATURE_HEADER,
    TWILIO_SIGNATURE_HEADER,
    expected_simulator_signature,
    expected_twilio_signature,
)
from protidhoni_api.main import create_app
from protidhoni_api.models import Report
from protidhoni_api.routes import get_db_pool

SMS_TOKEN = "s" * 32
USSD_TOKEN = "u" * 32
PHONE_PEPPER = "p" * 32
CALLER = "+8801711111111"
SMS_URL = "http://testserver/gateway/sms"
USSD_URL = "http://testserver/gateway/ussd"


@pytest.fixture
def gateway_env(monkeypatch):
    seed = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", seed)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", SMS_TOKEN)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN", USSD_TOKEN)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PHONE_PEPPER", PHONE_PEPPER)
    get_settings.cache_clear()
    gateway_module._phone_limiter._events.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def stored_reports(monkeypatch) -> list[Report]:
    captured: list[Report] = []

    async def fake_report_exists(pool, *, message_id: str) -> bool:
        return any(report.message_id == message_id for report in captured)

    async def fake_insert_report(pool, report: Report):
        if any(existing.message_id == report.message_id for existing in captured):
            return "duplicate"
        captured.append(report)
        return "accepted"

    monkeypatch.setattr(ingestion_module.db, "report_exists", fake_report_exists)
    monkeypatch.setattr(ingestion_module.db, "insert_report", fake_insert_report)
    return captured


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    return TestClient(app)


def _sms_params(**overrides) -> dict[str, str]:
    params = {
        "MessageSid": "SM" + secrets.token_hex(16),
        "From": CALLER,
        "To": "+8801000000000",
        "Body": "SOS trapped need rescue 4 people",
    }
    params.update(overrides)
    return params


def _ussd_params(**overrides) -> dict[str, str]:
    params = {
        "sessionId": "US" + secrets.token_hex(16),
        "serviceCode": "*789#",
        "phoneNumber": CALLER,
        "text": "",
    }
    params.update(overrides)
    return params


def _post_sms(
    client: TestClient,
    params: dict[str, str],
    *,
    token: str | None = SMS_TOKEN,
):
    body = urlencode(params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token is not None:
        headers[TWILIO_SIGNATURE_HEADER] = expected_twilio_signature(
            url=SMS_URL, params=params, auth_token=token
        )
    return client.post("/gateway/sms", content=body, headers=headers)


def _post_ussd(
    client: TestClient,
    params: dict[str, str],
    *,
    token: str | None = USSD_TOKEN,
):
    body = urlencode(params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token is not None:
        headers[SIMULATOR_SIGNATURE_HEADER] = expected_simulator_signature(
            url=USSD_URL, body=body, auth_token=token
        )
    return client.post("/gateway/ussd", content=body, headers=headers)


class TestAdapterAuthentication:
    @pytest.mark.parametrize("channel", ["sms", "ussd"])
    def test_unsigned_callbacks_are_rejected(self, channel, gateway_env, stored_reports) -> None:
        response = (
            _post_sms(_client(), _sms_params(), token=None)
            if channel == "sms"
            else _post_ussd(_client(), _ussd_params(), token=None)
        )
        assert response.status_code == 401
        assert stored_reports == []

    def test_tampering_after_twilio_signing_is_rejected(self, gateway_env, stored_reports) -> None:
        params = _sms_params()
        signature = expected_twilio_signature(url=SMS_URL, params=params, auth_token=SMS_TOKEN)
        params["Body"] = "injected content"
        response = _client().post(
            "/gateway/sms",
            content=urlencode(params),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                TWILIO_SIGNATURE_HEADER: signature,
            },
        )
        assert response.status_code == 401
        assert stored_reports == []

    def test_twilio_signature_does_not_authenticate_ussd(self, gateway_env, stored_reports) -> None:
        params = _ussd_params()
        response = _client().post(
            "/gateway/ussd",
            content=urlencode(params),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                TWILIO_SIGNATURE_HEADER: expected_twilio_signature(
                    url=USSD_URL, params=params, auth_token=SMS_TOKEN
                ),
            },
        )
        assert response.status_code == 401

    def test_ussd_signature_does_not_authenticate_sms(self, gateway_env, stored_reports) -> None:
        params = _sms_params()
        body = urlencode(params).encode()
        response = _client().post(
            "/gateway/sms",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                SIMULATOR_SIGNATURE_HEADER: expected_simulator_signature(
                    url=SMS_URL, body=body, auth_token=USSD_TOKEN
                ),
            },
        )
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("variable", "post"),
        [
            ("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", "sms"),
            ("PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN", "ussd"),
        ],
    )
    def test_unconfigured_adapter_fails_closed(
        self, monkeypatch, stored_reports, variable, post
    ) -> None:
        monkeypatch.delenv(variable, raising=False)
        get_settings.cache_clear()
        try:
            response = (
                _post_sms(_client(), _sms_params())
                if post == "sms"
                else _post_ussd(_client(), _ussd_params())
            )
        finally:
            get_settings.cache_clear()
        assert response.status_code == 503
        assert stored_reports == []


class TestRequestBoundaries:
    def test_wrong_content_type_is_rejected(self, gateway_env, stored_reports) -> None:
        response = _client().post("/gateway/sms", json=_sms_params())
        assert response.status_code == 415

    def test_oversized_body_is_rejected_before_parsing(self, gateway_env, stored_reports) -> None:
        response = _client().post(
            "/gateway/sms",
            content=b"x" * 9000,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 413

    def test_duplicate_form_keys_are_rejected(self, gateway_env, stored_reports) -> None:
        response = _client().post(
            "/gateway/sms",
            content="Body=help&Body=changed",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("phone", ["01711111111", "+880 1711111111", "+00000000"])
    def test_noncanonical_phone_cannot_evade_rate_limit(
        self, gateway_env, stored_reports, phone
    ) -> None:
        response = _post_sms(_client(), _sms_params(From=phone))
        assert response.status_code == 400


class TestSmsIngestion:
    def test_valid_sms_returns_twiml_and_stores_verified_report(
        self, gateway_env, stored_reports
    ) -> None:
        response = _post_sms(_client(), _sms_params())
        assert response.status_code == 200
        assert response.text == "<Response/>"
        assert response.headers["content-type"].startswith("application/xml")
        assert response.headers["x-protidhoni-ingest-outcome"] == "accepted"
        report = stored_reports[0]
        verify_report_signature(report)
        assert report.priority is None
        assert report.verification.status == "unverified"

    def test_retry_is_duplicate_and_does_not_consume_phone_quota(
        self, gateway_env, stored_reports
    ) -> None:
        client = _client()
        original = _sms_params()
        first = _post_sms(client, original)
        for _ in range(8):
            replay = _post_sms(client, original)
            assert replay.headers["x-protidhoni-ingest-outcome"] == "duplicate"

        # Original consumed one slot; four new reports consume the remaining four.
        for _ in range(4):
            assert _post_sms(client, _sms_params()).status_code == 200
        limited = _post_sms(client, _sms_params())
        assert limited.status_code == 429
        assert len(stored_reports) == 5
        assert first.headers["x-protidhoni-message-id"] == replay.headers["x-protidhoni-message-id"]

    def test_different_phone_has_independent_quota(self, gateway_env, stored_reports) -> None:
        client = _client()
        for _ in range(5):
            assert _post_sms(client, _sms_params()).status_code == 200
        other = _post_sms(client, _sms_params(From="+8801799999999"))
        assert other.status_code == 200

    def test_invalid_twilio_message_id_is_rejected(self, gateway_env, stored_reports) -> None:
        response = _post_sms(_client(), _sms_params(MessageSid="not-a-sid"))
        assert response.status_code == 400


class TestUssdIngestion:
    def test_navigation_returns_plain_con_without_storage(
        self, gateway_env, stored_reports
    ) -> None:
        response = _post_ussd(_client(), _ussd_params())
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text.startswith("CON ")
        assert stored_reports == []

    def test_completed_session_returns_end_and_stores_once(
        self, gateway_env, stored_reports
    ) -> None:
        params = _ussd_params(text="1*1*4*4")
        client = _client()
        first = _post_ussd(client, params)
        replay = _post_ussd(client, params)
        assert first.text.startswith("END ")
        assert first.headers["x-protidhoni-ingest-outcome"] == "accepted"
        assert replay.headers["x-protidhoni-ingest-outcome"] == "duplicate"
        assert len(stored_reports) == 1
        verify_report_signature(stored_reports[0])

    def test_invalid_session_id_is_rejected(self, gateway_env, stored_reports) -> None:
        response = _post_ussd(_client(), _ussd_params(sessionId="bad session id"))
        assert response.status_code == 400


class TestDataMinimisation:
    def test_provider_phone_metadata_never_reaches_report_or_insert_params(
        self, gateway_env, stored_reports, monkeypatch
    ) -> None:
        monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", _fernet_key())
        get_settings.cache_clear()
        _post_sms(_client(), _sms_params())
        report = stored_reports[0]
        serialized_report = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)
        serialized_insert = json.dumps(
            {key: str(value) for key, value in db_module._insert_params(report).items()},
            ensure_ascii=False,
        )
        assert CALLER not in serialized_report
        assert CALLER.lstrip("+") not in serialized_insert

    def test_user_typed_phone_number_remains_report_content(
        self, gateway_env, stored_reports
    ) -> None:
        typed_number = "+8801812345678"
        _post_sms(_client(), _sms_params(Body=f"SOS call my family at {typed_number}"))
        assert typed_number in stored_reports[0].payload.text


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()
