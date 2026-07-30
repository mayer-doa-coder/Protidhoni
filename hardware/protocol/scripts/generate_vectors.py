"""Generate or verify the deterministic Phase 5A golden vectors.

The embedded Ed25519 seeds are intentionally public test material. They are not
deployment credentials.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from protidhoni_lora_protocol import (
    APPLICATION_PORT,
    CHUNK_SIZE,
    FRAME_HEADER_SIZE,
    FRAME_VERSION,
    MAX_APPLICATION_PAYLOAD,
    MAX_FRAGMENT_COUNT,
    MAX_REPORT_SIZE,
    canonical_report_bytes,
    encode_report,
)

SIGNED_KEYS = (
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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _signed_report(
    *,
    seed_hex: str,
    message_id: str,
    report_type: str,
    created_at: str,
    language: str,
    location: dict[str, Any],
    text: str,
    people_count: int | None,
    needs: list[str],
) -> dict[str, Any]:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    public_key = private_key.public_key().public_bytes_raw()
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "message_id": message_id,
        "type": report_type,
        "sender_pubkey": _b64url(public_key),
        "sender_pubkey_hash": _b64url(hashlib.sha256(public_key).digest()),
        "created_at": created_at,
        "language": language,
        "location": location,
        "payload": {
            "text": text,
            "people_count": people_count,
            "needs": needs,
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": 5,
        "signature": {"algorithm": "Ed25519", "value": ""},
        "relay_path": [],
        "sync_status": "local",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }
    signed_subset = {key: report[key] for key in SIGNED_KEYS}
    report["signature"]["value"] = _b64url(private_key.sign(rfc8785.dumps(signed_subset)))
    return report


def _vector(name: str, report: dict[str, Any]) -> dict[str, Any]:
    _, payload = canonical_report_bytes(report)
    frames = encode_report(report)
    return {
        "name": name,
        "report": report,
        "canonical_payload_base64": base64.b64encode(payload).decode("ascii"),
        "canonical_payload_length": len(payload),
        "payload_sha256_hex": hashlib.sha256(payload).hexdigest(),
        "frame_lengths": [len(frame) for frame in frames],
        "frames_base64": [base64.b64encode(frame).decode("ascii") for frame in frames],
    }


def generate() -> bytes:
    reports = [
        (
            "bangla-sos-gps",
            _signed_report(
                seed_hex="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
                message_id="123e4567-e89b-42d3-a456-426614174000",
                report_type="SOS",
                created_at="2026-07-30T09:15:00Z",
                language="bn",
                location={
                    "lat": 23.8103,
                    "lng": 90.4125,
                    "accuracy_m": 7.5,
                    "source": "gps",
                },
                text="বন্যার পানিতে তিনজন আটকা পড়েছে। দ্রুত উদ্ধার ও চিকিৎসা সহায়তা দরকার।",
                people_count=3,
                needs=["rescue", "medical"],
            ),
        ),
        (
            "english-safe-route-no-location",
            _signed_report(
                seed_hex="202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f",
                message_id="123e4567-e89b-42d3-a456-426614174001",
                report_type="SAFE_ROUTE",
                created_at="2026-07-30T09:20:00Z",
                language="en",
                location={"lat": None, "lng": None, "accuracy_m": None, "source": "none"},
                text="The eastern school road is passable on foot; avoid the damaged bridge.",
                people_count=None,
                needs=["signage"],
            ),
        ),
    ]
    document = {
        "format": "protidhoni-lora-golden-v1",
        "protocol": {
            "version": FRAME_VERSION,
            "application_port": APPLICATION_PORT,
            "meshtastic_payload_bytes": MAX_APPLICATION_PAYLOAD,
            "header_bytes": FRAME_HEADER_SIZE,
            "chunk_bytes": CHUNK_SIZE,
            "max_report_bytes": MAX_REPORT_SIZE,
            "max_fragments": MAX_FRAGMENT_COUNT,
        },
        "vectors": [_vector(name, report) for name, report in reports],
    }
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", type=Path, help="fail unless PATH exactly matches generated data")
    args = parser.parse_args()
    generated = generate()
    if args.check is None:
        sys.stdout.buffer.write(generated)
        return 0
    try:
        existing = args.check.read_bytes()
    except FileNotFoundError:
        print(f"golden vector file does not exist: {args.check}", file=sys.stderr)
        return 1
    if not hmac_compare(existing, generated):
        print(f"golden vector file is stale or manually modified: {args.check}", file=sys.stderr)
        return 1
    print(f"golden vectors verified: {args.check}")
    return 0


def hmac_compare(left: bytes, right: bytes) -> bool:
    # Constant-time comparison is inexpensive here and avoids introducing a
    # second comparison convention into protocol-adjacent tooling.
    import hmac

    return hmac.compare_digest(left, right)


if __name__ == "__main__":
    raise SystemExit(main())

