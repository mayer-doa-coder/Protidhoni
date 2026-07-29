from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, gt=0)
    source: Literal["gps", "manual", "none"]


class PayloadInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    people_count: int | None = Field(default=None, ge=1, le=100_000)
    needs: list[str] = Field(default_factory=list, max_length=20)
    attachment_ref: str | None = None


class SignatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["Ed25519"]
    value: str


class VerificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unverified", "corroborated", "verified", "disputed"]
    corroboration_count: int = Field(ge=0)


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
    language: Literal["bn", "en"]
    location: LocationInput
    payload: PayloadInput
    priority: Priority | None
    ttl_hops: int = Field(ge=0, le=16)
    signature: SignatureInput
    relay_path: list[str] = Field(default_factory=list, max_length=16)
    sync_status: Literal["local", "relayed", "synced"]
    verification: VerificationInput


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ReportType
    needs: list[str]
    priority: Priority
    model: str
