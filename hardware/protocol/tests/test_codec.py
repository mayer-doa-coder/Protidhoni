from __future__ import annotations

import hashlib
import json
import struct
import uuid

import pytest
import rfc8785

from protidhoni_lora_protocol import (
    CHUNK_SIZE,
    FRAME_HEADER_SIZE,
    MAX_ACTIVE_ASSEMBLIES,
    MAX_APPLICATION_PAYLOAD,
    MAX_FRAGMENT_COUNT,
    MAX_REPORT_SIZE,
    FrameConflictError,
    FrameValidationError,
    Reassembler,
    ReassemblyCapacityError,
    ReassemblyStatus,
    TransportPayloadError,
    canonical_report_bytes,
    decode_canonical_report,
    decode_frame,
    encode_report,
)


def _report(*, message_id: str | None = None, text: str = "Need rescue") -> dict:
    return {
        "schema_version": "1.0.0",
        "message_id": message_id or str(uuid.uuid4()),
        "type": "SOS",
        "sender_pubkey": "A" * 43,
        "sender_pubkey_hash": "B" * 43,
        "created_at": "2026-07-30T09:15:00Z",
        "language": "en",
        "location": {"lat": None, "lng": None, "accuracy_m": None, "source": "none"},
        "payload": {
            "text": text,
            "people_count": 2,
            "needs": ["rescue"],
            "attachment_ref": None,
        },
        "priority": None,
        "ttl_hops": 5,
        "signature": {"algorithm": "Ed25519", "value": "C" * 86},
        "relay_path": [],
        "sync_status": "local",
        "verification": {"status": "unverified", "corroboration_count": 0},
    }


def _complete(reassembler: Reassembler, frames: list[bytes], *, start: float = 0.0):
    result = None
    for offset, frame in enumerate(frames):
        result = reassembler.accept(frame, now=start + offset)
    assert result is not None
    return result


def test_frozen_size_constants_are_internally_consistent() -> None:
    assert FRAME_HEADER_SIZE == 56
    assert CHUNK_SIZE == 168
    assert MAX_APPLICATION_PAYLOAD == 224
    assert MAX_FRAGMENT_COUNT == 98
    assert MAX_FRAGMENT_COUNT == (MAX_REPORT_SIZE + CHUNK_SIZE - 1) // CHUNK_SIZE


@pytest.mark.parametrize(
    "report_type",
    [
        "SOS",
        "MEDICAL_NEED",
        "RESOURCE_NEED",
        "SAFETY_STATUS",
        "SHELTER_INFO",
        "HAZARD_UPDATE",
        "SAFE_ROUTE",
        "INSTRUCTION",
    ],
)
def test_round_trip_every_report_type(report_type: str) -> None:
    report = _report(text="জরুরি সহায়তা দরকার — पानी rising 🌧️")
    report["type"] = report_type
    frames = encode_report(report)

    assert all(len(frame) <= MAX_APPLICATION_PAYLOAD for frame in frames)
    decoded = [decode_frame(frame) for frame in frames]
    assert [frame.fragment_index for frame in decoded] == list(range(len(frames)))
    assert all(frame.fragment_count == len(frames) for frame in decoded)

    result = _complete(Reassembler(), list(reversed(frames)))
    assert result.status is ReassemblyStatus.COMPLETE
    assert result.report == report
    assert result.canonical_payload == rfc8785.dumps(report)


def test_frame_chunks_are_exact_and_final_chunk_is_not_padded() -> None:
    frames = encode_report(_report(text="x" * 700))
    decoded = [decode_frame(frame) for frame in frames]
    assert all(len(frame.chunk) == CHUNK_SIZE for frame in decoded[:-1])
    assert 1 <= len(decoded[-1].chunk) <= CHUNK_SIZE
    assert sum(len(frame.chunk) for frame in decoded) == decoded[0].total_length


