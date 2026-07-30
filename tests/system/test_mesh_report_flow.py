"""Mesh-style report ingestion through the real backend, end to end.

Everything here is real: protidhoni_api.main.create_app(), real Pydantic
validation against contracts/message-schema.json's Python model, real Ed25519
signature verification (protidhoni_api.crypto), real idempotency and rate
limiting. Only the Postgres write is a fixture (see conftest.py).
"""

from __future__ import annotations


async def test_signed_report_is_accepted_and_round_trips(backend_client, signer, report_store):
    report = signer.build(
        report_type="SOS",
        language="bn",
        text="পানি এবং উদ্ধার দরকার, ৫ জন আটকা পড়েছি।",
        people_count=5,
        needs=["water", "rescue"],
        location={"lat": 23.8103, "lng": 90.4125, "accuracy_m": 8.0, "source": "gps"},
    )

    ingest_response = await backend_client.post("/reports", json={"reports": [report]})
    assert ingest_response.status_code == 202
    body = ingest_response.json()
    assert body["results"] == [{"message_id": report["message_id"], "outcome": "accepted"}]

    listed = await backend_client.get("/reports")
    assert listed.status_code == 200
    stored = next(r for r in listed.json()["reports"] if r["message_id"] == report["message_id"])
    assert stored["payload"]["text"] == report["payload"]["text"]
    assert stored["payload"]["people_count"] == 5
    assert stored["location"]["lat"] == 23.8103
    # A batch submission must not lose the caller's identity fields.
    assert stored["sender_pubkey_hash"] == signer.pubkey_hash_b64
    assert report_store[report["message_id"]]["sender_pubkey_hash"] == signer.pubkey_hash_b64


async def test_resubmission_is_idempotent_not_duplicated(backend_client, signer):
    report = signer.build()

    first = await backend_client.post("/reports", json={"reports": [report]})
    second = await backend_client.post("/reports", json={"reports": [report]})

    assert first.json()["results"][0]["outcome"] == "accepted"
    assert second.json()["results"][0]["outcome"] == "duplicate"

    listed = await backend_client.get("/reports")
    matches = [r for r in listed.json()["reports"] if r["message_id"] == report["message_id"]]
    assert len(matches) == 1


async def test_tampered_payload_is_rejected_not_silently_stored(backend_client, signer):
    report = signer.build(text="original, unmodified text")
    # A relay or a malicious intermediary rewrote the text after signing.
    report["payload"]["text"] = "an injected claim the sender never made"

    response = await backend_client.post("/reports", json={"reports": [report]})

    assert response.status_code == 202  # the batch itself is well-formed JSON
    assert response.json()["results"][0]["outcome"] == "rejected"

    listed = await backend_client.get("/reports")
    assert all(r["message_id"] != report["message_id"] for r in listed.json()["reports"])


async def test_wrong_pubkey_hash_is_rejected(backend_client, signer):
    report = signer.build()
    # sender_pubkey_hash must equal SHA-256(sender_pubkey); corrupt it.
    report["sender_pubkey_hash"] = "A" * 43

    response = await backend_client.post("/reports", json={"reports": [report]})

    assert response.json()["results"][0]["outcome"] == "rejected"


async def test_a_batch_of_independent_reports_is_all_accepted(backend_client, signer):
    reports = [signer.build(message_id=None) for _ in range(5)]

    response = await backend_client.post("/reports", json={"reports": reports})

    assert response.status_code == 202
    outcomes = {r["outcome"] for r in response.json()["results"]}
    assert outcomes == {"accepted"}
    assert len(response.json()["results"]) == 5


async def test_stored_shape_carries_every_field_the_dashboard_type_requires(
    backend_client, signer
):
    """dashboard/src/api.ts's CrisisReport type requires these exact keys.

    This is the one place that would catch a field renamed on the backend
    without the dashboard's TypeScript type being updated to match — neither
    project's own test suite can see the other's expectations.
    """
    report = signer.build()
    await backend_client.post("/reports", json={"reports": [report]})

    listed = await backend_client.get("/reports")
    stored = next(r for r in listed.json()["reports"] if r["message_id"] == report["message_id"])

    required_top_level = {
        "schema_version", "message_id", "type", "sender_pubkey_hash", "created_at",
        "language", "location", "payload", "priority", "ttl_hops", "relay_path",
        "sync_status", "verification",
    }
    assert required_top_level <= stored.keys()
    assert {"lat", "lng", "accuracy_m", "source"} <= stored["location"].keys()
    assert {"text", "people_count", "needs", "attachment_ref"} <= stored["payload"].keys()
    assert {"status", "corroboration_count"} <= stored["verification"].keys()
