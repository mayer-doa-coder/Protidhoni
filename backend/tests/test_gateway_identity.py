"""Gateway signing identity and provider webhook signature primitives."""

import base64
import hashlib
import hmac
import secrets
import uuid
from hashlib import sha1

import pytest

from protidhoni_api.config import get_settings
from protidhoni_api.crypto import verify_report_signature
from protidhoni_api.gateway_identity import (
    GatewayIdentityError,
    GatewayLocation,
    ReportDraft,
    build_signed_report,
    gateway_pubkey_hash_or_none,
    load_gateway_identity,
)
from protidhoni_api.gateway_webhook import (
    WebhookAuthError,
    expected_simulator_signature,
    expected_twilio_signature,
    resolve_signed_url,
    verify_simulator_signature,
    verify_twilio_signature,
)
from protidhoni_api.models import Report

AUTH_TOKEN = "a" * 32


@pytest.fixture
def gateway_key(monkeypatch) -> str:
    seed = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", seed)
    get_settings.cache_clear()
    yield seed
    get_settings.cache_clear()


def _draft(**overrides) -> ReportDraft:
    values = {
        "report_type": "SOS",
        "language": "en",
        "text": "trapped, need rescue",
        "people_count": 4,
        "needs": ("rescue",),
    }
    values.update(overrides)
    return ReportDraft(**values)


