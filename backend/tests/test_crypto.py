import pytest

from protidhoni_api.crypto import SignatureVerificationError, verify_report_signature
from protidhoni_api.models import Report

from .factories import make_signed_report


def test_verify_accepts_a_genuinely_signed_report() -> None:
    report = Report.model_validate(make_signed_report())

    identity = verify_report_signature(report)

    assert identity.sender_pubkey_hash == report.sender_pubkey_hash


def test_verify_rejects_a_corrupted_signature() -> None:
    report = Report.model_validate(make_signed_report(corrupt_signature=True))

    with pytest.raises(SignatureVerificationError):
        verify_report_signature(report)


def test_verify_rejects_a_pubkey_hash_that_does_not_match_the_pubkey() -> None:
    report = Report.model_validate(make_signed_report(wrong_pubkey_hash=True))

    with pytest.raises(SignatureVerificationError):
        verify_report_signature(report)


def test_verify_rejects_a_signed_field_tampered_with_after_signing() -> None:
    raw = make_signed_report()
    report = Report.model_validate(raw)
    tampered = report.model_copy(update={"payload": report.payload.model_copy(update={"text": "different"})})

    with pytest.raises(SignatureVerificationError):
        verify_report_signature(tampered)


def test_verify_ignores_mutation_of_fields_outside_the_signed_subset() -> None:
    """ttl_hops/relay_path/priority/verification are excluded from the signature
    by design (contracts/README.md) so relays and the backend can update them
    without invalidating the sender's signature."""
    raw = make_signed_report(ttl_hops=5)
    report = Report.model_validate(raw)
    relayed = report.model_copy(
        update={
            "ttl_hops": report.ttl_hops - 1,
            "relay_path": [*report.relay_path, "A" * 43],
            "priority": "high",
        }
    )

    identity = verify_report_signature(relayed)

    assert identity.sender_pubkey_hash == report.sender_pubkey_hash
