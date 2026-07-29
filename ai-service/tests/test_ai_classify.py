from fastapi.testclient import TestClient

from protidhoni_ai.main import create_app
from protidhoni_ai.settings import Settings

from .factories import make_report


def make_client() -> TestClient:
    return TestClient(create_app(Settings(ai_internal_token="test-token")))


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
        headers={"X-Internal-Service-Token": "test-token"},
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
        headers={"X-Internal-Service-Token": "test-token"},
        json={"type": "SOS", "payload": {"text": "help"}},
    )

    assert response.status_code == 422


def test_classify_rejects_inconsistent_location_from_the_frozen_envelope() -> None:
    report = make_report(text="Need rescue now", language="en")
    report["location"] = {"lat": 23.8, "lng": 90.4, "accuracy_m": 5, "source": "none"}

    response = make_client().post(
        "/ai/classify",
        headers={"X-Internal-Service-Token": "test-token"},
        json=report,
    )

    assert response.status_code == 422
