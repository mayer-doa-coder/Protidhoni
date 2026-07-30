"""SMS and offline-USSD-simulator adapters, exercised as real HTTP requests.

Uses the real webhook-signature functions the adapters themselves verify
against, so a passing test proves the same thing a real Twilio callback (or
the offline USSD simulator script) would prove: authentication, parsing,
gateway signing, and idempotent ingestion into the real backend, without
persisting the caller's phone number anywhere.
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlencode

import pytest
from protidhoni_api.gateway_webhook import (
    SIMULATOR_SIGNATURE_HEADER,
    TWILIO_SIGNATURE_HEADER,
    expected_simulator_signature,
    expected_twilio_signature,
)

from conftest import SMS_WEBHOOK_TOKEN, USSD_WEBHOOK_TOKEN

SMS_URL = "http://backend.test/gateway/sms"
USSD_URL = "http://backend.test/gateway/ussd"
CALLER = "+8801711111111"


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


async def _post_sms(client, params, *, token=SMS_WEBHOOK_TOKEN):
    body = urlencode(params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token is not None:
        headers[TWILIO_SIGNATURE_HEADER] = expected_twilio_signature(
            url=SMS_URL, params=params, auth_token=token
        )
    return await client.post("/gateway/sms", content=body, headers=headers)


async def _post_ussd(client, params, *, token=USSD_WEBHOOK_TOKEN):
    body = urlencode(params).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if token is not None:
        headers[SIMULATOR_SIGNATURE_HEADER] = expected_simulator_signature(
            url=USSD_URL, body=body, auth_token=token
        )
    return await client.post("/gateway/ussd", content=body, headers=headers)


@pytest.mark.usefixtures("gateway_env")
class TestSmsAdapter:
    async def test_valid_sms_is_accepted_and_stored_as_a_signed_report(
        self, backend_client, report_store
    ) -> None:
        response = await _post_sms(backend_client, _sms_params())

        assert response.status_code == 200
        assert response.text == "<Response/>"
        assert response.headers["x-protidhoni-ingest-outcome"] == "accepted"

        message_id = response.headers["x-protidhoni-message-id"]
        stored = report_store[message_id]
        assert stored["type"] == "SOS"
        assert stored["payload"]["people_count"] == 4

    async def test_replaying_the_same_message_sid_is_idempotent(
        self, backend_client, report_store
    ) -> None:
        params = _sms_params()

        first = await _post_sms(backend_client, params)
        second = await _post_sms(backend_client, params)

        assert first.headers["x-protidhoni-ingest-outcome"] == "accepted"
        assert second.headers["x-protidhoni-ingest-outcome"] == "duplicate"
        assert first.headers["x-protidhoni-message-id"] == second.headers["x-protidhoni-message-id"]
        assert len(report_store) == 1

    async def test_unsigned_request_is_rejected(self, backend_client, report_store) -> None:
        response = await _post_sms(backend_client, _sms_params(), token=None)

        assert response.status_code == 401
        assert report_store == {}

    async def test_caller_phone_number_never_reaches_storage(
        self, backend_client, report_store
    ) -> None:
        await _post_sms(backend_client, _sms_params())

        serialised = json.dumps(report_store, ensure_ascii=False)
        assert CALLER not in serialised
        assert CALLER.lstrip("+") not in serialised


@pytest.mark.usefixtures("gateway_env")
class TestUssdAdapter:
    async def test_completed_session_is_stored_as_a_signed_report(
        self, backend_client, report_store
    ) -> None:
        response = await _post_ussd(backend_client, _ussd_params(text="1*1*4*4"))

        assert response.status_code == 200
        assert response.text.startswith("END ")
        assert response.headers["x-protidhoni-ingest-outcome"] == "accepted"

        message_id = response.headers["x-protidhoni-message-id"]
        assert report_store[message_id]["type"] == "SOS"

    async def test_menu_navigation_stores_nothing(self, backend_client, report_store) -> None:
        response = await _post_ussd(backend_client, _ussd_params(text=""))

        assert response.text.startswith("CON ")
        assert "x-protidhoni-message-id" not in response.headers
        assert report_store == {}

    async def test_replaying_the_same_session_id_is_idempotent(
        self, backend_client, report_store
    ) -> None:
        params = _ussd_params(text="1*1*4*4")

        first = await _post_ussd(backend_client, params)
        second = await _post_ussd(backend_client, params)

        assert first.headers["x-protidhoni-ingest-outcome"] == "accepted"
        assert second.headers["x-protidhoni-ingest-outcome"] == "duplicate"
        assert len(report_store) == 1

    async def test_wrong_adapter_secret_does_not_authenticate(
        self, backend_client, report_store
    ) -> None:
        # The SMS token must not authenticate the USSD adapter, and vice versa
        # (contracts/README.md: "Adapters authenticate independently").
        response = await _post_ussd(backend_client, _ussd_params(text="1*1*4*4"), token=SMS_WEBHOOK_TOKEN)

        assert response.status_code == 401
        assert report_store == {}


@pytest.mark.usefixtures("gateway_env")
async def test_sms_and_ussd_reports_share_one_gateway_signing_identity(
    backend_client, report_store
) -> None:
    sms_response = await _post_sms(backend_client, _sms_params())
    ussd_response = await _post_ussd(backend_client, _ussd_params(text="1*1*4*4"))

    sms_hash = report_store[sms_response.headers["x-protidhoni-message-id"]]["sender_pubkey_hash"]
    ussd_hash = report_store[ussd_response.headers["x-protidhoni-message-id"]]["sender_pubkey_hash"]
    assert sms_hash == ussd_hash

    health = await backend_client.get("/health")
    assert health.json()["gateway_pubkey_hash"] == sms_hash
