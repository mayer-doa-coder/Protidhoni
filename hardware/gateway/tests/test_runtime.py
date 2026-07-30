from __future__ import annotations

import threading

from protidhoni_lora_gateway.processor import GatewayProcessor
from protidhoni_lora_gateway.runtime import FrameWorker


class UnusedBackend:
    def submit(self, report: dict) -> str:
        raise AssertionError("invalid frames must not reach the backend")


def test_worker_queue_is_bounded_before_start() -> None:
    processor = GatewayProcessor(UnusedBackend())
    worker = FrameWorker(processor, capacity=1, stop_event=threading.Event())
    assert worker.submit(b"first")
    assert not worker.submit(b"second")
    assert processor.metrics.frame_queue_overflow == 1


def test_worker_drains_queued_frames_on_shutdown() -> None:
    processor = GatewayProcessor(UnusedBackend())
    stop = threading.Event()
    worker = FrameWorker(processor, capacity=2, stop_event=stop)
    assert worker.submit(b"invalid-frame")
    worker.start()
    worker.stop()
    assert processor.metrics.frames_received == 1
    assert processor.metrics.frames_rejected == 1
