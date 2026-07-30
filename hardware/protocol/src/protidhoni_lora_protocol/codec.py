"""Reference implementation of the frozen Phase 5A binary framing.

The codec deliberately validates only transport invariants. The existing backend
remains responsible for the public JSON schema and Ed25519 trust decision.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import struct
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

import rfc8785

APPLICATION_PORT = 256
# Meshtastic's protobuf Data.payload field permits 233 bytes. The pinned daemon
# accepts 231 PRIVATE_APP bytes, but Meshtasticator cannot relay that decoded
# envelope. Its observed relay boundary is 225 bytes, so version 1 keeps one
# byte of safety margin and uses the stricter end-to-end limit below.
MAX_APPLICATION_PAYLOAD = 224
FRAME_MAGIC = b"PD"
FRAME_VERSION = 1
FRAME_FLAGS = 0
MAX_REPORT_SIZE = 16_384
REASSEMBLY_TIMEOUT_SECONDS = 600.0
REPLAY_WINDOW_SECONDS = 3_600.0
MAX_ACTIVE_ASSEMBLIES = 32
MAX_COMPLETED_MESSAGES = 256

_HEADER = struct.Struct(">2sBB16s32sHBB")
FRAME_HEADER_SIZE = _HEADER.size
CHUNK_SIZE = MAX_APPLICATION_PAYLOAD - FRAME_HEADER_SIZE
MAX_FRAGMENT_COUNT = math.ceil(MAX_REPORT_SIZE / CHUNK_SIZE)


class ProtocolError(ValueError):
    """Base class for a rejected protocol input."""


class FrameValidationError(ProtocolError):
    """A frame is malformed or violates a frozen version-1 invariant."""


class TransportPayloadError(ProtocolError):
    """A complete payload cannot be represented or trusted as canonical JSON."""


class FrameConflictError(ProtocolError):
    """Frames reuse an identifier or index with conflicting content."""


class ReassemblyCapacityError(ProtocolError):
    """The bounded active-assembly capacity is exhausted."""


def _parse_canonical_message_id(value: object) -> UUID:
    if not isinstance(value, str):
        raise TransportPayloadError("report.message_id must be a string")
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError) as error:
        raise TransportPayloadError("report.message_id must be a valid UUID") from error
    if value != str(parsed):
        raise TransportPayloadError(
            "report.message_id must use canonical lowercase hyphenated UUID text"
        )
    return parsed


def canonical_report_bytes(report: dict[str, Any]) -> tuple[UUID, bytes]:
    """Return the message UUID and RFC 8785 bytes for one complete report."""

    if not isinstance(report, dict):
        raise TransportPayloadError("report must be a JSON object")
    message_id = _parse_canonical_message_id(report.get("message_id"))
    try:
        payload = rfc8785.dumps(report)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as error:
        raise TransportPayloadError("report cannot be serialized with RFC 8785 JCS") from error
    if not payload:
        raise TransportPayloadError("canonical report payload must not be empty")
    if len(payload) > MAX_REPORT_SIZE:
        raise TransportPayloadError(
            f"canonical report payload exceeds the {MAX_REPORT_SIZE}-byte transport limit"
        )
    return message_id, payload


@dataclass(frozen=True, slots=True)
class Frame:
    """A decoded version-1 application frame."""

    message_id: UUID
    payload_digest: bytes
    total_length: int
    fragment_index: int
    fragment_count: int
    chunk: bytes
    version: int = FRAME_VERSION
    flags: int = FRAME_FLAGS

    def to_bytes(self) -> bytes:
        _validate_frame(self)
        return _HEADER.pack(
            FRAME_MAGIC,
            self.version,
            self.flags,
            self.message_id.bytes,
            self.payload_digest,
            self.total_length,
            self.fragment_index,
            self.fragment_count,
        ) + self.chunk


def _expected_fragment_count(total_length: int) -> int:
    return math.ceil(total_length / CHUNK_SIZE)


def _expected_chunk_length(total_length: int, fragment_index: int, fragment_count: int) -> int:
    if fragment_index < fragment_count - 1:
        return CHUNK_SIZE
    return total_length - CHUNK_SIZE * (fragment_count - 1)


def _validate_frame(frame: Frame) -> None:
    if frame.version != FRAME_VERSION:
        raise FrameValidationError(f"unsupported frame version: {frame.version}")
    if frame.flags != FRAME_FLAGS:
        raise FrameValidationError("version 1 requires flags=0")
    if len(frame.payload_digest) != hashlib.sha256().digest_size:
        raise FrameValidationError("payload digest must contain exactly 32 bytes")
    if not 1 <= frame.total_length <= MAX_REPORT_SIZE:
        raise FrameValidationError(
            f"total payload length must be between 1 and {MAX_REPORT_SIZE} bytes"
        )
    expected_count = _expected_fragment_count(frame.total_length)
    if frame.fragment_count != expected_count:
        raise FrameValidationError(
            f"fragment count must be {expected_count} for total length {frame.total_length}"
        )
    if not 1 <= frame.fragment_count <= MAX_FRAGMENT_COUNT:
        raise FrameValidationError(
            f"fragment count must be between 1 and {MAX_FRAGMENT_COUNT}"
        )
    if not 0 <= frame.fragment_index < frame.fragment_count:
        raise FrameValidationError("fragment index is outside the declared fragment count")
    expected_chunk_length = _expected_chunk_length(
        frame.total_length, frame.fragment_index, frame.fragment_count
    )
    if len(frame.chunk) != expected_chunk_length:
        raise FrameValidationError(
            f"fragment {frame.fragment_index} must contain {expected_chunk_length} chunk bytes"
        )
    if FRAME_HEADER_SIZE + len(frame.chunk) > MAX_APPLICATION_PAYLOAD:
        raise FrameValidationError("frame exceeds the Meshtastic application payload budget")


def decode_frame(raw_frame: bytes | bytearray | memoryview) -> Frame:
    """Decode and strictly validate one binary frame."""

    raw = bytes(raw_frame)
    if len(raw) < FRAME_HEADER_SIZE:
        raise FrameValidationError(
            f"frame is shorter than the {FRAME_HEADER_SIZE}-byte header"
        )
    if len(raw) > MAX_APPLICATION_PAYLOAD:
        raise FrameValidationError(
            f"frame exceeds the {MAX_APPLICATION_PAYLOAD}-byte Meshtastic limit"
        )
    magic, version, flags, uuid_bytes, digest, total, index, count = _HEADER.unpack_from(raw)
    if magic != FRAME_MAGIC:
        raise FrameValidationError("frame magic is not PD")
    frame = Frame(
        version=version,
        flags=flags,
        message_id=UUID(bytes=uuid_bytes),
        payload_digest=digest,
        total_length=total,
        fragment_index=index,
        fragment_count=count,
        chunk=raw[FRAME_HEADER_SIZE:],
    )
    _validate_frame(frame)
    return frame


def encode_report(report: dict[str, Any]) -> list[bytes]:
    """Canonicalize and split one complete report into version-1 frames."""

    message_id, payload = canonical_report_bytes(report)
    digest = hashlib.sha256(payload).digest()
    fragment_count = _expected_fragment_count(len(payload))
    frames: list[bytes] = []
    for fragment_index in range(fragment_count):
        start = fragment_index * CHUNK_SIZE
        chunk = payload[start : start + CHUNK_SIZE]
        frames.append(
            Frame(
                message_id=message_id,
                payload_digest=digest,
                total_length=len(payload),
                fragment_index=fragment_index,
                fragment_count=fragment_count,
                chunk=chunk,
            ).to_bytes()
        )
    return frames


def decode_canonical_report(
    payload: bytes,
    *,
    expected_message_id: UUID,
    expected_digest: bytes,
) -> dict[str, Any]:
    """Validate a reconstructed payload and return its JSON report object."""

    if not 1 <= len(payload) <= MAX_REPORT_SIZE:
        raise TransportPayloadError("reassembled payload length is outside the transport limit")
    actual_digest = hashlib.sha256(payload).digest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise TransportPayloadError("reassembled payload SHA-256 does not match the frame digest")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise TransportPayloadError("reassembled payload is not valid UTF-8") from error
    try:
        report = json.loads(text)
    except json.JSONDecodeError as error:
        raise TransportPayloadError("reassembled payload is not valid JSON") from error
    if not isinstance(report, dict):
        raise TransportPayloadError("reassembled JSON must be one report object")
    try:
        recanonicalized = rfc8785.dumps(report)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as error:
        raise TransportPayloadError("reassembled JSON cannot be canonicalized") from error
    if not hmac.compare_digest(recanonicalized, payload):
        raise TransportPayloadError("reassembled JSON is not RFC 8785 canonical bytes")
    report_message_id = _parse_canonical_message_id(report.get("message_id"))
    if report_message_id != expected_message_id:
        raise TransportPayloadError("frame UUID does not match report.message_id")
    return report


class ReassemblyStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE_FRAGMENT = "duplicate_fragment"
    COMPLETE = "complete"
    DUPLICATE_MESSAGE = "duplicate_message"


@dataclass(frozen=True, slots=True)
class ReassemblyResult:
    status: ReassemblyStatus
    message_id: UUID
    received_fragments: int
    fragment_count: int
    report: dict[str, Any] | None = None
    canonical_payload: bytes | None = None


@dataclass(slots=True)
class _Assembly:
    payload_digest: bytes
    total_length: int
    fragment_count: int
    last_progress_at: float
    chunks: dict[int, bytes] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Completed:
    payload_digest: bytes
    expires_at: float


class Reassembler:
    """Bounded, out-of-order version-1 reassembly with replay suppression."""

    def __init__(
        self,
        *,
        timeout_seconds: float = REASSEMBLY_TIMEOUT_SECONDS,
        replay_window_seconds: float = REPLAY_WINDOW_SECONDS,
        max_active: int = MAX_ACTIVE_ASSEMBLIES,
        max_completed: int = MAX_COMPLETED_MESSAGES,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if not math.isfinite(replay_window_seconds) or replay_window_seconds <= 0:
            raise ValueError("replay_window_seconds must be finite and positive")
        if not 1 <= max_active <= MAX_ACTIVE_ASSEMBLIES:
            raise ValueError(f"max_active must be between 1 and {MAX_ACTIVE_ASSEMBLIES}")
        if not 1 <= max_completed <= MAX_COMPLETED_MESSAGES:
            raise ValueError(
                f"max_completed must be between 1 and {MAX_COMPLETED_MESSAGES}"
            )
        self.timeout_seconds = timeout_seconds
        self.replay_window_seconds = replay_window_seconds
        self.max_active = max_active
        self.max_completed = max_completed
        self._active: dict[UUID, _Assembly] = {}
        self._completed: OrderedDict[UUID, _Completed] = OrderedDict()

    @staticmethod
    def _now(now: float | None) -> float:
        value = time.monotonic() if now is None else now
        if not math.isfinite(value) or value < 0:
            raise ValueError("now must be finite and non-negative")
        return value

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    def expire(self, *, now: float | None = None) -> int:
        """Drop expired incomplete/replay state and return incomplete removals."""

        current = self._now(now)
        expired_active = [
            message_id
            for message_id, state in self._active.items()
            if current - state.last_progress_at >= self.timeout_seconds
        ]
        for message_id in expired_active:
            del self._active[message_id]
        expired_completed = [
            message_id
            for message_id, state in self._completed.items()
            if current >= state.expires_at
        ]
        for message_id in expired_completed:
            del self._completed[message_id]
        return len(expired_active)

    def _remember_completed(self, message_id: UUID, digest: bytes, now: float) -> None:
        while len(self._completed) >= self.max_completed:
            self._completed.popitem(last=False)
        self._completed[message_id] = _Completed(
            payload_digest=digest,
            expires_at=now + self.replay_window_seconds,
        )

    def accept(
        self, raw_frame: bytes | bytearray | memoryview, *, now: float | None = None
    ) -> ReassemblyResult:
        """Accept one frame and return a precise, non-exceptional progress state.

        Malformed, conflicting, over-capacity, and invalid completed payloads raise
        typed protocol exceptions. Callers should reject that packet and keep the
        listener alive for unrelated messages.
        """

        frame = decode_frame(raw_frame)
        current = self._now(now)
        self.expire(now=current)

        completed = self._completed.get(frame.message_id)
        if completed is not None:
            if not hmac.compare_digest(completed.payload_digest, frame.payload_digest):
                raise FrameConflictError(
                    "completed message_id was reused with a different payload digest"
                )
            return ReassemblyResult(
                status=ReassemblyStatus.DUPLICATE_MESSAGE,
                message_id=frame.message_id,
                received_fragments=frame.fragment_count,
                fragment_count=frame.fragment_count,
            )

        state = self._active.get(frame.message_id)
        if state is None:
            if len(self._active) >= self.max_active:
                raise ReassemblyCapacityError("active reassembly capacity is exhausted")
            state = _Assembly(
                payload_digest=frame.payload_digest,
                total_length=frame.total_length,
                fragment_count=frame.fragment_count,
                last_progress_at=current,
            )
            self._active[frame.message_id] = state
        elif (
            not hmac.compare_digest(state.payload_digest, frame.payload_digest)
            or state.total_length != frame.total_length
            or state.fragment_count != frame.fragment_count
        ):
            raise FrameConflictError("message_id was reused with conflicting frame metadata")

        previous_chunk = state.chunks.get(frame.fragment_index)
        if previous_chunk is not None:
            if not hmac.compare_digest(previous_chunk, frame.chunk):
                raise FrameConflictError("fragment index was reused with different chunk bytes")
            return ReassemblyResult(
                status=ReassemblyStatus.DUPLICATE_FRAGMENT,
                message_id=frame.message_id,
                received_fragments=len(state.chunks),
                fragment_count=state.fragment_count,
            )

        state.chunks[frame.fragment_index] = frame.chunk
        state.last_progress_at = current
        if len(state.chunks) < state.fragment_count:
            return ReassemblyResult(
                status=ReassemblyStatus.ACCEPTED,
                message_id=frame.message_id,
                received_fragments=len(state.chunks),
                fragment_count=state.fragment_count,
            )

        payload = b"".join(state.chunks[index] for index in range(state.fragment_count))
        try:
            report = decode_canonical_report(
                payload,
                expected_message_id=frame.message_id,
                expected_digest=state.payload_digest,
            )
        except TransportPayloadError:
            del self._active[frame.message_id]
            raise

        del self._active[frame.message_id]
        self._remember_completed(frame.message_id, state.payload_digest, current)
        return ReassemblyResult(
            status=ReassemblyStatus.COMPLETE,
            message_id=frame.message_id,
            received_fragments=state.fragment_count,
            fragment_count=state.fragment_count,
            report=report,
            canonical_payload=payload,
        )

