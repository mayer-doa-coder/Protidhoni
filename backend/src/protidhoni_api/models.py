"""Pydantic models mirroring contracts/message-schema.json exactly.

Fields that participate in the Ed25519 signature (see contracts/README.md,
"Report signing rule") are kept as plain ``str``/``Literal`` values rather than
richer Python types (``UUID``, ``datetime``) so that ``signed_subset()``
reproduces byte-for-byte the same JSON values the sender canonicalized and
signed. Reformatting them (e.g. normalizing UUID casing or re-serializing a
parsed datetime) would silently break signature verification for otherwise
valid messages.
"""

from __future__ import annotations

import re
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ReportType = Literal[
    "SOS",
    "MEDICAL_NEED",
    "RESOURCE_NEED",
    "SAFETY_STATUS",
    "SHELTER_INFO",
    "HAZARD_UPDATE",
    "SAFE_ROUTE",
    "INSTRUCTION",
]
Language = Literal["bn", "en"]
LocationSource = Literal["gps", "manual", "none"]
Priority = Literal["critical", "high", "medium", "low"]
SyncStatus = Literal["local", "relayed", "synced"]
VerificationStatus = Literal["unverified", "corroborated", "verified", "disputed"]

_DEVICE_HASH_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SIGNATURE_VALUE_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
_ATTACHMENT_REF_RE = re.compile(r"^[a-f0-9]{64}$")
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    accuracy_m: float | None = Field(None, gt=0)
    source: LocationSource

    @model_validator(mode="after")
    def _check_source_consistency(self) -> Location:
        if self.source == "none":
            if self.lat is not None or self.lng is not None or self.accuracy_m is not None:
                raise ValueError(
                    "location.source 'none' requires lat, lng, and accuracy_m to be null"
                )
        elif self.source == "gps":
            if self.lat is None or self.lng is None or self.accuracy_m is None:
                raise ValueError("location.source 'gps' requires lat, lng, and accuracy_m")
        elif self.source == "manual" and (self.lat is None or self.lng is None):
            raise ValueError("location.source 'manual' requires lat and lng")
        return self


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    people_count: int | None = Field(None, ge=1, le=100_000)
    needs: list[str] = Field(default_factory=list, max_length=20)
    attachment_ref: str | None = None

    @model_validator(mode="after")
    def _check_formats(self) -> Payload:
        for need in self.needs:
            if not (1 <= len(need) <= 64):
                raise ValueError("each payload.needs entry must be 1-64 characters")
        if len(set(self.needs)) != len(self.needs):
            raise ValueError("payload.needs must not contain duplicates")
        if self.attachment_ref is not None and not _ATTACHMENT_REF_RE.match(self.attachment_ref):
            raise ValueError(
                "payload.attachment_ref must be a lowercase 64-character hex SHA-256 hash"
            )
        return self


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["Ed25519"]
    value: str

    @model_validator(mode="after")
    def _check_value_format(self) -> Signature:
        if not _SIGNATURE_VALUE_RE.match(self.value):
            raise ValueError(
                "signature.value must be 86 base64url characters (64 raw bytes, unpadded)"
            )
        return self


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    corroboration_count: int = Field(ge=0)


class VerificationUpdate(BaseModel):
    """Responder-owned fields accepted by PATCH /reports/{message_id}."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    responder_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null_note(cls, value):
        if (
            isinstance(value, dict)
            and "responder_note" in value
            and value["responder_note"] is None
        ):
            raise ValueError("responder_note must be a string when provided")
        return value

    @property
    def note_was_provided(self) -> bool:
        return "responder_note" in self.model_fields_set


class TranslationRequest(BaseModel):
    """An authorized request to translate one stored report, never raw text."""

    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    target_language: Language


class TranslationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    source_language: Language
    target_language: Language
    text: str = Field(min_length=1, max_length=4000)
    provider: str = Field(min_length=1, max_length=64)


_ALLOWED_VERIFICATION_TRANSITIONS: dict[VerificationStatus, frozenset[VerificationStatus]] = {
    "unverified": frozenset({"unverified", "corroborated", "verified", "disputed"}),
    "corroborated": frozenset({"corroborated", "verified", "disputed"}),
    "verified": frozenset({"verified"}),
    "disputed": frozenset({"disputed"}),
}


def verification_transition_allowed(
    current: VerificationStatus, requested: VerificationStatus
) -> bool:
    """Enforce unverified → corroborated → verified, or terminal disputed.

    Repeating the current state is idempotent. Verified and disputed are
    terminal so a later request cannot silently erase an adjudicated result.
    """
    return requested in _ALLOWED_VERIFICATION_TRANSITIONS[current]


def _validate_device_hash(value: str, field_name: str) -> str:
    if not _DEVICE_HASH_RE.match(value):
        raise ValueError(f"{field_name} must be 43 base64url characters (32 raw bytes, unpadded)")
    return value


class Report(BaseModel):
    """Mirrors contracts/message-schema.json#/$defs/report."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    message_id: str
    type: ReportType
    sender_pubkey: str
    sender_pubkey_hash: str
    created_at: str
    language: Language
    location: Location
    payload: Payload
    priority: Priority | None
    ttl_hops: int = Field(ge=0, le=16)
    signature: Signature
    relay_path: list[str] = Field(default_factory=list, max_length=16)
    sync_status: SyncStatus
    verification: Verification

    @model_validator(mode="after")
    def _check_identifiers(self) -> Report:
        try:
            import uuid

            uuid.UUID(self.message_id)
        except ValueError as error:
            raise ValueError("message_id must be a UUID string") from error
        if not _ISO8601_RE.match(self.created_at):
            raise ValueError("created_at must be an ISO 8601 date-time string")
        _validate_device_hash(self.sender_pubkey, "sender_pubkey")
        _validate_device_hash(self.sender_pubkey_hash, "sender_pubkey_hash")
        for device_hash in self.relay_path:
            _validate_device_hash(device_hash, "relay_path entry")
        if len(set(self.relay_path)) != len(self.relay_path):
            raise ValueError("relay_path must not contain duplicate entries")
        return self

    def signed_subset(self) -> dict:
        """The exact object shape covered by the Ed25519 signature.

        See contracts/README.md, "Report signing rule": ttl_hops, relay_path,
        sync_status, priority, and verification are mutable operational
        metadata and are deliberately excluded here.
        """
        return {
            "schema_version": self.schema_version,
            "message_id": self.message_id,
            "type": self.type,
            "sender_pubkey": self.sender_pubkey,
            "sender_pubkey_hash": self.sender_pubkey_hash,
            "created_at": self.created_at,
            "language": self.language,
            "location": {
                "lat": self.location.lat,
                "lng": self.location.lng,
                "accuracy_m": self.location.accuracy_m,
                "source": self.location.source,
            },
            "payload": {
                "text": self.payload.text,
                "people_count": self.payload.people_count,
                "needs": list(self.payload.needs),
                "attachment_ref": self.payload.attachment_ref,
            },
        }


class ReportBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[Report] = Field(min_length=1, max_length=100)
