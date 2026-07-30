"""Signature verification for the frozen contract's signing rule.

contracts/README.md defines the rule this module enforces: an Ed25519
signature over the RFC 8785 (JCS) canonical form of the report's signed
subset, plus a requirement that ``sender_pubkey_hash`` equals SHA-256 of
``sender_pubkey``. Both checks must pass before a signature is trusted.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .models import Report


class SignatureVerificationError(ValueError):
    """Raised when a report's signature or pubkey hash cannot be trusted."""


@dataclass(frozen=True)
class VerifiedIdentity:
    sender_pubkey_hash: str


def _b64url_decode(value: str, *, expected_length: int, field_name: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(value + padding)
    except (ValueError, base64.binascii.Error) as error:  # type: ignore[attr-defined]
        raise SignatureVerificationError(f"{field_name} is not valid base64url") from error
    if len(raw) != expected_length:
        raise SignatureVerificationError(
            f"{field_name} decodes to {len(raw)} bytes, expected {expected_length}"
        )
    return raw


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def verify_report_signature(report: Report) -> VerifiedIdentity:
    """Verify a report's signature and identity binding.

    Raises SignatureVerificationError if either check fails. On success,
    returns the confirmed sender_pubkey_hash.
    """
    pubkey_bytes = _b64url_decode(report.sender_pubkey, expected_length=32, field_name="sender_pubkey")

    computed_hash = _b64url_encode(hashlib.sha256(pubkey_bytes).digest())
    if computed_hash != report.sender_pubkey_hash:
        raise SignatureVerificationError(
            "sender_pubkey_hash does not equal SHA-256(sender_pubkey)"
        )

    signature_bytes = _b64url_decode(
        report.signature.value, expected_length=64, field_name="signature.value"
    )

    canonical_bytes = rfc8785.dumps(report.signed_subset())

    try:
        Ed25519PublicKey.from_public_bytes(pubkey_bytes).verify(signature_bytes, canonical_bytes)
    except InvalidSignature as error:
        raise SignatureVerificationError("Ed25519 signature does not match the signed subset") from error

    return VerifiedIdentity(sender_pubkey_hash=report.sender_pubkey_hash)
