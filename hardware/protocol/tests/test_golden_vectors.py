from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import jsonschema
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from protidhoni_lora_protocol import Reassembler, ReassemblyStatus, encode_report

PROTOCOL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
VECTORS_PATH = PROTOCOL_DIR / "vectors" / "golden-v1.json"
SCHEMA_PATH = REPO_ROOT / "contracts" / "message-schema.json"
SIGNED_KEYS = (
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


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_golden_vectors_match_codec_contract_schema_and_real_signatures() -> None:
    document = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    assert document["format"] == "protidhoni-lora-golden-v1"
    assert document["protocol"] == {
        "version": 1,
        "application_port": 256,
        "meshtastic_payload_bytes": 224,
        "header_bytes": 56,
        "chunk_bytes": 168,
        "max_report_bytes": 16_384,
        "max_fragments": 98,
    }
    assert len(document["vectors"]) >= 2

    for vector in document["vectors"]:
        report = vector["report"]
        validator.validate(report)
        canonical = base64.b64decode(vector["canonical_payload_base64"], validate=True)
        frames = [base64.b64decode(value, validate=True) for value in vector["frames_base64"]]

        assert canonical == rfc8785.dumps(report)
        assert vector["canonical_payload_length"] == len(canonical)
        assert vector["payload_sha256_hex"] == hashlib.sha256(canonical).hexdigest()
        assert vector["frame_lengths"] == [len(frame) for frame in frames]
        assert frames == encode_report(report)

        signed_subset = {key: report[key] for key in SIGNED_KEYS}
        public_key = _b64url_decode(report["sender_pubkey"])
        signature = _b64url_decode(report["signature"]["value"])
        assert hashlib.sha256(public_key).digest() == _b64url_decode(
            report["sender_pubkey_hash"]
        )
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature, rfc8785.dumps(signed_subset)
        )

        reassembler = Reassembler()
        result = None
        for index, frame in enumerate(reversed(frames)):
            result = reassembler.accept(frame, now=float(index))
        assert result is not None
        assert result.status is ReassemblyStatus.COMPLETE
        assert result.report == report
        assert result.canonical_payload == canonical