def test_exact_maximum_payload_uses_the_frozen_maximum_fragment_count() -> None:
    report = _report(text="")
    _, empty_text_payload = canonical_report_bytes(report)
    report["payload"]["text"] = "x" * (MAX_REPORT_SIZE - len(empty_text_payload))
    _, payload = canonical_report_bytes(report)
    frames = encode_report(report)

    assert len(payload) == MAX_REPORT_SIZE
    assert len(frames) == MAX_FRAGMENT_COUNT
    assert len(decode_frame(frames[-1]).chunk) == MAX_REPORT_SIZE - CHUNK_SIZE * 97


@pytest.mark.parametrize("mutation", ["magic", "version", "flags", "too_long"])
def test_decode_rejects_invalid_outer_frame(mutation: str) -> None:
    raw = bytearray(encode_report(_report())[0])
    if mutation == "magic":
        raw[0:2] = b"XX"
    elif mutation == "version":
        raw[2] = 2
    elif mutation == "flags":
        raw[3] = 1
    else:
        raw.extend(b"x" * (MAX_APPLICATION_PAYLOAD + 1 - len(raw)))
    with pytest.raises(FrameValidationError):
        decode_frame(raw)


def test_decode_rejects_short_header_and_inconsistent_fragment_metadata() -> None:
    with pytest.raises(FrameValidationError, match="shorter"):
        decode_frame(b"PD")

    raw = bytearray(encode_report(_report())[0])
    raw[55] += 1
    with pytest.raises(FrameValidationError, match="fragment count"):
        decode_frame(raw)

    raw = bytearray(encode_report(_report())[0])
    raw[54] = raw[55]
    with pytest.raises(FrameValidationError, match="index"):
        decode_frame(raw)


def test_decode_rejects_short_intermediate_and_wrong_final_chunks() -> None:
    frames = encode_report(_report(text="x" * 700))
    with pytest.raises(FrameValidationError, match="chunk bytes"):
        decode_frame(frames[0][:-1])
    with pytest.raises(FrameValidationError, match="chunk bytes"):
        decode_frame(frames[-1] + b"x")


def test_duplicate_fragment_is_idempotent_and_does_not_extend_timeout() -> None:
    frames = encode_report(_report())
    reassembler = Reassembler(timeout_seconds=10)
    first = reassembler.accept(frames[0], now=0)
    duplicate = reassembler.accept(frames[0], now=9)
    assert first.status is ReassemblyStatus.ACCEPTED
    assert duplicate.status is ReassemblyStatus.DUPLICATE_FRAGMENT
    assert duplicate.received_fragments == 1
    assert reassembler.expire(now=10) == 1


def test_conflicting_fragment_does_not_replace_valid_state() -> None:
    frames = encode_report(_report())
    changed = bytearray(frames[0])
    changed[-1] ^= 0x01
    reassembler = Reassembler()
    reassembler.accept(frames[0], now=0)
    with pytest.raises(FrameConflictError, match="different chunk"):
        reassembler.accept(changed, now=1)
    assert reassembler.active_count == 1


def test_same_message_id_with_another_digest_is_rejected() -> None:
    message_id = str(uuid.uuid4())
    first = encode_report(_report(message_id=message_id, text="first"))
    second = encode_report(_report(message_id=message_id, text="second"))
    reassembler = Reassembler()
    reassembler.accept(first[0], now=0)
    with pytest.raises(FrameConflictError, match="metadata"):
        reassembler.accept(second[0], now=1)


def test_corrupt_reassembled_digest_fails_and_releases_state() -> None:
    frames = encode_report(_report(text="x" * 700))
    corrupt = bytearray(frames[-1])
    corrupt[-1] ^= 0x01
    frames[-1] = bytes(corrupt)
    reassembler = Reassembler()
    with pytest.raises(TransportPayloadError, match="SHA-256"):
        _complete(reassembler, frames)
    assert reassembler.active_count == 0


