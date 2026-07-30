"""Submit one real, signed development report for the Phase 2 responder check.

This script deliberately generates an ephemeral Ed25519 identity. It is for a
local demonstration only; the mobile client owns persistent device identities.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from protidhoni_api.crypto import verify_report_signature
from protidhoni_api.models import Report

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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def build_demo_report() -> dict:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    report = {
        "schema_version": "1.0.0",
        "message_id": str(uuid.uuid4()),
        "type": "SOS",
        "sender_pubkey": _b64url(public_key),
        "sender_pubkey_hash": _b64url(hashlib.sha256(public_key).digest()),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "language": "en",
        "location": {"lat": 23.81, "lng": 90.41, "accuracy_m": 5.0, "source": "gps"},
        "payload": {
            "text": "Demo responder verification check: water needed.",
            "people_count": 2,
            "needs": ["water"],
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": 5,
        "relay_path": [],
        "sync_status": "local",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }
    canonical = rfc8785.dumps({key: report[key] for key in _SIGNED_SUBSET_KEYS})
    report["signature"] = {
        "algorithm": "Ed25519",
        "value": _b64url(private_key.sign(canonical)),
    }
    verify_report_signature(Report.model_validate(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000")
    args = parser.parse_args()

    report = build_demo_report()
    request = Request(
        f"{args.api_base.rstrip('/')}/reports",
        data=json.dumps({"reports": [report]}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 - explicit local/demo URL
        result = json.loads(response.read())
    if result["results"] != [{"message_id": report["message_id"], "outcome": "accepted"}]:
        raise RuntimeError(f"Demo report was not accepted: {result}")
    print(report["message_id"])


if __name__ == "__main__":
    main()
