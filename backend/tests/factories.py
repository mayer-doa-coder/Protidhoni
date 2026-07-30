"""Test-only helpers for building genuinely signed reports.

Not shipped as part of the API surface; imported directly by tests. Building
a real Ed25519 keypair and signing the canonical subset here (rather than
hand-crafting a plausible-looking dict) means these tests exercise the exact
same signing rule contracts/README.md documents for real client code, not a
convenient fake.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_SIGNED_SUBSET_KEYS = (
    "schema_version",
    "message_id",
    "type",
    "sender_pubkey",
    "sender_pubkey_hash",
    "created_at",
    "language",
    "location",
    "payload",
)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_signed_report(
    *,
    private_key: Ed25519PrivateKey | None = None,
    message_id: str | None = None,
    report_type: str = "SOS",
    created_at: str | None = None,
    language: str = "bn",
    location: dict | None = None,
    payload: dict | None = None,
    priority: str | None = None,
    ttl_hops: int = 5,
    relay_path: list[str] | None = None,
    sync_status: str = "local",
    verification: dict | None = None,
    corrupt_signature: bool = False,
    wrong_pubkey_hash: bool = False,
) -> dict:
    key = private_key or Ed25519PrivateKey.generate()
    public_key_raw = key.public_key().public_bytes_raw()
    pubkey_b64 = b64url(public_key_raw)
    pubkey_hash_b64 = b64url(hashlib.sha256(public_key_raw).digest())
    if wrong_pubkey_hash:
        other_raw = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        pubkey_hash_b64 = b64url(hashlib.sha256(other_raw).digest())

    report: dict = {
        "schema_version": "1.0.0",
        "message_id": message_id or str(uuid.uuid4()),
        "type": report_type,
        "sender_pubkey": pubkey_b64,
        "sender_pubkey_hash": pubkey_hash_b64,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "language": language,
        "location": location
        if location is not None
        else {"lat": 23.81, "lng": 90.41, "accuracy_m": 5.0, "source": "gps"},
        "payload": payload
        if payload is not None
        else {
            "text": "সাহায্য দরকার",
            "people_count": 2,
            "needs": ["water"],
            "attachment_ref": None,
        },
    }

    signed_subset = {key_name: report[key_name] for key_name in _SIGNED_SUBSET_KEYS}
    canonical_bytes = rfc8785.dumps(signed_subset)
    signature_bytes = bytearray(key.sign(canonical_bytes))
    if corrupt_signature:
        signature_bytes[0] ^= 0xFF

    report.update(
        {
            "priority": priority,
            "ttl_hops": ttl_hops,
            "signature": {"algorithm": "Ed25519", "value": b64url(bytes(signature_bytes))},
            "relay_path": relay_path or [],
            "sync_status": sync_status,
            "verification": verification or {"status": "unverified", "corroboration_count": 0},
        }
    )
    return report
