"""Phase 5 chain, automated: sign -> LoRa frames -> reassemble -> real backend.

This is the single highest-value integration test in this repository: it is
the only place that exercises hardware/protocol's encoder, its Reassembler,
hardware/gateway's BackendClient, and the real backend's ingestion/signature
verification all in one process. Each of those four pieces has its own unit
tests that mock the other three; this test mocks none of them.

`BackendClient` is deliberately a *synchronous* httpx client (it is called
from Meshtastic's synchronous TCP callback API in production), so these tests
run it against a real live backend on a real localhost port (`live_backend_url`
in conftest.py) rather than an in-process ASGI transport, which httpx only
supports cleanly for async clients.
"""

from __future__ import annotations

import pytest

from protidhoni_lora_gateway.backend import BackendClient
from protidhoni_lora_protocol import (
    MAX_APPLICATION_PAYLOAD,
    Reassembler,
    ReassemblyStatus,
    encode_report,
)
from protidhoni_lora_protocol.codec import ProtocolError


def test_signed_report_survives_fragmentation_and_reassembly_unchanged(signer):
    report = signer.build(
        report_type="SOS",
        language="bn",
        text="পানি এবং উদ্ধার দরকার, ৫ জন আটকা পড়েছি।",
        people_count=5,
        needs=["water", "rescue"],
        location={"lat": 23.8103, "lng": 90.4125, "accuracy_m": 12.5, "source": "gps"},
    )

    frames = encode_report(report)
    assert len(frames) > 1, "the test fixture should exercise real multi-fragment reassembly"
    assert all(len(frame) <= MAX_APPLICATION_PAYLOAD for frame in frames)

    reassembler = Reassembler()
    result = None
    for frame in frames:
        result = reassembler.accept(frame, now=0.0)

    assert result is not None
    assert result.status is ReassemblyStatus.COMPLETE
    assert result.report == report


def test_reassembled_report_is_accepted_by_the_real_backend(live_backend_url, signer, report_store):
    report = signer.build(report_type="SOS", people_count=4, needs=["rescue"])
    frames = encode_report(report)

    reassembler = Reassembler()
    result = None
    for frame in frames:
        result = reassembler.accept(frame, now=0.0)
    assert result.status is ReassemblyStatus.COMPLETE

    client = BackendClient(
        base_url=live_backend_url, timeout_seconds=5, attempts=1, retry_delay_seconds=0
    )
    try:
        outcome = client.submit(result.report)
    finally:
        client.close()

    assert outcome == "accepted"
    assert report_store[report["message_id"]]["sender_pubkey_hash"] == signer.pubkey_hash_b64


def test_replaying_the_same_reassembled_report_is_idempotent(live_backend_url, signer):
    report = signer.build()
    frames = encode_report(report)
    reassembler = Reassembler()
    for frame in frames:
        result = reassembler.accept(frame, now=0.0)

    client = BackendClient(
        base_url=live_backend_url, timeout_seconds=5, attempts=1, retry_delay_seconds=0
    )
    try:
        first = client.submit(result.report)
        second = client.submit(result.report)
    finally:
        client.close()

    assert first == "accepted"
    assert second == "duplicate"


def test_a_corrupt_fragment_is_rejected_before_ever_reaching_the_backend(signer):
    report = signer.build()
    frames = encode_report(report)
    corrupted = bytearray(frames[-1])
    corrupted[-1] ^= 0xFF  # flip the last byte of the final fragment

    reassembler = Reassembler()
    for frame in frames[:-1]:
        reassembler.accept(frame, now=0.0)

    # The corrupted final fragment completes the byte count but fails the
    # whole-payload SHA-256 digest carried in the frame header, so reassembly
    # must raise rather than silently hand a tampered report to the caller.
    with pytest.raises(ProtocolError):
        reassembler.accept(bytes(corrupted), now=0.0)
