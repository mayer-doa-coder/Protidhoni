"""Bounded worker that keeps radio callbacks independent from HTTP work."""

from __future__ import annotations

import queue
import threading
import time

from .processor import GatewayProcessor


class WorkerError(RuntimeError):
    """The gateway processing worker failed or could not stop safely."""


class FrameWorker:
    def __init__(
        self,
        processor: GatewayProcessor,
        *,
        capacity: int,
        stop_event: threading.Event,
    ) -> None:
        self.processor = processor
        self.stop_event = stop_event
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=capacity)
        self._failure: Exception | None = None
        self._thread = threading.Thread(
            target=self._work,
            name="protidhoni-lora-gateway-worker",
            daemon=False,
        )

    @property
    def queued_count(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        self._thread.start()

    def submit(self, frame: bytes) -> bool:
        try:
            self._queue.put_nowait(bytes(frame))
        except queue.Full:
            self.processor.record_frame_queue_overflow()
            return False
        return True

    def _work(self) -> None:
        try:
            while not self.stop_event.is_set() or not self._queue.empty():
                try:
                    frame = self._queue.get(timeout=0.25)
                except queue.Empty:
                    self.processor.retry_pending(now=time.monotonic())
                    continue
                try:
                    self.processor.handle_frame(frame, now=time.monotonic())
                finally:
                    self._queue.task_done()
                self.processor.retry_pending(now=time.monotonic())
        # This is the worker thread's final failure boundary. Preserve any
        # unexpected dependency/programming error for the main thread instead
        # of letting the daemon thread die silently.
        except Exception as error:  # noqa: BLE001
            self._failure = error
            self.stop_event.set()

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise WorkerError("gateway processing worker failed") from self._failure

    def stop(self, *, timeout_seconds: float = 10.0) -> None:
        self.stop_event.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=timeout_seconds)
        if self._thread.is_alive():
            raise WorkerError("gateway processing worker did not stop in time")
        self.raise_if_failed()
