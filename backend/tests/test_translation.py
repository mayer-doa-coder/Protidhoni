"""Translation route and internal-client safety tests."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from protidhoni_api import routes as routes_module
from protidhoni_api import translation
from protidhoni_api.auth import require_responder_token
from protidhoni_api.config import get_settings
from protidhoni_api.main import create_app
from protidhoni_api.models import Report
from protidhoni_api.routes import get_db_pool

from .factories import make_signed_report


def _authorized_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    app.dependency_overrides[require_responder_token] = lambda: None
    return TestClient(app)


def test_translation_reads_stored_text_and_never_uses_client_supplied_text(monkeypatch) -> None:
    raw = make_signed_report(
        language="bn",
        payload={"text": "মূল রিপোর্ট", "people_count": 1, "needs": [], "attachment_ref": None},
    )
    stored_report = Report.model_validate(raw).model_copy(update={"sync_status": "synced"})
    database_calls: list[str] = []
    ai_calls: list[dict] = []

    async def fake_get_report(pool, *, message_id):
        database_calls.append(message_id)
        return stored_report

    async def fake_request_ai_translation(**kwargs):
        ai_calls.append(kwargs)
        return translation.InternalTranslationResponse(
            text="Original report",
            source_language="bn",
            target_language="en",
            provider="libretranslate",
        )

    monkeypatch.setattr(routes_module.db, "get_report", fake_get_report)
    monkeypatch.setattr(
        routes_module.translation, "request_ai_translation", fake_request_ai_translation
    )
    with _authorized_client() as client:
        response = client.post(
            "/translations",
            json={"message_id": raw["message_id"], "target_language": "en"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "message_id": raw["message_id"],
        "source_language": "bn",
        "target_language": "en",
        "text": "Original report",
        "provider": "libretranslate",
    }
    assert database_calls == [raw["message_id"]]
    assert ai_calls[0]["text"] == "মূল রিপোর্ট"
    assert ai_calls[0]["source_language"] == "bn"
    assert ai_calls[0]["target_language"] == "en"


def test_translation_rejects_raw_browser_text_before_database_access(monkeypatch) -> None:
    async def fake_get_report(pool, *, message_id):
        raise AssertionError("invalid public translation input must not query reports")

    monkeypatch.setattr(routes_module.db, "get_report", fake_get_report)
    with _authorized_client() as client:
        response = client.post(
            "/translations",
            json={
                "message_id": make_signed_report()["message_id"],
                "target_language": "en",
                "text": "forged",
            },
        )

    assert response.status_code == 400


def test_translation_denies_by_default_when_responder_auth_is_unset(monkeypatch) -> None:
    # An explicit blank environment variable overrides any developer .env file.
    monkeypatch.setenv("PROTIDHONI_RESPONDER_TOKEN", "")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/translations",
                json={"message_id": make_signed_report()["message_id"], "target_language": "en"},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 503


def test_translation_returns_404_without_calling_ai_for_unknown_report(monkeypatch) -> None:
    async def fake_get_report(pool, *, message_id):
        return None

    async def fake_request_ai_translation(**kwargs):
        raise AssertionError("unknown reports must never be sent to the AI service")

    monkeypatch.setattr(routes_module.db, "get_report", fake_get_report)
    monkeypatch.setattr(
        routes_module.translation, "request_ai_translation", fake_request_ai_translation
    )
    with _authorized_client() as client:
        response = client.post(
            "/translations",
            json={"message_id": make_signed_report()["message_id"], "target_language": "en"},
        )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (
            translation.TranslationUnavailable("provider secret"),
            503,
            "Translation is temporarily unavailable.",
        ),
        (
            translation.TranslationProtocolError("bad provider body"),
            502,
            "Translation service returned an invalid response.",
        ),
    ],
)
def test_translation_hides_internal_errors(monkeypatch, error, status_code, detail) -> None:
    raw = make_signed_report()
    stored_report = Report.model_validate(raw)

    async def fake_get_report(pool, *, message_id):
        return stored_report

    async def fake_request_ai_translation(**kwargs):
        raise error

    monkeypatch.setattr(routes_module.db, "get_report", fake_get_report)
    monkeypatch.setattr(
        routes_module.translation, "request_ai_translation", fake_request_ai_translation
    )
    with _authorized_client() as client:
        response = client.post(
            "/translations",
            json={"message_id": raw["message_id"], "target_language": "en"},
        )

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_internal_translation_client_sends_only_expected_body_and_token() -> None:
    sent_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append(request)
        return httpx.Response(
            200,
            json={
                "text": "Emergency assistance",
                "source_language": "bn",
                "target_language": "en",
                "provider": "libretranslate",
            },
        )

    async def run() -> translation.InternalTranslationResponse:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await translation.request_ai_translation(
                base_url="http://ai-service:8001",
                internal_token="a" * 32,
                text="জরুরি সাহায্য",
                source_language="bn",
                target_language="en",
                client=client,
            )

    result = asyncio.run(run())
    assert result.text == "Emergency assistance"
    assert sent_requests[0].url == "http://ai-service:8001/ai/translate"
    assert sent_requests[0].headers["X-Internal-Service-Token"] == "a" * 32
    assert json.loads(sent_requests[0].content) == {
        "text": "জরুরি সাহায্য",
        "source_language": "bn",
        "target_language": "en",
    }


def test_internal_translation_client_rejects_mismatched_or_unavailable_responses() -> None:
    async def mismatch_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "text": "Emergency assistance",
                "source_language": "en",
                "target_language": "en",
                "provider": "libretranslate",
            },
        )

    async def run_mismatch() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(mismatch_handler)) as client:
            await translation.request_ai_translation(
                base_url="http://ai-service:8001",
                internal_token="a" * 32,
                text="জরুরি সাহায্য",
                source_language="bn",
                target_language="en",
                client=client,
            )

    with pytest.raises(translation.TranslationProtocolError, match="mismatched languages"):
        asyncio.run(run_mismatch())

    async def run_unconfigured() -> None:
        await translation.request_ai_translation(
            base_url="http://ai-service:8001",
            internal_token=None,
            text="জরুরি সাহায্য",
            source_language="bn",
            target_language="en",
        )

    with pytest.raises(translation.TranslationUnavailable, match="credentials"):
        asyncio.run(run_unconfigured())
