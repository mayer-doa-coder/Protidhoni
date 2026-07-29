from fastapi.testclient import TestClient

from protidhoni_api import routes as routes_module
from protidhoni_api.auth import require_responder_token
from protidhoni_api.db import InstructionConflictError
from protidhoni_api.main import create_app
from protidhoni_api.routes import get_db_pool

from .factories import make_signed_report


def _authorized_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    app.dependency_overrides[require_responder_token] = lambda: None
    return TestClient(app)


def test_queues_a_genuinely_signed_instruction(monkeypatch) -> None:
    instruction = make_signed_report(report_type="INSTRUCTION")
    queued = []

    async def fake_queue(pool, report):
        queued.append(report.message_id)
        return "accepted"

    monkeypatch.setattr(routes_module.db, "queue_instruction", fake_queue)
    with _authorized_client() as client:
        response = client.post("/instructions", json=instruction)

    assert response.status_code == 202
    assert response.json() == {
        "message_id": instruction["message_id"],
        "delivery_status": "queued",
    }
    assert queued == [instruction["message_id"]]


def test_allows_a_signed_safe_route_instruction(monkeypatch) -> None:
    instruction = make_signed_report(report_type="SAFE_ROUTE")

    async def fake_queue(pool, report):
        return "accepted"

    monkeypatch.setattr(routes_module.db, "queue_instruction", fake_queue)
    with _authorized_client() as client:
        response = client.post("/instructions", json=instruction)
    assert response.status_code == 202


def test_rejects_non_instruction_report_types_without_persisting(monkeypatch) -> None:
    async def fake_queue(pool, report):
        raise AssertionError("ordinary reports must not enter the instruction outbox")

    monkeypatch.setattr(routes_module.db, "queue_instruction", fake_queue)
    with _authorized_client() as client:
        response = client.post("/instructions", json=make_signed_report(report_type="SOS"))
    assert response.status_code == 400


def test_rejects_tampered_instruction_without_persisting(monkeypatch) -> None:
    async def fake_queue(pool, report):
        raise AssertionError("invalid signatures must not be persisted")

    monkeypatch.setattr(routes_module.db, "queue_instruction", fake_queue)
    instruction = make_signed_report(report_type="INSTRUCTION", corrupt_signature=True)
    with _authorized_client() as client:
        response = client.post("/instructions", json=instruction)
    assert response.status_code == 400


def test_reports_uuid_content_conflict_as_409(monkeypatch) -> None:
    async def fake_queue(pool, report):
        raise InstructionConflictError("message_id is already used by different report content")

    monkeypatch.setattr(routes_module.db, "queue_instruction", fake_queue)
    instruction = make_signed_report(report_type="INSTRUCTION")
    with _authorized_client() as client:
        response = client.post("/instructions", json=instruction)
    assert response.status_code == 409


def test_instruction_route_denies_by_default_when_responder_auth_is_unset(monkeypatch) -> None:
    monkeypatch.delenv("PROTIDHONI_RESPONDER_TOKEN", raising=False)
    from protidhoni_api.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/instructions", json=make_signed_report(report_type="INSTRUCTION")
            )
    finally:
        get_settings.cache_clear()
    assert response.status_code == 503
