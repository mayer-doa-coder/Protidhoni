"""HTTP-layer tests for POST/GET /reports with the DB layer mocked out.

These deliberately do not touch a real database — they verify request
validation, signature/rate-limit enforcement, and response shaping, which are
all pure logic independent of persistence. See test_reports_integration.py
for the real-Postgres coverage of db.insert_report/db.list_reports themselves.
"""

from fastapi.testclient import TestClient

from protidhoni_api import routes as routes_module
from protidhoni_api.main import create_app
from protidhoni_api.ratelimit import SenderRateLimiter
from protidhoni_api.routes import get_db_pool

from .factories import make_signed_report


def _make_client():
    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    return TestClient(app)


def test_ingest_accepts_a_genuinely_signed_report(monkeypatch) -> None:
    inserted = []

    async def fake_insert_report(pool, report):
        inserted.append(report.message_id)
        return "accepted"

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    report = make_signed_report()
    with _make_client() as client:
        response = client.post("/reports", json={"reports": [report]})

    assert response.status_code == 202
    assert response.json() == {"results": [{"message_id": report["message_id"], "outcome": "accepted"}]}
    assert inserted == [report["message_id"]]


def test_ingest_rejects_a_tampered_signature_without_persisting(monkeypatch) -> None:
    async def fake_insert_report(pool, report):
        raise AssertionError("a report with an invalid signature must never be persisted")

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    report = make_signed_report(corrupt_signature=True)
    with _make_client() as client:
        response = client.post("/reports", json={"reports": [report]})

    assert response.status_code == 202
    assert response.json()["results"] == [{"message_id": report["message_id"], "outcome": "rejected"}]


def test_ingest_rejects_a_pubkey_hash_mismatch_without_persisting(monkeypatch) -> None:
    async def fake_insert_report(pool, report):
        raise AssertionError("a report with a mismatched pubkey hash must never be persisted")

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    report = make_signed_report(wrong_pubkey_hash=True)
    with _make_client() as client:
        response = client.post("/reports", json={"reports": [report]})

    assert response.status_code == 202
    assert response.json()["results"][0]["outcome"] == "rejected"


def test_ingest_passes_through_duplicate_outcome(monkeypatch) -> None:
    async def fake_insert_report(pool, report):
        return "duplicate"

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    report = make_signed_report()
    with _make_client() as client:
        response = client.post("/reports", json={"reports": [report]})

    assert response.json()["results"][0]["outcome"] == "duplicate"


def test_ingest_handles_one_bad_report_among_many_good_ones(monkeypatch) -> None:
    accepted_ids = []

    async def fake_insert_report(pool, report):
        accepted_ids.append(report.message_id)
        return "accepted"

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    good_one = make_signed_report()
    bad_one = make_signed_report(corrupt_signature=True)
    good_two = make_signed_report()

    with _make_client() as client:
        response = client.post("/reports", json={"reports": [good_one, bad_one, good_two]})

    assert response.status_code == 202
    outcomes = {r["message_id"]: r["outcome"] for r in response.json()["results"]}
    assert outcomes[good_one["message_id"]] == "accepted"
    assert outcomes[bad_one["message_id"]] == "rejected"
    assert outcomes[good_two["message_id"]] == "accepted"
    assert set(accepted_ids) == {good_one["message_id"], good_two["message_id"]}


def test_ingest_empty_batch_is_a_400_not_a_500() -> None:
    with _make_client() as client:
        response = client.post("/reports", json={"reports": []})
    assert response.status_code == 400


def test_ingest_structurally_invalid_report_is_a_400() -> None:
    report = make_signed_report()
    del report["signature"]
    with _make_client() as client:
        response = client.post("/reports", json={"reports": [report]})
    assert response.status_code == 400


def test_ingest_enforces_the_per_sender_rate_limit(monkeypatch) -> None:
    monkeypatch.setattr(routes_module, "_sender_limiter", SenderRateLimiter(max_reports_per_minute=3))

    async def fake_insert_report(pool, report):
        return "accepted"

    monkeypatch.setattr(routes_module.db, "insert_report", fake_insert_report)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    outcomes = []
    with _make_client() as client:
        for _ in range(5):
            report = make_signed_report(private_key=key)
            response = client.post("/reports", json={"reports": [report]})
            outcomes.append(response.json()["results"][0]["outcome"])

    assert outcomes == ["accepted", "accepted", "accepted", "rejected", "rejected"]


def test_get_reports_rejects_bbox_out_of_wgs84_range() -> None:
    with _make_client() as client:
        response = client.get("/reports", params={"bbox": "200,10,190,20"})
    assert response.status_code == 400


def test_get_reports_rejects_inverted_bbox() -> None:
    with _make_client() as client:
        response = client.get("/reports", params={"bbox": "90,20,80,10"})
    assert response.status_code == 400


def test_get_reports_rejects_malformed_since() -> None:
    with _make_client() as client:
        response = client.get("/reports", params={"since": "not-a-date"})
    assert response.status_code == 400


def test_get_reports_returns_the_mocked_page(monkeypatch) -> None:
    async def fake_list_reports(pool, *, since, bbox, limit):
        assert bbox == (90.0, 20.0, 91.0, 21.0)
        assert limit == 50
        return {"reports": [], "next_since": None}

    monkeypatch.setattr(routes_module.db, "list_reports", fake_list_reports)

    with _make_client() as client:
        response = client.get("/reports", params={"bbox": "90,20,91,21", "limit": 50})

    assert response.status_code == 200
    assert response.json() == {"reports": [], "next_since": None}


def test_reports_endpoints_503_without_a_configured_database() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/reports")
    assert response.status_code == 503