def test_completed_message_replay_is_suppressed_and_conflict_is_rejected() -> None:
    message_id = str(uuid.uuid4())
    frames = encode_report(_report(message_id=message_id, text="first"))
    reassembler = Reassembler()
    complete = _complete(reassembler, frames)
    replay = reassembler.accept(frames[0], now=100)
    assert complete.status is ReassemblyStatus.COMPLETE
    assert replay.status is ReassemblyStatus.DUPLICATE_MESSAGE
    assert reassembler.completed_count == 1

    conflicting = encode_report(_report(message_id=message_id, text="second"))
    with pytest.raises(FrameConflictError, match="completed"):
        reassembler.accept(conflicting[0], now=101)


def test_completed_replay_cache_is_bounded() -> None:
    first = encode_report(_report(text="first"))
    second = encode_report(_report(text="second"))
    reassembler = Reassembler(max_completed=1)
    _complete(reassembler, first, start=0)
    _complete(reassembler, second, start=100)
    assert reassembler.completed_count == 1
    assert reassembler.accept(first[0], now=200).status is ReassemblyStatus.ACCEPTED


def test_capacity_is_bounded_and_expiration_frees_a_slot() -> None:
    first = encode_report(_report(text="first"))
    second = encode_report(_report(text="second"))
    reassembler = Reassembler(max_active=1, timeout_seconds=10)
    reassembler.accept(first[0], now=0)
    with pytest.raises(ReassemblyCapacityError):
        reassembler.accept(second[0], now=1)
    assert reassembler.expire(now=10) == 1
    assert reassembler.accept(second[0], now=10).status is ReassemblyStatus.ACCEPTED


def test_constructor_rejects_configuration_above_frozen_resource_limits() -> None:
    with pytest.raises(ValueError, match="max_active"):
        Reassembler(max_active=MAX_ACTIVE_ASSEMBLIES + 1)
    with pytest.raises(ValueError, match="timeout"):
        Reassembler(timeout_seconds=float("inf"))
    with pytest.raises(ValueError, match="now"):
        Reassembler().expire(now=-1)


def test_transport_rejects_noncanonical_uuid_and_oversized_report() -> None:
    report = _report()
    report["message_id"] = report["message_id"].upper()
    with pytest.raises(TransportPayloadError, match="canonical lowercase"):
        encode_report(report)

    oversized = _report(text="🌧️" * MAX_REPORT_SIZE)
    with pytest.raises(TransportPayloadError, match="transport limit"):
        encode_report(oversized)


def test_reconstructed_payload_must_already_be_canonical_json() -> None:
    report = _report()
    message_id, _ = canonical_report_bytes(report)
    noncanonical = json.dumps(report, indent=2).encode()
    digest = hashlib.sha256(noncanonical).digest()
    with pytest.raises(TransportPayloadError, match="not RFC 8785 canonical"):
        decode_canonical_report(
            noncanonical,
            expected_message_id=message_id,
            expected_digest=digest,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\xff", "valid UTF-8"),
        (b"{", "valid JSON"),
        (b"[]", "one report object"),
        (b"{}", "message_id"),
    ],
)
def test_reconstructed_payload_rejects_invalid_content(payload: bytes, message: str) -> None:
    with pytest.raises(TransportPayloadError, match=message):
        decode_canonical_report(
            payload,
            expected_message_id=uuid.uuid4(),
            expected_digest=hashlib.sha256(payload).digest(),
        )


def test_frame_uuid_must_match_reconstructed_report() -> None:
    report = _report()
    _, payload = canonical_report_bytes(report)
    with pytest.raises(TransportPayloadError, match="does not match"):
        decode_canonical_report(
            payload,
            expected_message_id=uuid.uuid4(),
            expected_digest=hashlib.sha256(payload).digest(),
        )


def test_zero_total_length_is_rejected_before_allocation() -> None:
    raw = bytearray(encode_report(_report())[0])
    struct.pack_into(">H", raw, 52, 0)
    with pytest.raises(FrameValidationError, match="total payload length"):
        decode_frame(raw)
