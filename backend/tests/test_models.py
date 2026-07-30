import pytest
from pydantic import ValidationError

from protidhoni_api.models import Report

from .factories import make_signed_report


def test_valid_report_parses() -> None:
    report = Report.model_validate(make_signed_report())
    assert report.type == "SOS"


def test_signed_subset_contains_exactly_the_documented_fields() -> None:
    report = Report.model_validate(make_signed_report())
    assert set(report.signed_subset()) == {
        "schema_version",
        "message_id",
        "type",
        "sender_pubkey",
        "sender_pubkey_hash",
        "created_at",
        "language",
        "location",
        "payload",
    }


def test_rejects_out_of_range_latitude() -> None:
    raw = make_signed_report(location={"lat": 999, "lng": 90.41, "accuracy_m": 5.0, "source": "gps"})
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_gps_source_missing_coordinates() -> None:
    raw = make_signed_report(location={"lat": None, "lng": None, "accuracy_m": None, "source": "gps"})
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_none_source_with_coordinates_present() -> None:
    raw = make_signed_report(location={"lat": 23.8, "lng": 90.4, "accuracy_m": None, "source": "none"})
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_unknown_top_level_field() -> None:
    raw = make_signed_report()
    raw["unexpected_field"] = "nope"
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_duplicate_needs() -> None:
    raw = make_signed_report(payload={"text": "help", "people_count": 1, "needs": ["water", "water"], "attachment_ref": None})
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_malformed_sender_pubkey() -> None:
    raw = make_signed_report()
    raw["sender_pubkey"] = "too-short"
    with pytest.raises(ValidationError):
        Report.model_validate(raw)


def test_rejects_non_uuid_message_id() -> None:
    raw = make_signed_report()
    raw["message_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        Report.model_validate(raw)
