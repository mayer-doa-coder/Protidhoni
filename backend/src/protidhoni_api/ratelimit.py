"""In-memory rate limiting for the Phase 1 hackathon deployment.

Two independent limiters, because they defend against two different threats
(see Protidhoni_Roadmap.md §5.2 and §5.5):

- ``SenderRateLimiter`` caps how many reports a single *signed identity*
  (``sender_pubkey_hash``) may submit per minute, regardless of which device
  or relay path actually made the HTTP call. This is Sybil resistance: one
  compromised or malicious identity should not be able to flood the mesh or
  the dashboard, even if a well-behaved relay is carrying its messages.
- ``ClientIpRateLimiter`` caps requests per source IP across every public
  endpoint. This is basic abuse protection at the transport level.

Both are single-process, in-memory sliding-window limiters. That is
deliberately proportionate to a hackathon-scale single-instance deployment;
a multi-instance production deployment would need a shared store (e.g.
Redis) instead, noted here rather than built speculatively.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class SlidingWindowLimiter:
    def __init__(self, *, max_events: int, window_seconds: float) -> None:
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, *, now: float | None = None) -> bool:
        current_time = time.monotonic() if now is None else now
        events = self._events[key]
        cutoff = current_time - self._window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= self._max_events:
            return False
        events.append(current_time)
        return True


class SenderRateLimiter(SlidingWindowLimiter):
    """Caps reports per minute per sender_pubkey_hash."""

    def __init__(self, *, max_reports_per_minute: int = 10) -> None:
        super().__init__(max_events=max_reports_per_minute, window_seconds=60.0)


class ClientIpRateLimitMiddleware(BaseHTTPMiddleware):
    """Caps requests per minute per client IP across every route."""

    def __init__(self, app, *, max_requests_per_minute: int = 120) -> None:
        super().__init__(app)
        self._limiter = SlidingWindowLimiter(max_events=max_requests_per_minute, window_seconds=60.0)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not self._limiter.allow(client_ip):
            return JSONResponse(
                {"detail": "Too many requests from this client. Try again shortly."},
                status_code=429,
            )
        return await call_next(request)
