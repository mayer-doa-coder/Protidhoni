"""Encryption at rest for the most sensitive report fields.

Protidhoni_Roadmap.md §5.5 requires encrypting medical-need text and exact
locations of vulnerable people at rest. This module encrypts ``payload.text``
and ``location.lat``/``location.lng`` for ``SOS`` and ``MEDICAL_NEED`` reports
only — the two types most likely to carry a specific person's situation and
whereabouts — using Fernet (AES128-CBC + HMAC-SHA256) from the ``cryptography``
package, already a direct dependency for Ed25519 verification (see crypto.py).

Exact coordinates are encrypted in the JSONB copies (``reports.raw_message``
and ``reports.payload``). The parallel PostGIS ``reports.location`` geography
column is kept queryable, but SOS/MEDICAL_NEED coordinates are rounded before
storage so bbox filtering can work without storing exact vulnerable-person
locations twice.
"""

from __future__ import annotations

import copy

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

SENSITIVE_REPORT_TYPES = frozenset({"SOS", "MEDICAL_NEED"})
SENSITIVE_LOCATION_DECIMAL_PLACES = 2


class EncryptionKeyError(RuntimeError):
    """Raised when PROTIDHONI_DATA_ENCRYPTION_KEY is missing, invalid, or ciphertext fails to decrypt with it."""


def _fernet() -> Fernet:
    key = get_settings().data_encryption_key
    raw = key.get_secret_value() if key else ""
    if not raw:
        raise EncryptionKeyError(
            "PROTIDHONI_DATA_ENCRYPTION_KEY is not configured; cannot encrypt or "
            "decrypt sensitive report fields (SOS/MEDICAL_NEED payload.text and location)."
        )
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, TypeError) as error:
        raise EncryptionKeyError(
            "PROTIDHONI_DATA_ENCRYPTION_KEY must be a valid urlsafe-base64 32-byte Fernet key."
        ) from error


def validate_encryption_key() -> None:
    """Fail before a migration or ingest if the configured key is unusable."""
    _fernet()


def encrypt_sensitive_text(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_sensitive_text(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise EncryptionKeyError(
            "Stored ciphertext could not be decrypted with the configured "
            "PROTIDHONI_DATA_ENCRYPTION_KEY."
        ) from error


def _encrypt_number(value: float | None) -> float | str | None:
    if value is None:
        return None
    return encrypt_sensitive_text(repr(value))


def _decrypt_number(value: float | str | None) -> float | None:
    if value is None:
        return None
    return float(decrypt_sensitive_text(value))


def encrypt_sensitive_report_dict(report_dict: dict, report_type: str) -> dict:
    """Return a copy of a ``Report.model_dump(mode="json")`` dict ready for storage.

    Non-sensitive types are returned unchanged (same object, no copy) so that
    idempotency/conflict comparisons against stored JSONB keep working
    byte-for-byte. Sensitive types get a deep copy with ``payload.text`` and
    ``location.lat``/``location.lng`` replaced by Fernet ciphertext strings.
    """
    if report_type not in SENSITIVE_REPORT_TYPES:
        return report_dict

    stored = copy.deepcopy(report_dict)
    stored["payload"]["text"] = encrypt_sensitive_text(stored["payload"]["text"])
    stored["location"]["lat"] = _encrypt_number(stored["location"]["lat"])
    stored["location"]["lng"] = _encrypt_number(stored["location"]["lng"])
    return stored


def decrypt_sensitive_report_dict(report_dict: dict, report_type: str) -> dict:
    """Reverse of ``encrypt_sensitive_report_dict``, applied to a stored raw_message dict."""
    if report_type not in SENSITIVE_REPORT_TYPES:
        return report_dict

    restored = copy.deepcopy(report_dict)
    restored["payload"]["text"] = decrypt_sensitive_text(restored["payload"]["text"])
    restored["location"]["lat"] = _decrypt_number(restored["location"]["lat"])
    restored["location"]["lng"] = _decrypt_number(restored["location"]["lng"])
    return restored


def location_coordinate_for_query_index(value: float | None, report_type: str) -> float | None:
    """Return the coordinate safe to store in the plaintext PostGIS query column."""
    if value is None or report_type not in SENSITIVE_REPORT_TYPES:
        return value
    return round(value, SENSITIVE_LOCATION_DECIMAL_PLACES)
