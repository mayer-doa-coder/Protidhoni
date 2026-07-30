"""Backend's translation client against the real, independently built ai-service app.

Both sides are real: backend/src/protidhoni_api/translation.py's HTTP client
and Pydantic response model, and ai-service/src/protidhoni_ai/main.py's real
FastAPI routing, real internal-token auth, and real InternalTranslationRequest/
Response schemas. They run as two separate ASGI apps in one process, connected
by httpx.ASGITransport — genuinely two codebases talking over HTTP, without a
real socket or a real third-party translation provider.

`request_ai_translation`'s success path is proven through the provider's own
identity shortcut (source_language == target_language returns the input text
unchanged with provider="identity", with no outbound network call) rather than
a live LibreTranslate instance, which this environment does not have. That is
disclosed here, not hidden: it proves the auth, routing, and schema contract
genuinely round-trip between two real codebases, not translation quality.
"""

from __future__ import annotations

import httpx
import pytest

INTERNAL_TOKEN = "t" * 32


def _ai_service_app(monkeypatch, *, translation_base_url: str | None):
    monkeypatch.setenv("PROTIDHONI_AI_INTERNAL_TOKEN", INTERNAL_TOKEN)
    if translation_base_url is None:
        monkeypatch.delenv("PROTIDHONI_TRANSLATION_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("PROTIDHONI_TRANSLATION_BASE_URL", translation_base_url)

    from protidhoni_ai.settings import get_settings

    get_settings.cache_clear()
    from protidhoni_ai.main import create_app

    app = create_app()
    get_settings.cache_clear()
    return app


@pytest.fixture
def ai_service_client_factory(monkeypatch):
    def _make(*, translation_base_url: str | None):
        app = _ai_service_app(monkeypatch, translation_base_url=translation_base_url)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://ai-service.test"
        )

    return _make


async def test_identity_translation_round_trips_through_two_real_apps(
    ai_service_client_factory,
):
    """source_language == target_language never calls a provider, so this
    proves the real auth header, real request/response schemas, and real
    routing between backend's client and ai-service's endpoint, deterministically.
    """
    from protidhoni_api.translation import request_ai_translation

    async with ai_service_client_factory(translation_base_url="http://unused.test") as client:
        result = await request_ai_translation(
            base_url="http://ai-service.test",
            internal_token=INTERNAL_TOKEN,
            text="আমরা নিরাপদ",
            source_language="bn",
            target_language="bn",
            client=client,
        )

    assert result.text == "আমরা নিরাপদ"
    assert result.source_language == "bn"
    assert result.target_language == "bn"
    assert result.provider == "identity"


async def test_unconfigured_translation_provider_fails_closed_across_the_real_boundary(
    ai_service_client_factory,
):
    from protidhoni_api.translation import (
        TranslationUnavailable,
        request_ai_translation,
    )

    async with ai_service_client_factory(translation_base_url=None) as client:
        with pytest.raises(TranslationUnavailable):
            await request_ai_translation(
                base_url="http://ai-service.test",
                internal_token=INTERNAL_TOKEN,
                text="need water",
                source_language="en",
                target_language="bn",
                client=client,
            )


async def test_wrong_internal_token_is_treated_as_unavailable_not_leaked(
    ai_service_client_factory,
):
    """Backend must not distinguish 'ai-service rejected our credential' from
    'ai-service is down' to the responder — see contracts/README.md's
    "Translation failures fail closed" rule.
    """
    from protidhoni_api.translation import (
        TranslationUnavailable,
        request_ai_translation,
    )

    async with ai_service_client_factory(translation_base_url="http://unused.test") as client:
        with pytest.raises(TranslationUnavailable):
            await request_ai_translation(
                base_url="http://ai-service.test",
                internal_token="wrong-token-wrong-token-wrong-t",
                text="need water",
                source_language="en",
                target_language="bn",
                client=client,
            )


async def test_ai_service_health_is_reachable_over_the_same_real_app(
    ai_service_client_factory,
):
    async with ai_service_client_factory(translation_base_url=None) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "ai-service"
