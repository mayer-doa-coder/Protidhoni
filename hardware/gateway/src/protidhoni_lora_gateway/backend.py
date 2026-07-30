"""Strict adapter for the existing Protidhoni report-ingestion endpoint."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any

import httpx


class BackendSubmissionError(RuntimeError):
    """Base class for a backend submission failure."""


class TemporaryBackendError(BackendSubmissionError):
    """The report should be retried later without changing it."""


class PermanentBackendError(BackendSubmissionError):
    """The backend permanently rejected the request or broke its contract."""


class BackendRejectedError(PermanentBackendError):
    """The backend returned the explicit per-report rejected outcome."""


class BackendClient:
    """Submit one reconstructed report with bounded transient retries."""

    _TRANSIENT_STATUS_CODES = frozenset({408, 425, 429})

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        attempts: int,
        retry_delay_seconds: float,
        sleeper: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if isinstance(attempts, bool) or not 1 <= attempts <= 10:
            raise ValueError("attempts must be between 1 and 10")
        if not math.isfinite(retry_delay_seconds) or not 0 <= retry_delay_seconds <= 60:
            raise ValueError("retry_delay_seconds must be between 0 and 60")
        self._attempts = attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    def close(self) -> None:
        self._client.close()

    def submit(self, report: dict[str, Any]) -> str:
        message_id = report.get("message_id")
        if not isinstance(message_id, str):
            raise PermanentBackendError("reassembled report has no string message ID")

        last_temporary_status: int | None = None
        for attempt_index in range(self._attempts):
            try:
                response = self._client.post("/reports", json={"reports": [report]})
            except httpx.RequestError as error:
                if attempt_index + 1 >= self._attempts:
                    raise TemporaryBackendError(
                        "backend report submission is unavailable"
                    ) from error
                self._sleep_before_retry(attempt_index)
                continue

            if response.status_code == 202:
                return self._parse_outcome(response, expected_message_id=message_id)
            if response.status_code in self._TRANSIENT_STATUS_CODES or response.status_code >= 500:
                last_temporary_status = response.status_code
                if attempt_index + 1 < self._attempts:
                    self._sleep_before_retry(attempt_index)
                    continue
                break
            raise PermanentBackendError(
                f"backend rejected the report batch with HTTP {response.status_code}"
            )

        status_suffix = f" (HTTP {last_temporary_status})" if last_temporary_status else ""
        raise TemporaryBackendError(f"backend report submission is unavailable{status_suffix}")

    def _sleep_before_retry(self, attempt_index: int) -> None:
        delay = min(self._retry_delay_seconds * (2**attempt_index), 60.0)
        if delay > 0:
            self._sleeper(delay)

    @staticmethod
    def _parse_outcome(response: httpx.Response, *, expected_message_id: str) -> str:
        try:
            document = response.json()
        except ValueError as error:
            raise PermanentBackendError("backend returned an invalid ingestion response") from error
        if not isinstance(document, dict) or set(document) != {"results"}:
            raise PermanentBackendError("backend returned an invalid ingestion response")
        results = document["results"]
        if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
            raise PermanentBackendError("backend returned an invalid ingestion response")
        result = results[0]
        if (
            set(result) != {"message_id", "outcome"}
            or result.get("message_id") != expected_message_id
        ):
            raise PermanentBackendError("backend returned an invalid ingestion response")
        outcome = result.get("outcome")
        if outcome == "rejected":
            raise BackendRejectedError("backend rejected the report")
        if outcome not in {"accepted", "duplicate"}:
            raise PermanentBackendError("backend returned an invalid ingestion response")
        return outcome
