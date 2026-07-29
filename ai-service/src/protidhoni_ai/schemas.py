import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
Priority = Literal["critical", "high", "medium", "low"]
Language = Literal["bn", "en"]

_DEVICE_HASH_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SIGNATURE_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")
_ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, gt=0)
    source: Literal["gps", "manual", "none"]

    @model_validator(mode="after")
    def check_source_consistency(self) -> "LocationInput":
        if self.source == "none" and any(
            value is not None for value in (self.lat, self.lng, self.accuracy_m)
        ):
            raise ValueError(
                "location.source 'none' requires null coordinates and accuracy"
            )
        if self.source == "gps" and any(
            value is None for value in (self.lat, self.lng, self.accuracy_m)
        ):
            raise ValueError("location.source 'gps' requires coordinates and accuracy")
        if self.source == "manual" and (self.lat is None or self.lng is None):
            raise ValueError("location.source 'manual' requires coordinates")
        return self


class PayloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    people_count: int | None = Field(default=None, ge=1, le=100_000)
    needs: list[str] = Field(default_factory=list, max_length=20)
    attachment_ref: str | None = None

    @model_validator(mode="after")
    def check_needs(self) -> "PayloadInput":
        if any(not 1 <= len(need) <= 64 for need in self.needs):
            raise ValueError("each payload.needs item must contain 1-64 characters")
        if len(set(self.needs)) != len(self.needs):
            raise ValueError("payload.needs must not contain duplicates")
        return self


class SignatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["Ed25519"]
    value: str

    @model_validator(mode="after")
    def check_signature_length(self) -> "SignatureInput":
        if not _SIGNATURE_RE.fullmatch(self.value):
            raise ValueError(
                "signature.value must be an unpadded 64-byte base64url value"
            )
        return self


class VerificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unverified", "corroborated", "verified", "disputed"]
    corroboration_count: int = Field(ge=0)


class InternalTranslationRequest(BaseModel):
    """Private AI-service request defined by contracts/openapi.yaml v1.2.0."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    source_language: Language
    target_language: Language

    @field_validator("text")
    @classmethod
    def check_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("translation text must not be blank")
        return value


class InternalTranslationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    source_language: Language
    target_language: Language
    provider: str = Field(min_length=1, max_length=64)


class ClassificationReport(BaseModel):
    """The frozen report envelope consumed by the isolated AI service.

    Signature verification remains the backend's responsibility. Requiring the
    complete envelope here still prevents the internal endpoint from quietly
    drifting into a second, incompatible request contract.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"]
    message_id: str
    type: ReportType
    sender_pubkey: str
    sender_pubkey_hash: str
    created_at: str
    language: Language
    location: LocationInput
    payload: PayloadInput
    priority: Priority | None
    ttl_hops: int = Field(ge=0, le=16)
    signature: SignatureInput
    relay_path: list[str] = Field(default_factory=list, max_length=16)
    sync_status: Literal["local", "relayed", "synced"]
    verification: VerificationInput

    @model_validator(mode="after")
    def check_frozen_identifiers(self) -> "ClassificationReport":
        try:
            uuid.UUID(self.message_id)
        except ValueError as error:
            raise ValueError("message_id must be a UUID") from error
        if not _ISO8601_RE.fullmatch(self.created_at):
            raise ValueError("created_at must be an ISO 8601 date-time")
        if not _DEVICE_HASH_RE.fullmatch(self.sender_pubkey):
            raise ValueError("sender_pubkey must be a 32-byte base64url value")
        if not _DEVICE_HASH_RE.fullmatch(self.sender_pubkey_hash):
            raise ValueError("sender_pubkey_hash must be a 32-byte base64url value")
        if len(set(self.relay_path)) != len(self.relay_path) or any(
            not _DEVICE_HASH_RE.fullmatch(item) for item in self.relay_path
        ):
            raise ValueError("relay_path must contain unique 32-byte base64url hashes")
        return self


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ReportType
    needs: list[str]
    priority: Priority
    model: str
