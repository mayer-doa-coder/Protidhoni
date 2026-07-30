from __future__ import annotations

import copy
import uuid
from collections import deque

from protidhoni_lora_protocol import Reassembler, encode_report

from protidhoni_lora_gateway.backend import BackendRejectedError, TemporaryBackendError
from protidhoni_lora_gateway.processor import GatewayEvent, GatewayProcessor


class StubBackend:
    def __init__(self, outcomes: list[object] | None = None) -> None:
        self.outcomes = deque(["accepted"] if outcomes is None else outcomes)
        self.reports: list[dict] = []

    def submit(self, report: dict) -> str:
        self.reports.append(report)
        outcome = self.outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, str)
        return outcome


def _complete(
    processor: GatewayProcessor, report: dict, *, reverse: bool = False, now: float = 0
) -> list[GatewayEvent]:
    frames = encode_report(report)
    if reverse:
        frames.reverse()
    return [processor.handle_frame(frame, now=now + index) for index, frame in enumerate(frames)]


def _with_new_identity(report: dict, *, text: str) -> dict:
    changed = copy.deepcopy(report)
    changed["message_id"] = str(uuid.uuid4())
    changed["payload"]["text"] = text
    return changed


def test_reordered_multifragment_report_is_submitted_once(signed_report: dict) -> None:
    backend = StubBackend()
    processor = GatewayProcessor(backend)
    events = _complete(processor, signed_report, reverse=True)
    assert events[-1] is GatewayEvent.REPORT_ACCEPTED
    assert backend.reports == [signed_report]

    for frame in encode_report(signed_report):
        assert processor.handle_frame(frame, now=100) is GatewayEvent.DUPLICATE_MESSAGE
    assert backend.reports == [signed_report]
    assert processor.metrics.duplicate_messages == len(encode_report(signed_report))


def test_duplicate_and_missing_fragments_do_not_submit(signed_report: dict) -> None:
    backend = StubBackend()
    processor = GatewayProcessor(backend)
    frames = encode_report(signed_report)
    assert processor.handle_frame(frames[0], now=0) is GatewayEvent.FRAME_ACCEPTED
    assert processor.handle_frame(frames[0], now=1) is GatewayEvent.DUPLICATE_FRAGMENT
    for index, frame in enumerate(frames[1:-1], start=2):
        processor.handle_frame(frame, now=float(index))
    assert backend.reports == []
    assert processor.reassembler.active_count == 1


def test_corruption_and_conflicting_metadata_are_rejected(signed_report: dict) -> None:
    backend = StubBackend()
    processor = GatewayProcessor(backend)
    corrupt_frames = encode_report(signed_report)
    corrupt_frames[-1] = corrupt_frames[-1][:-1] + bytes([corrupt_frames[-1][-1] ^ 1])
    events = [
        processor.handle_frame(frame, now=float(index))
        for index, frame in enumerate(corrupt_frames)
    ]
    assert events[-1] is GatewayEvent.FRAME_REJECTED
    assert backend.reports == []

    first = _with_new_identity(signed_report, text="first")
    conflicting = copy.deepcopy(first)
    conflicting["payload"]["text"] = "different canonical bytes"
    assert processor.handle_frame(encode_report(first)[0], now=100) is GatewayEvent.FRAME_ACCEPTED
    assert (
        processor.handle_frame(encode_report(conflicting)[0], now=101)
        is GatewayEvent.FRAME_REJECTED
    )


def test_timeout_cleanup_and_active_capacity_are_enforced(signed_report: dict) -> None:
    backend = StubBackend()
    reassembler = Reassembler(timeout_seconds=1, max_active=1)
    processor = GatewayProcessor(backend, reassembler=reassembler)
    first = _with_new_identity(signed_report, text="first incomplete")
    second = _with_new_identity(signed_report, text="second incomplete")
    assert processor.handle_frame(encode_report(first)[0], now=0) is GatewayEvent.FRAME_ACCEPTED
    assert processor.handle_frame(encode_report(second)[0], now=0.5) is GatewayEvent.FRAME_REJECTED
    assert reassembler.active_count == 1
    assert processor.handle_frame(encode_report(second)[0], now=1) is GatewayEvent.FRAME_ACCEPTED
    assert reassembler.active_count == 1


def test_temporary_backend_outage_is_deferred_then_recovered(signed_report: dict) -> None:
    backend = StubBackend([TemporaryBackendError("offline"), "accepted"])
    processor = GatewayProcessor(
        backend,
        pending_capacity=2,
        pending_retry_seconds=5,
        pending_ttl_seconds=60,
    )
    completed_at = float(len(encode_report(signed_report)) - 1)
    assert _complete(processor, signed_report, now=0)[-1] is GatewayEvent.REPORT_DEFERRED
    assert processor.pending_count == 1
    assert processor.retry_pending(now=completed_at + 4) == 0
    assert processor.retry_pending(now=completed_at + 5) == 1
    assert processor.pending_count == 0
    assert processor.metrics.reports_accepted == 1


def test_pending_queue_is_bounded_and_entries_expire(signed_report: dict) -> None:
    backend = StubBackend(
        [
            TemporaryBackendError("offline"),
            TemporaryBackendError("offline"),
            TemporaryBackendError("offline"),
        ]
    )
    processor = GatewayProcessor(
        backend,
        pending_capacity=1,
        pending_retry_seconds=10,
        pending_ttl_seconds=20,
    )
    first = signed_report
    second = _with_new_identity(signed_report, text="second")
    assert _complete(processor, first, now=0)[-1] is GatewayEvent.REPORT_DEFERRED
    assert _complete(processor, second, now=5)[-1] is GatewayEvent.REPORT_DROPPED
    assert processor.pending_count == 1
    assert processor.metrics.pending_overflow == 1
    assert processor.retry_pending(now=30) == 0
    assert processor.pending_count == 0
    assert processor.metrics.pending_expired == 1


def test_backend_rejection_is_final_and_report_data_is_not_logged(
    signed_report: dict, caplog
) -> None:
    backend = StubBackend([BackendRejectedError("do not include payload")])
    processor = GatewayProcessor(backend)
    assert _complete(processor, signed_report)[-1] is GatewayEvent.REPORT_REJECTED
    assert processor.pending_count == 0
    assert signed_report["payload"]["text"] not in caplog.text
    assert signed_report["sender_pubkey"] not in caplog.text
