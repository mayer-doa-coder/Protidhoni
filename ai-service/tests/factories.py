import uuid
from datetime import UTC, datetime


def make_report(
    *,
    text: str,
    report_type: str = "SOS",
    language: str = "bn",
    people_count: int | None = None,
    needs: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "1.0.0",
        "message_id": str(uuid.uuid4()),
        "type": report_type,
        "sender_pubkey": "A" * 43,
        "sender_pubkey_hash": "B" * 43,
        "created_at": datetime.now(UTC).isoformat(),
        "language": language,
        "location": {
            "lat": None,
            "lng": None,
            "accuracy_m": None,
            "source": "none",
        },
        "payload": {
            "text": text,
            "people_count": people_count,
            "needs": needs or [],
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": 8,
        "signature": {"algorithm": "Ed25519", "value": "C" * 86},
        "relay_path": [],
        "sync_status": "local",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }
