"""Automates the cross-language crypto proof the Phase 0-5 audit ran by hand.

Two independent implementations of contracts/README.md's signing rule must
agree, or a device-signed report from the real mobile client would never
verify against the real backend — exactly the class of bug the Bridgefy
lesson (Protidhoni_Roadmap.md §8) warns about. This test shells out once to
Node, running mobile-client's *actual* installed `canonicalize` and
`@noble/ed25519` packages (not a reimplementation), and checks the output
against backend's actual `rfc8785` and `cryptography` libraries.

Skipped, not failed, when Node or mobile-client's node_modules are not
available in the current environment (this suite is not mobile-client's own
dependency and should not force `npm install` as a side effect).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

BRIDGE_SCRIPT = (
    Path(__file__).resolve().parents[2] / "mobile-client" / "scripts" / "crypto_bridge_for_system_tests.mjs"
)
NODE_MODULES = BRIDGE_SCRIPT.parents[1] / "node_modules"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not NODE_MODULES.is_dir(),
    reason="requires Node and mobile-client's node_modules (npm install in mobile-client/)",
)


def _run_bridge(payload: dict) -> dict:
    result = subprocess.run(
        ["node", str(BRIDGE_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


SIGNED_SUBSET_SAMPLE = {
    "schema_version": "1.0.0",
    "message_id": "c8e53505-f11f-4b9c-a36b-4068ba038d6a",
    "type": "SOS",
    "sender_pubkey": "A" * 43,
    "sender_pubkey_hash": "B" * 43,
    "created_at": "2026-07-30T10:00:00Z",
    "language": "bn",
    "location": {"lat": 23.8103, "lng": 90.4125, "accuracy_m": 12.5, "source": "gps"},
    "payload": {
        "text": "পানি এবং উদ্ধার দরকার, ৫ জন আটকা পড়েছি।",
        "people_count": 5,
        "needs": ["water", "rescue"],
        "attachment_ref": None,
    },
}


def test_canonicalization_is_byte_identical_across_languages():
    bridge_result = _run_bridge(SIGNED_SUBSET_SAMPLE)
    node_canonical = bytes.fromhex(bridge_result["canonical_hex"])

    python_canonical = rfc8785.dumps(SIGNED_SUBSET_SAMPLE)

    assert node_canonical == python_canonical


def test_noble_ed25519_signature_verifies_with_python_cryptography():
    bridge_result = _run_bridge(SIGNED_SUBSET_SAMPLE)
    assert bridge_result["self_verified"] is True

    canonical_bytes = bytes.fromhex(bridge_result["canonical_hex"])
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(bridge_result["public_key_hex"]))
    signature = bytes.fromhex(bridge_result["signature_hex"])

    public_key.verify(signature, canonical_bytes)  # raises InvalidSignature on failure


def test_a_tampered_canonical_payload_is_rejected():
    bridge_result = _run_bridge(SIGNED_SUBSET_SAMPLE)
    canonical_bytes = bytearray(bytes.fromhex(bridge_result["canonical_hex"]))
    canonical_bytes[10] ^= 0xFF  # flip a byte inside the signed content

    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(bridge_result["public_key_hex"]))
    signature = bytes.fromhex(bridge_result["signature_hex"])

    with pytest.raises(InvalidSignature):
        public_key.verify(signature, bytes(canonical_bytes))


def test_key_ordering_does_not_affect_canonical_bytes():
    """RFC 8785 requires deterministic key ordering regardless of source order —
    this is what makes the same logical object hash identically no matter which
    language or object-literal order produced it."""
    reordered = dict(reversed(list(SIGNED_SUBSET_SAMPLE.items())))

    bridge_a = _run_bridge(SIGNED_SUBSET_SAMPLE)
    bridge_b = _run_bridge(reordered)

    assert bridge_a["canonical_hex"] == bridge_b["canonical_hex"]
    assert rfc8785.dumps(SIGNED_SUBSET_SAMPLE) == rfc8785.dumps(reordered)
