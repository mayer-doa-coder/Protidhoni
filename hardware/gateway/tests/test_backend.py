from __future__ import annotations

import json

import httpx
import pytest

from protidhoni_lora_gateway.backend import (
    BackendClient,
    BackendRejectedError,
    PermanentBackendError,
    TemporaryBackendError,
)


def _response(request: httpx.Request, status: int, document: object) -> httpx.Response:
    return httpx.Response(status, json=document, request=request)


@pytest.mark.parametrize("outcome", ["accepted", "duplicate"])
def test_backend_client_submits_the_existing_batch_shape(signed_report: dict, outcome: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(
            request,
            202,
            {"results": [{"message_id": signed_report["message_id"], "outcome": outcome}]},
        )

    client = BackendClient(
        base_url="http://backend.test",
        timeout_seconds=1,
        attempts=1,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.submit(signed_report) == outcome
    finally:
        client.close()

    assert len(requests) == 1
    assert requests[0].url == httpx.URL("http://backend.test/reports")
    assert json.loads(requests[0].content) == {"reports": [signed_report]}
    assert "X-Responder-Token" not in requests[0].headers


def test_backend_client_retries_transient_failure_then_succeeds(signed_report: dict) -> None:
    statuses = [503, 202]
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        document = (
            {"results": [{"message_id": signed_report["message_id"], "outcome": "accepted"}]}
            if status == 202
            else {"detail": "unavailable"}
        )
        return _response(request, status, document)

    client = BackendClient(
        base_url="http://backend.test",
        timeout_seconds=1,
        attempts=2,
        retry_delay_seconds=0.25,
        sleeper=sleeps.append,
        transport=httpx.MockTransport(handler),
    )
    try:
        assert client.submit(signed_report) == "accepted"
    finally:
        client.close()
    assert sleeps == [0.25]


def test_backend_outage_is_temporary_and_does_not_echo_report(signed_report: dict) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = BackendClient(
        base_url="http://backend.test",
        timeout_seconds=1,
        attempts=2,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(TemporaryBackendError) as caught:
            client.submit(signed_report)
    finally:
        client.close()
    assert signed_report["payload"]["text"] not in str(caught.value)
    assert signed_report["sender_pubkey"] not in str(caught.value)


def test_backend_rejected_outcome_is_not_retried(signed_report: dict) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _response(
            request,
            202,
            {"results": [{"message_id": signed_report["message_id"], "outcome": "rejected"}]},
        )

    client = BackendClient(
        base_url="http://backend.test",
        timeout_seconds=1,
        attempts=3,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(BackendRejectedError):
            client.submit(signed_report)
    finally:
        client.close()
    assert calls == 1


@pytest.mark.parametrize(
    "status, document",
    [
        (400, {"detail": "invalid"}),
        (202, {"results": []}),
        (202, {"results": [{"message_id": "wrong", "outcome": "accepted"}]}),
        (202, {"results": [{"message_id": "ignored", "outcome": "unknown"}]}),
    ],
)
def test_permanent_or_invalid_backend_responses_fail_closed(
    signed_report: dict, status: int, document: object
) -> None:
    if status == 202 and isinstance(document, dict) and document.get("results"):
        result = document["results"][0]
        if result["message_id"] == "ignored":
            result["message_id"] = signed_report["message_id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return _response(request, status, document)

    client = BackendClient(
        base_url="http://backend.test",
        timeout_seconds=1,
        attempts=1,
        retry_delay_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PermanentBackendError):
            client.submit(signed_report)
    finally:
        client.close()