class TestGatewayIdentity:
    def test_key_is_derived_into_contract_shaped_identifiers(self, gateway_key) -> None:
        identity = load_gateway_identity()

        # Both must be 43-character base64url per contracts/message-schema.json.
        assert len(identity.public_key_b64) == 43
        assert len(identity.pubkey_hash_b64) == 43

    def test_hash_is_sha256_of_the_public_key_as_crypto_py_requires(self, gateway_key) -> None:
        identity = load_gateway_identity()

        raw_public = base64.urlsafe_b64decode(identity.public_key_b64 + "=")
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(raw_public).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        assert identity.pubkey_hash_b64 == expected

    def test_identity_is_stable_across_calls(self, gateway_key) -> None:
        assert load_gateway_identity().pubkey_hash_b64 == load_gateway_identity().pubkey_hash_b64

    def test_missing_key_fails_closed(self, monkeypatch) -> None:
        monkeypatch.delenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", raising=False)
        get_settings.cache_clear()
        try:
            with pytest.raises(GatewayIdentityError):
                load_gateway_identity()
        finally:
            get_settings.cache_clear()

    @pytest.mark.parametrize(
        "value",
        [
            "not-valid-base64url!!",
            base64.urlsafe_b64encode(b"too-short").rstrip(b"=").decode("ascii"),
            base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii"),
        ],
    )
    def test_malformed_key_fails_closed(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", value)
        get_settings.cache_clear()
        try:
            with pytest.raises(GatewayIdentityError):
                load_gateway_identity()
        finally:
            get_settings.cache_clear()

    def test_pubkey_hash_helper_never_raises_for_health(self, monkeypatch) -> None:
        monkeypatch.delenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", raising=False)
        get_settings.cache_clear()
        try:
            # GET /health must stay usable on a deployment with no gateway.
            assert gateway_pubkey_hash_or_none() is None
        finally:
            get_settings.cache_clear()


class TestSignedReportAssembly:
    def test_report_validates_and_verifies(self, gateway_key) -> None:
        report_dict = build_signed_report(_draft(), message_id=str(uuid.uuid4()))
        report = Report.model_validate(report_dict)

        assert verify_report_signature(report).sender_pubkey_hash == report.sender_pubkey_hash

    def test_gateway_reports_start_unscored_and_unverified(self, gateway_key) -> None:
        report = Report.model_validate(build_signed_report(_draft(), message_id=str(uuid.uuid4())))

        # Ingestion does not synchronously call AI; a responder owns verification.
        assert report.priority is None
        assert report.verification.status == "unverified"
        assert report.verification.corroboration_count == 0

    def test_gateway_reports_carry_no_mesh_history(self, gateway_key) -> None:
        report = Report.model_validate(build_signed_report(_draft(), message_id=str(uuid.uuid4())))

        # It arrived directly at the backend, so claiming relay hops would be a lie.
        assert report.relay_path == []
        assert report.ttl_hops == 0
        assert report.sync_status == "synced"

    def test_typed_coordinates_are_recorded_as_manual(self, gateway_key) -> None:
        report = Report.model_validate(
            build_signed_report(
                _draft(location=GatewayLocation(lat=23.81, lng=90.41)),
                message_id=str(uuid.uuid4()),
            )
        )

        assert report.location.source == "manual"
        assert report.location.accuracy_m is None

    def test_absent_coordinates_are_recorded_as_none(self, gateway_key) -> None:
        report = Report.model_validate(build_signed_report(_draft(), message_id=str(uuid.uuid4())))

        assert report.location.source == "none"
        assert report.location.lat is None

    def test_tampering_after_signing_breaks_verification(self, gateway_key) -> None:
        report_dict = build_signed_report(_draft(), message_id=str(uuid.uuid4()))
        report_dict["payload"]["text"] = "an injected claim the sender never made"

        from protidhoni_api.crypto import SignatureVerificationError

        with pytest.raises(SignatureVerificationError):
            verify_report_signature(Report.model_validate(report_dict))

    def test_mutable_fields_are_outside_the_signature(self, gateway_key) -> None:
        report_dict = build_signed_report(_draft(), message_id=str(uuid.uuid4()))
        report_dict["ttl_hops"] = 9
        report_dict["priority"] = "critical"
        report_dict["verification"] = {"status": "verified", "corroboration_count": 3}

        # Relay/server-owned fields must remain updatable without invalidating
        # the sender attestation, exactly as for mesh reports.
        verify_report_signature(Report.model_validate(report_dict))


class TestTwilioSignature:
    """Structural checks on the provider signature scheme.

    These deliberately do not assert a vendor-published constant: no verified
    Twilio test vector was available offline while writing them, and inventing
    one would look like cross-vendor validation without being it. What is
    verified here is the algorithm's independently-recomputed output and the
    security properties that actually matter. Confirming interoperability
    against a live provider callback remains an explicit manual step in
    backend/README.md.
    """

    def test_matches_an_independent_recomputation_of_the_documented_steps(self) -> None:
        url = "https://example.org/gateway/sms?x=1"
        params = {"B": "two", "A": "one", "C": "three"}

        # Literal transcription of the published algorithm: full URL, then each
        # parameter name and value appended in sorted key order, HMAC-SHA1, base64.
        payload = url + "A" + "one" + "B" + "two" + "C" + "three"
        expected = base64.b64encode(
            hmac.new(AUTH_TOKEN.encode(), payload.encode(), sha1).digest()
        ).decode()

        assert expected_twilio_signature(url=url, params=params, auth_token=AUTH_TOKEN) == expected

    def test_parameter_order_does_not_change_the_signature(self) -> None:
        url = "https://example.org/gateway/sms"
        forward = expected_twilio_signature(
            url=url, params={"A": "1", "B": "2"}, auth_token=AUTH_TOKEN
        )
        reverse = expected_twilio_signature(
            url=url, params={"B": "2", "A": "1"}, auth_token=AUTH_TOKEN
        )

        assert forward == reverse

    def test_url_is_part_of_the_signed_material(self) -> None:
        params = {"A": "1"}
        first = expected_twilio_signature(
            url="https://example.org/gateway/sms", params=params, auth_token=AUTH_TOKEN
        )
        second = expected_twilio_signature(
            url="https://example.org/gateway/ussd", params=params, auth_token=AUTH_TOKEN
        )

        # Otherwise a callback signed for one endpoint could be replayed at another.
        assert first != second

    def test_valid_signature_is_accepted(self) -> None:
        url, params = "https://example.org/gateway/sms", {"Body": "help"}
        signature = expected_twilio_signature(url=url, params=params, auth_token=AUTH_TOKEN)

        verify_twilio_signature(
            url=url, params=params, presented_signature=signature, auth_token=AUTH_TOKEN
        )

    @pytest.mark.parametrize("presented", [None, "", "not-a-signature"])
    def test_missing_or_wrong_signature_is_rejected_as_unauthorised(self, presented) -> None:
        with pytest.raises(WebhookAuthError) as raised:
            verify_twilio_signature(
                url="https://example.org/gateway/sms",
                params={"Body": "help"},
                presented_signature=presented,
                auth_token=AUTH_TOKEN,
            )

        assert raised.value.status_code == 401

    def test_unconfigured_token_is_a_server_error_not_an_open_door(self) -> None:
        with pytest.raises(WebhookAuthError) as raised:
            verify_twilio_signature(
                url="https://example.org/gateway/sms",
                params={},
                presented_signature="anything",
                auth_token=None,
            )

        assert raised.value.status_code == 503

    def test_a_signature_from_a_different_token_is_rejected(self) -> None:
        url, params = "https://example.org/gateway/sms", {"Body": "help"}
        forged = expected_twilio_signature(url=url, params=params, auth_token="b" * 32)

        with pytest.raises(WebhookAuthError):
            verify_twilio_signature(
                url=url, params=params, presented_signature=forged, auth_token=AUTH_TOKEN
            )


class TestSimulatorSignature:
    def test_valid_signature_is_accepted_and_bound_to_exact_body(self) -> None:
        url = "https://example.org/gateway/ussd"
        body = b"sessionId=US123&text=1%2A2"
        signature = expected_simulator_signature(url=url, body=body, auth_token=AUTH_TOKEN)

        verify_simulator_signature(
            url=url,
            body=body,
            presented_signature=signature,
            auth_token=AUTH_TOKEN,
        )
        with pytest.raises(WebhookAuthError):
            verify_simulator_signature(
                url=url,
                body=body + b"%2A3",
                presented_signature=signature,
                auth_token=AUTH_TOKEN,
            )

    def test_unconfigured_simulator_fails_closed(self) -> None:
        with pytest.raises(WebhookAuthError) as raised:
            verify_simulator_signature(
                url="https://example.org/gateway/ussd",
                body=b"",
                presented_signature="anything",
                auth_token=None,
            )
        assert raised.value.status_code == 503


class TestBlankConfigurationIsDisabledNotBroken:
    """docker compose passes "" for every unset optional variable.

    Blank must mean "this deployment has no gateway", never a startup crash and
    never a weakened check.
    """

    @pytest.fixture(autouse=True)
    def blank_gateway_env(self, monkeypatch):
        for name in (
            "GATEWAY_PRIVATE_KEY",
            "GATEWAY_WEBHOOK_TOKEN",
            "GATEWAY_USSD_WEBHOOK_TOKEN",
            "GATEWAY_PHONE_PEPPER",
            "GATEWAY_PUBLIC_BASE_URL",
        ):
            monkeypatch.setenv(f"PROTIDHONI_{name}", "")
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_blank_public_base_url_is_normalised_rather_than_rejected(self) -> None:
        assert get_settings().gateway_public_base_url is None

    def test_blank_secrets_read_as_unconfigured(self) -> None:
        settings = get_settings()

        assert settings.configured_gateway_webhook_token() is None
        assert settings.configured_gateway_ussd_webhook_token() is None
        assert settings.configured_gateway_phone_pepper() is None
        assert gateway_pubkey_hash_or_none() is None

    def test_a_genuinely_invalid_public_base_url_is_still_rejected(self, monkeypatch) -> None:
        monkeypatch.setenv("PROTIDHONI_GATEWAY_PUBLIC_BASE_URL", "not-a-url")
        get_settings.cache_clear()

        with pytest.raises(ValueError):
            get_settings()

    @pytest.mark.parametrize(
        "value", ["http://gateway.example.org", "https://gateway.example.org/prefix"]
    )
    def test_public_callback_url_requires_a_bare_https_origin(self, monkeypatch, value) -> None:
        monkeypatch.setenv("PROTIDHONI_GATEWAY_PUBLIC_BASE_URL", value)
        get_settings.cache_clear()
        with pytest.raises(ValueError):
            get_settings()


class TestProxyUrlResolution:
    def test_inbound_url_is_used_when_no_public_origin_is_configured(self) -> None:
        assert (
            resolve_signed_url(request_url="http://api:8000/gateway/sms", public_base_url=None)
            == "http://api:8000/gateway/sms"
        )

    def test_public_origin_replaces_the_internal_one(self) -> None:
        # Behind a TLS-terminating proxy the provider signed the public https
        # origin, not the internal http hostname this process observes.
        resolved = resolve_signed_url(
            request_url="http://api:8000/gateway/sms",
            public_base_url="https://protidhoni.example.org",
        )

        assert resolved == "https://protidhoni.example.org/gateway/sms"

    def test_query_string_is_preserved(self) -> None:
        resolved = resolve_signed_url(
            request_url="http://api:8000/gateway/sms?trace=7",
            public_base_url="https://protidhoni.example.org",
        )

        assert resolved == "https://protidhoni.example.org/gateway/sms?trace=7"
