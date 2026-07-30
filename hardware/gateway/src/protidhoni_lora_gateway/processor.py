"""Frame processing, bounded reassembly, and deferred backend submission."""

from __future__ import annotations

import logging
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from protidhoni_lora_protocol import Reassembler, ReassemblyStatus
from protidhoni_lora_protocol.codec import ProtocolError

from .backend import BackendRejectedError, PermanentBackendError, TemporaryBackendError

logger = logging.getLogger(__name__)


class BackendSubmitter(Protocol):
    def submit(self, report: dict[str, Any]) -> str: ...


class GatewayEvent(str, Enum):
    FRAME_ACCEPTED = "frame_accepted"
    DUPLICATE_FRAGMENT = "duplicate_fragment"
    DUPLICATE_MESSAGE = "duplicate_message"
    REPORT_ACCEPTED = "report_accepted"
    REPORT_DUPLICATE = "report_duplicate"
    REPORT_DEFERRED = "report_deferred"
    REPORT_REJECTED = "report_rejected"
    REPORT_DROPPED = "report_dropped"
    FRAME_REJECTED = "frame_rejected"


@dataclass(slots=True)
class GatewayMetrics:
    frames_received: int = 0
    frames_rejected: int = 0
    duplicate_fragments: int = 0
    duplicate_messages: int = 0
    reports_accepted: int = 0
    reports_duplicate: int = 0
    reports_deferred: int = 0
    reports_rejected: int = 0
    pending_expired: int = 0
    pending_overflow: int = 0
    frame_queue_overflow: int = 0


@dataclass(slots=True)
class _PendingSubmission:
    report: dict[str, Any]
    queued_at: float
    next_attempt_at: float


class GatewayProcessor:
    """Convert frames into reports while bounding every retained collection."""

    def __init__(
        self,
        backend: BackendSubmitter,
        *,
        reassembler: Reassembler | None = None,
        pending_capacity: int = 32,
        pending_retry_seconds: float = 10.0,
        pending_ttl_seconds: float = 3_600.0,
    ) -> None:
        if not 1 <= pending_capacity <= 32:
            raise ValueError("pending_capacity must be between 1 and 32")
        if not math.isfinite(pending_retry_seconds) or pending_retry_seconds <= 0:
            raise ValueError("pending_retry_seconds must be finite and positive")
        if not math.isfinite(pending_ttl_seconds) or pending_ttl_seconds <= pending_retry_seconds:
            raise ValueError(
                "pending_ttl_seconds must be finite and greater than pending_retry_seconds"
            )
        self.backend = backend
        self.reassembler = Reassembler() if reassembler is None else reassembler
        self.pending_capacity = pending_capacity
        self.pending_retry_seconds = pending_retry_seconds
        self.pending_ttl_seconds = pending_ttl_seconds
        self.metrics = GatewayMetrics()
        self._pending: OrderedDict[UUID, _PendingSubmission] = OrderedDict()

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def record_frame_queue_overflow(self) -> None:
        self.metrics.frame_queue_overflow += 1

    def handle_frame(self, raw_frame: bytes, *, now: float | None = None) -> GatewayEvent:
        current = time.monotonic() if now is None else now
        self.retry_pending(now=current)
        self.metrics.frames_received += 1
        try:
            result = self.reassembler.accept(raw_frame, now=current)
        except ProtocolError as error:
            self.metrics.frames_rejected += 1
            logger.warning("Rejected transport frame: %s", type(error).__name__)
            return GatewayEvent.FRAME_REJECTED

        if result.status is ReassemblyStatus.ACCEPTED:
            return GatewayEvent.FRAME_ACCEPTED
        if result.status is ReassemblyStatus.DUPLICATE_FRAGMENT:
            self.metrics.duplicate_fragments += 1
            return GatewayEvent.DUPLICATE_FRAGMENT
        if result.status is ReassemblyStatus.DUPLICATE_MESSAGE:
            self.metrics.duplicate_messages += 1
            return GatewayEvent.DUPLICATE_MESSAGE

        if result.report is None:
            raise RuntimeError("complete reassembly returned no report")
        return self._submit_or_defer(result.message_id, result.report, now=current)

    def _submit_or_defer(
        self, message_id: UUID, report: dict[str, Any], *, now: float
    ) -> GatewayEvent:
        try:
            outcome = self.backend.submit(report)
        except TemporaryBackendError:
            if len(self._pending) >= self.pending_capacity:
                self.metrics.pending_overflow += 1
                logger.error("Pending submission capacity exhausted; report_id=%s", message_id)
                return GatewayEvent.REPORT_DROPPED
            self._pending[message_id] = _PendingSubmission(
                report=report,
                queued_at=now,
                next_attempt_at=now + self.pending_retry_seconds,
            )
            self.metrics.reports_deferred += 1
            logger.warning("Deferred report submission; report_id=%s", message_id)
            return GatewayEvent.REPORT_DEFERRED
        except (BackendRejectedError, PermanentBackendError) as error:
            self.metrics.reports_rejected += 1
            logger.warning(
                "Backend rejected reconstructed report; report_id=%s reason=%s",
                message_id,
                type(error).__name__,
            )
            return GatewayEvent.REPORT_REJECTED
        return self._record_success(message_id, outcome)

    def _record_success(self, message_id: UUID, outcome: str) -> GatewayEvent:
        if outcome == "accepted":
            self.metrics.reports_accepted += 1
            logger.info("Backend accepted reconstructed report; report_id=%s", message_id)
            return GatewayEvent.REPORT_ACCEPTED
        if outcome == "duplicate":
            self.metrics.reports_duplicate += 1
            logger.info("Backend confirmed duplicate report; report_id=%s", message_id)
            return GatewayEvent.REPORT_DUPLICATE
        raise RuntimeError("backend adapter returned an unsupported outcome")

    def retry_pending(self, *, now: float | None = None) -> int:
        current = time.monotonic() if now is None else now
        completed = 0
        for message_id, pending in list(self._pending.items()):
            if current - pending.queued_at >= self.pending_ttl_seconds:
                del self._pending[message_id]
                self.metrics.pending_expired += 1
                logger.warning("Expired pending report submission; report_id=%s", message_id)
                continue
            if current < pending.next_attempt_at:
                continue
            try:
                outcome = self.backend.submit(pending.report)
            except TemporaryBackendError:
                pending.next_attempt_at = current + self.pending_retry_seconds
                continue
            except (BackendRejectedError, PermanentBackendError) as error:
                del self._pending[message_id]
                self.metrics.reports_rejected += 1
                logger.warning(
                    "Backend rejected deferred report; report_id=%s reason=%s",
                    message_id,
                    type(error).__name__,
                )
                completed += 1
                continue
            del self._pending[message_id]
            self._record_success(message_id, outcome)
            completed += 1
        return completed
