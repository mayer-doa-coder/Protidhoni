from fastapi import FastAPI
from fastapi.testclient import TestClient

from protidhoni_api.ratelimit import ClientIpRateLimitMiddleware, SenderRateLimiter


def test_sender_rate_limiter_allows_up_to_the_configured_burst() -> None:
    limiter = SenderRateLimiter(max_reports_per_minute=3)

    results = [limiter.allow("sender-a", now=0.0) for _ in range(3)]
    blocked = limiter.allow("sender-a", now=0.0)

    assert results == [True, True, True]
    assert blocked is False


def test_sender_rate_limiter_tracks_senders_independently() -> None:
    limiter = SenderRateLimiter(max_reports_per_minute=1)

    assert limiter.allow("sender-a", now=0.0) is True
    assert limiter.allow("sender-b", now=0.0) is True
    assert limiter.allow("sender-a", now=0.0) is False


def test_sender_rate_limiter_recovers_after_the_window_elapses() -> None:
    limiter = SenderRateLimiter(max_reports_per_minute=1)

    assert limiter.allow("sender-a", now=0.0) is True
    assert limiter.allow("sender-a", now=30.0) is False
    assert limiter.allow("sender-a", now=61.0) is True


def test_client_ip_middleware_returns_429_once_the_limit_is_exceeded() -> None:
    app = FastAPI()
    app.add_middleware(ClientIpRateLimitMiddleware, max_requests_per_minute=2)

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        first = client.get("/ping")
        second = client.get("/ping")
        third = client.get("/ping")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
