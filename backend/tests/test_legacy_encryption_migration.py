from __future__ import annotations

import copy

import pytest
from cryptography.fernet import Fernet

from protidhoni_api import encryption
from protidhoni_api.config import get_settings
from protidhoni_api.migrate_legacy_encryption import (
    LegacyEncryptionMigrationError,
    _migration_params,
    classify_sensitive_storage,
)

from .factories import make_signed_report


@pytest.fixture
def configured_key(monkeypatch):
    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _row(raw_message: dict) -> dict:
    return {
        "message_id": raw_message["message_id"],
        "report_type": raw_message["type"],
        "payload": copy.deepcopy(raw_message["payload"]),
        "raw_message": raw_message,
    }


def test_classifies_valid_legacy_plaintext_report(configured_key) -> None:
    report = make_signed_report(report_type="SOS")

    assert classify_sensitive_storage(report) == "legacy_plaintext"


def test_classifies_ciphertext_encrypted_with_current_key(configured_key) -> None:
    report = make_signed_report(report_type="MEDICAL_NEED")
    encrypted = encryption.encrypt_sensitive_report_dict(report, report["type"])

    assert classify_sensitive_storage(encrypted) == "encrypted"
    assert _migration_params(_row(encrypted)) is None


def test_plans_all_sensitive_copies_and_rounded_location(configured_key) -> None:
    report = make_signed_report(
        report_type="SOS",
        location={"lat": 23.81491, "lng": 90.41478, "accuracy_m": 5.0, "source": "gps"},
    )

    params = _migration_params(_row(report))

    assert params is not None
    assert params["raw_message"].obj["payload"]["text"] != report["payload"]["text"]
    assert params["payload"].obj == params["raw_message"].obj["payload"]
    assert params["lat"] == 23.81
    assert params["lng"] == 90.41


def test_rejects_ciphertext_from_a_different_key(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    get_settings.cache_clear()
    report = make_signed_report(report_type="SOS")
    encrypted = encryption.encrypt_sensitive_report_dict(report, report["type"])

    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    get_settings.cache_clear()
    try:
        with pytest.raises(encryption.EncryptionKeyError):
            classify_sensitive_storage(encrypted)
    finally:
        get_settings.cache_clear()


def test_rejects_mixed_plaintext_and_ciphertext(configured_key) -> None:
    report = make_signed_report(report_type="SOS")
    encrypted_text = encryption.encrypt_sensitive_text(report["payload"]["text"])
    report["payload"]["text"] = encrypted_text

    with pytest.raises(LegacyEncryptionMigrationError, match="mixes plaintext and ciphertext"):
        classify_sensitive_storage(report)


def test_rejects_payload_copy_drift(configured_key) -> None:
    report = make_signed_report(report_type="SOS")
    row = _row(report)
    row["payload"]["text"] = "different stored copy"

    with pytest.raises(LegacyEncryptionMigrationError, match="payload disagrees"):
        _migration_params(row)


def test_rejects_non_sensitive_report(configured_key) -> None:
    report = make_signed_report(report_type="SHELTER_INFO")

    with pytest.raises(LegacyEncryptionMigrationError, match="non-sensitive"):
        classify_sensitive_storage(report)
