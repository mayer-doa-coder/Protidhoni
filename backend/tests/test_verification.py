import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from protidhoni_api import routes as routes_module
from protidhoni_api.auth import require_responder_token
from protidhoni_api.db import VerificationTransitionError
from protidhoni_api.main import create_app
from protidhoni_api.models import (
    Report,
    VerificationUpdate,
    verification_transition_allowed,
)
from protidhoni_api.routes import get_db_pool

from .factories import make_signed_report


def _authorized_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    app.dependency_overrides[require_responder_token] = lambda: None
    return TestClient(app)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        ("unverified", "corroborated"),
        ("unverified", "verified"),
        ("unverified", "disputed"),
        ("corroborated", "verified"),
        ("corroborated", "disputed"),
        ("verified", "verified"),
        ("disputed", "disputed"),
    ],
)
def test_allows_forward_or_idempotent_verification_transitions(current, requested) -> None:
    assert verification_transition_allowed(current, requested)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        ("corroborated", "unverified"),
        ("verified", "corroborated"),
        ("verified", "disputed"),
        ("disputed", "unverified"),
        ("disputed", "verified"),
    ],
)
def test_rejects_regressive_or_terminal_verification_transitions(current, requested) -> None:
    assert not verification_transition_allowed(current, requested)


def test_verification_update_rejects_unknown_fields_and_explicit_null_note() -> None:
    with pytest.raises(ValidationError):
        VerificationUpdate.model_validate({"status": "verified", "unexpected": True})
    with pytest.raises(ValidationError):
        VerificationUpdate.model_validate({"status": "verified", "responder_note": None})


def test_patch_updates_verification_and_preserves_contract_response(monkeypatch) -> None:
    raw = make_signed_report(verification={"status": "verified", "corroboration_count": 0})
    updated_report = Report.model_validate(raw).model_copy(update={"sync_status": "synced"})
    calls = []

    async def fake_update(pool, **values):
        calls.append(values)
        return updated_report

    monkeypatch.setattr(routes_module.db, "update_report_verification", fake_update)

    with _authorized_client() as client:
        response = client.patch(
            f"/reports/{raw['message_id']}",
            json={"status": "verified", "responder_note": "Confirmed by field team"},
        )

    assert response.status_code == 200
    assert response.json()["verification"]["status"] == "verified"
    assert calls == [
        {
            "message_id": raw["message_id"],
            "status": "verified",
            "responder_note": "Confirmed by field team",
            "note_was_provided": True,
        }
    ]


def test_patch_returns_404_for_unknown_report(monkeypatch) -> None:
    async def fake_update(pool, **values):
        return None

    monkeypatch.setattr(routes_module.db, "update_report_verification", fake_update)
    message_id = make_signed_report()["message_id"]
    with _authorized_client() as client:
        response = client.patch(f"/reports/{message_id}", json={"status": "verified"})
    assert response.status_code == 404


def test_patch_returns_409_for_invalid_transition(monkeypatch) -> None:
    async def fake_update(pool, **values):
        raise VerificationTransitionError("verified", "disputed")

    monkeypatch.setattr(routes_module.db, "update_report_verification", fake_update)
    message_id = make_signed_report()["message_id"]
    with _authorized_client() as client:
        response = client.patch(f"/reports/{message_id}", json={"status": "disputed"})
    assert response.status_code == 409
