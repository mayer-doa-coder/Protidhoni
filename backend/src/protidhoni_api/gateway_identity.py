"""The SMS/USSD gateway's own Ed25519 signing identity.

contracts/message-schema.json requires ``sender_pubkey``, ``sender_pubkey_hash``,
and a valid Ed25519 ``signature`` on every report, and crypto.py enforces that
the hash equals SHA-256 of the key. A feature phone cannot sign anything, so the
gateway holds its own keypair and signs on the sender's behalf.

That makes every gateway-originated report carry the *gateway's*
``sender_pubkey_hash``, which is deliberate and has two consequences:

1. It is honest about provenance. The gateway is the attesting party — it
   witnessed an SMS/USSD session — not the phone owner. A responder must not
   read these as device-attested the way mesh reports are (see the Phase 4
   addendum in contracts/README.md).
2. That shared hash is the provenance marker the dashboard filters on, so no
   new schema field — and therefore no schema version bump and no three-person
   contract renegotiation — is required.

Provider-supplied caller metadata is never signed, persisted, or placed in a
report field. A number deliberately typed into report text remains user
content. See gateway_routes.py for the HMAC pseudonym used only in memory.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import get_settings
from .models import Language, ReportType

SCHEMA_VERSION = "1.0.0"

# Reports arriving here are already at the backend, so they have no mesh
# forwarding budget left to spend and never traversed a relay path.
_GATEWAY_TTL_HOPS = 0

# Must stay byte-identical to contracts/README.md's "Report signing rule" and to
# crypto.verify_report_signature's view of the signed subset.
_SIGNED_SUBSET_KEYS = (
    "schema_version",
    "message_id",
    "type",
    "sender_pubkey",
    "sender_pubkey_hash",
    "created_at",
    "language",
    "location",
    "payload",
)


class GatewayIdentityError(RuntimeError):
    """Raised when PROTIDHONI_GATEWAY_PRIVATE_KEY is missing or malformed."""


@dataclass(frozen=True)
class GatewayLocation:
    """A gateway report's location, defaulting to 'no location supplied'.

    A feature phone gives the gateway no GPS fix. An SMS sender may type
    coordinates, which the schema calls ``manual`` — user-asserted, not
    device-measured — and USSD menus cannot practically carry them at all.
    """

    lat: float | None = None
    lng: float | None = None

    def as_contract_dict(self) -> dict:
        if self.lat is None or self.lng is None:
            return {"lat": None, "lng": None, "accuracy_m": None, "source": "none"}
        return {"lat": self.lat, "lng": self.lng, "accuracy_m": None, "source": "manual"}


@dataclass(frozen=True)
class ReportDraft:
    """The provider-neutral result of parsing one SMS body or USSD session."""

    report_type: ReportType
    language: Language
    text: str
    people_count: int | None = None
    needs: tuple[str, ...] = ()
    location: GatewayLocation = GatewayLocation()


@dataclass(frozen=True)
class GatewayIdentity:
    private_key: Ed25519PrivateKey
    public_key_b64: str
    pubkey_hash_b64: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def load_gateway_identity() -> GatewayIdentity:
    """Load the gateway keypair from configuration, failing closed when unset.

    Deliberately not cached: deriving an Ed25519 key from a 32-byte seed is
    cheap, and a module-level cache would silently outlive the settings cache
    that tests clear between cases.
    """
    configured = get_settings().gateway_private_key
    seed_b64 = configured.get_secret_value() if configured else ""
    if not seed_b64:
        raise GatewayIdentityError(
            "PROTIDHONI_GATEWAY_PRIVATE_KEY is not configured; the SMS/USSD gateway "
            "cannot sign reports on behalf of feature-phone senders."
        )

    padding = "=" * ((4 - len(seed_b64) % 4) % 4)
    try:
        seed = base64.urlsafe_b64decode(seed_b64 + padding)
    except (ValueError, base64.binascii.Error) as error:  # type: ignore[attr-defined]
        raise GatewayIdentityError(
            "PROTIDHONI_GATEWAY_PRIVATE_KEY must be base64url-encoded."
        ) from error

    if len(seed) != 32:
        raise GatewayIdentityError(
            f"PROTIDHONI_GATEWAY_PRIVATE_KEY must decode to exactly 32 bytes (got {len(seed)})."
        )

    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public_key_raw = private_key.public_key().public_bytes_raw()
    return GatewayIdentity(
        private_key=private_key,
        public_key_b64=_b64url_encode(public_key_raw),
        pubkey_hash_b64=_b64url_encode(hashlib.sha256(public_key_raw).digest()),
    )


def gateway_pubkey_hash_or_none() -> str | None:
    """The gateway's public identity for GET /health, or None when unconfigured.

    Safe to expose publicly: it is a public-key hash that already appears in
    every gateway-originated report returned by the public GET /reports. The
    dashboard reads it from here so it can label gateway traffic without a
    build-time environment variable.
    """
    try:
        return load_gateway_identity().pubkey_hash_b64
    except GatewayIdentityError:
        return None


def build_signed_report(
    draft: ReportDraft,
    *,
    message_id: str,
    created_at: str | None = None,
) -> dict:
    """Assemble and sign a complete contract-shaped report for one draft.

    ``created_at`` is server time by default: a feature phone has no trusted
    clock, and the gateway is the party actually attesting to when the message
    arrived.
    """
    identity = load_gateway_identity()
    report = {
        "schema_version": SCHEMA_VERSION,
        "message_id": message_id,
        "type": draft.report_type,
        "sender_pubkey": identity.public_key_b64,
        "sender_pubkey_hash": identity.pubkey_hash_b64,
        "created_at": created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "language": draft.language,
        "location": draft.location.as_contract_dict(),
        "payload": {
            "text": draft.text,
            "people_count": draft.people_count,
            "needs": list(draft.needs),
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": _GATEWAY_TTL_HOPS,
        "relay_path": [],
        "sync_status": "synced",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }

    canonical = rfc8785.dumps({key: report[key] for key in _SIGNED_SUBSET_KEYS})
    report["signature"] = {
        "algorithm": "Ed25519",
        "value": _b64url_encode(identity.private_key.sign(canonical)),
    }
    return report
