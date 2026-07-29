import pytest
from cryptography.fernet import Fernet

from protidhoni_api import db
from protidhoni_api.config import get_settings
from protidhoni_api.encryption import (
    EncryptionKeyError,
    decrypt_sensitive_report_dict,
    decrypt_sensitive_text,
    encrypt_sensitive_report_dict,
    encrypt_sensitive_text,
)
from protidhoni_api.models import Report

from .factories import make_signed_report

_A_VALID_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture
def configured_key(monkeypatch):
    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", _A_VALID_KEY)
    get_settings.cache_clear()
    yield _A_VALID_KEY
    get_settings.cache_clear()


def test_encrypt_decrypt_text_round_trips(configured_key) -> None:
    ciphertext = encrypt_sensitive_text("সাহায্য দরকার")

    assert ciphertext != "সাহায্য দরকার"
    assert decrypt_sensitive_text(ciphertext) == "সাহায্য দরকার"


def test_encrypt_raises_when_key_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("PROTIDHONI_DATA_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyError):
            encrypt_sensitive_text("anything")
    finally:
        get_settings.cache_clear()


def test_encrypt_raises_when_key_is_malformed(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyError):
            encrypt_sensitive_text("anything")
    finally:
        get_settings.cache_clear()


def test_decrypt_raises_when_ciphertext_does_not_match_the_configured_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    ciphertext = encrypt_sensitive_text("secret")

    monkeypatch.setenv("PROTIDHONI_DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyError):
            decrypt_sensitive_text(ciphertext)
    finally:
        get_settings.cache_clear()


def test_non_sensitive_report_types_are_returned_unchanged(configured_key) -> None:
    report_dict = make_signed_report(report_type="SHELTER_INFO")

    stored = encrypt_sensitive_report_dict(report_dict, "SHELTER_INFO")

    assert stored is report_dict
    assert stored["payload"]["text"] == report_dict["payload"]["text"]


def test_sensitive_report_types_get_encrypted_payload_and_location(configured_key) -> None:
    for report_type in ("SOS", "MEDICAL_NEED"):
        report_dict = make_signed_report(
            report_type=report_type,
            payload={
                "text": "trapped under debris",
                "people_count": 1,
                "needs": [],
                "attachment_ref": None,
            },
            location={"lat": 23.81, "lng": 90.41, "accuracy_m": 5.0, "source": "gps"},
        )

        stored = encrypt_sensitive_report_dict(report_dict, report_type)

        assert stored["payload"]["text"] != "trapped under debris"
        assert isinstance(stored["location"]["lat"], str)
        assert isinstance(stored["location"]["lng"], str)

        restored = decrypt_sensitive_report_dict(stored, report_type)
        assert restored["payload"]["text"] == "trapped under debris"
        assert restored["location"]["lat"] == 23.81
        assert restored["location"]["lng"] == 90.41


def test_sensitive_report_with_no_location_round_trips_null_coordinates(
    configured_key,
) -> None:
    report_dict = make_signed_report(
        report_type="SOS",
        location={"lat": None, "lng": None, "accuracy_m": None, "source": "none"},
    )

    stored = encrypt_sensitive_report_dict(report_dict, "SOS")
    assert stored["location"]["lat"] is None
    assert stored["location"]["lng"] is None

    restored = decrypt_sensitive_report_dict(stored, "SOS")
    assert restored["location"]["lat"] is None
    assert restored["location"]["lng"] is None


def test_insert_params_stores_ciphertext_for_medical_need_and_report_from_row_decrypts_it(
    configured_key,
) -> None:
    report = Report.model_validate(
        make_signed_report(
            report_type="MEDICAL_NEED",
            payload={
                "text": "insulin needed urgently",
                "people_count": 1,
                "needs": ["medical"],
                "attachment_ref": None,
            },
        )
    )

    params = db._insert_params(report)

    stored_raw_message = params["raw_message"].obj
    stored_payload = params["payload"].obj
    assert stored_raw_message["payload"]["text"] != "insulin needed urgently"
    assert stored_payload["text"] != "insulin needed urgently"
    # The parallel geography-column params must stay plaintext floats for bbox queries.
    assert params["lat"] == report.location.lat
    assert params["lng"] == report.location.lng

    fake_row = {
        "raw_message": stored_raw_message,
        "priority": report.priority,
        "verification_status": report.verification.status,
        "corroboration_count": report.verification.corroboration_count,
    }
    reconstructed = db._report_from_row(fake_row)

    assert reconstructed.payload.text == "insulin needed urgently"
    assert reconstructed.location.lat == report.location.lat
    assert reconstructed.location.lng == report.location.lng
    assert reconstructed.message_id == report.message_id


def test_insert_params_leaves_non_sensitive_report_types_as_plaintext(configured_key) -> None:
    report = Report.model_validate(make_signed_report(report_type="HAZARD_UPDATE"))

    params = db._insert_params(report)

    assert params["raw_message"].obj["payload"]["text"] == report.payload.text
    assert params["payload"].obj["text"] == report.payload.text
