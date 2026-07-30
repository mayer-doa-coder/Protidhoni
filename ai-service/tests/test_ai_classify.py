import json
from io import BytesIO
from typing import Self
from unittest.mock import patch

from fastapi.testclient import TestClient

from protidhoni_ai.main import create_app
from protidhoni_ai.settings import Settings

from .factories import make_report

INTERNAL_TOKEN = "t" * 32


class FakeTranslationResponse:
    def __init__(self, body: dict) -> None:
        self._body = BytesIO(json.dumps(body).encode("utf-8"))

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args) -> None:
        return None


def make_client() -> TestClient:
    return TestClient(create_app(Settings(ai_internal_token=INTERNAL_TOKEN)))


def test_classify_requires_the_internal_service_token() -> None:
    response = make_client().post(
        "/ai/classify", json=make_report(text="Need rescue now", language="en")
    )

    assert response.status_code == 401


def test_classify_is_unavailable_when_the_service_token_is_not_configured() -> None:
    response = TestClient(create_app(Settings(ai_internal_token=None))).post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": "anything"},
        json=make_report(text="Need rescue now", language="en"),
    )

    assert response.status_code == 503


def test_classify_rejects_a_blank_internal_service_token_configuration() -> None:
    response = TestClient(create_app(Settings(ai_internal_token="   "))).post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": "anything"},
        json=make_report(text="Need rescue now", language="en"),
    )

    assert response.status_code == 503


def test_classify_returns_the_frozen_response_shape() -> None:
    response = make_client().post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
        json=make_report(text="Severe bleeding, doctor needed", language="en"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "type": "MEDICAL_NEED",
        "needs": ["medical"],
        "priority": "critical",
        "model": "phase1-tfidf-rules-v1",
    }


def test_classify_rejects_an_incomplete_non_contract_request() -> None:
    response = make_client().post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
        json={"type": "SOS", "payload": {"text": "help"}},
    )

    assert response.status_code == 400


def test_classify_rejects_inconsistent_location_from_the_frozen_envelope() -> None:
    report = make_report(text="Need rescue now", language="en")
    report["location"] = {"lat": 23.8, "lng": 90.4, "accuracy_m": 5, "source": "none"}

    response = make_client().post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
        json=report,
    )

    assert response.status_code == 400


def test_translate_requires_internal_token_before_provider_access() -> None:
    client = TestClient(
        create_app(
            Settings(
                ai_internal_token=INTERNAL_TOKEN,
                translation_base_url="http://translator.test",
            )
        )
    )
    with patch("protidhoni_ai.translation.urlopen") as provider_request:
        response = client.post(
            "/ai/translate",
            json={
                "text": "জরুরি সাহায্য",
                "source_language": "bn",
                "target_language": "en",
            },
        )

    assert response.status_code == 401
    provider_request.assert_not_called()


def test_translate_returns_the_frozen_internal_response_shape() -> None:
    client = TestClient(
        create_app(
            Settings(
                ai_internal_token=INTERNAL_TOKEN,
                translation_base_url="http://translator.test",
            )
        )
    )
    with patch(
        "protidhoni_ai.translation.urlopen",
        return_value=FakeTranslationResponse(
            {"translatedText": "Emergency assistance"}
        ),
    ) as provider_request:
        response = client.post(
            "/ai/translate",
            headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
            json={
                "text": "জরুরি সাহায্য",
                "source_language": "bn",
                "target_language": "en",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "Emergency assistance",
        "source_language": "bn",
        "target_language": "en",
        "provider": "libretranslate",
    }
    assert json.loads(provider_request.call_args.args[0].data) == {
        "q": "জরুরি সাহায্য",
        "source": "bn",
        "target": "en",
        "format": "text",
    }


def test_translate_fails_closed_when_no_provider_or_valid_text_is_available() -> None:
    unavailable_client = TestClient(
        create_app(Settings(ai_internal_token=INTERNAL_TOKEN))
    )
    unavailable = unavailable_client.post(
        "/ai/translate",
        headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
        json={"text": "জরুরি সাহায্য", "source_language": "bn", "target_language": "en"},
    )
    blank = make_client().post(
        "/ai/translate",
        headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
        json={"text": "   ", "source_language": "bn", "target_language": "en"},
    )

    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "Translation is temporarily unavailable."}
    assert blank.status_code == 400


def test_translate_fails_closed_when_provider_output_breaks_the_contract() -> None:
    client = TestClient(
        create_app(
            Settings(
                ai_internal_token=INTERNAL_TOKEN,
                translation_base_url="http://translator.test",
            )
        )
    )
    with patch(
        "protidhoni_ai.translation.urlopen",
        return_value=FakeTranslationResponse({"translatedText": "x" * 4001}),
    ):
        response = client.post(
            "/ai/translate",
            headers={"X-Internal-Service-Token": INTERNAL_TOKEN},
            json={
                "text": "জরুরি সাহায্য",
                "source_language": "bn",
                "target_language": "en",
            },
        )

    assert response.status_code == 503


def test_ai_openapi_declares_internal_translation_security() -> None:
    spec = create_app(Settings(ai_internal_token=INTERNAL_TOKEN)).openapi()

    assert spec["paths"]["/ai/translate"]["post"]["security"] == [
        {"InternalServiceToken": []}
    ]
