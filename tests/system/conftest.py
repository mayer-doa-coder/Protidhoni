"""Shared fixtures for cross-service integration/system tests.

These tests exist because per-project unit suites (backend/tests,
ai-service/tests, mobile-client's jest tests, hardware/*/tests) each mock the
*other* side of every boundary they touch. That proves each project is
internally correct; it cannot prove two real implementations agree on the
wire format, the signed byte layout, or an HTTP contract. Every test in this
directory uses at least two of the real, installed packages together and
mocks only what a genuinely offline/CI environment cannot provide (a real
Postgres instance, a real Twilio/telco account, a real Meshtasticator radio
simulation) — never a second project's own code.
"""

from __future__ import annotations

import base64
import hashlib
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
import rfc8785
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from protidhoni_api import db as db_module
from protidhoni_api.main import create_app
from protidhoni_api.routes import get_db_pool

# Must match contracts/README.md's "Report signing rule" exactly — this is a
# second, independent implementation of the same rule backend/tests/factories.py
# and mobile-client/src/crypto/sign.ts each implement, on purpose: if any of the
# three ever drift apart, a test here should be the one that notices.
_SIGNED_SUBSET_KEYS = (
    "schema_version",
    "message_id",
    "type",
    "sender_pubkey",
    "sender_pubkey_hash",
    "created_at",
    "language",
    "location",
    "payload",
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class SignedReportFactory:
    """Signs reports with one freshly generated device identity per instance."""

    private_key: Ed25519PrivateKey

    @property
    def pubkey_b64(self) -> str:
        return _b64url(self.private_key.public_key().public_bytes_raw())

    @property
    def pubkey_hash_b64(self) -> str:
        return _b64url(hashlib.sha256(self.private_key.public_key().public_bytes_raw()).digest())

    def build(
        self,
        *,
        report_type: str = "SOS",
        language: str = "en",
        text: str = "Trapped on the roof, need rescue",
        people_count: int | None = 4,
        needs: list[str] | None = None,
        location: dict | None = None,
        message_id: str | None = None,
    ) -> dict:
        report = {
            "schema_version": "1.0.0",
            "message_id": message_id or str(uuid.uuid4()),
            "type": report_type,
            "sender_pubkey": self.pubkey_b64,
            "sender_pubkey_hash": self.pubkey_hash_b64,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "language": language,
            "location": location or {"lat": None, "lng": None, "accuracy_m": None, "source": "none"},
            "payload": {
                "text": text,
                "people_count": people_count,
                "needs": needs or [],
                "attachment_ref": None,
            },
            "priority": None,
            "ttl_hops": 8,
            "relay_path": [],
            "sync_status": "local",
            "verification": {"status": "unverified", "corroboration_count": 0},
        }
        canonical = rfc8785.dumps({key: report[key] for key in _SIGNED_SUBSET_KEYS})
        report["signature"] = {
            "algorithm": "Ed25519",
            "value": _b64url(self.private_key.sign(canonical)),
        }
        return report


@pytest.fixture
def signer() -> SignedReportFactory:
    return SignedReportFactory(private_key=Ed25519PrivateKey.generate())


@pytest.fixture
def report_store() -> dict[str, dict]:
    """In-memory stand-in for Postgres.

    Every route this suite exercises goes through the real
    protidhoni_api.ingestion module — real Pydantic validation, real Ed25519
    verification, real rate limiting. Only db.py's actual SQL execution is
    replaced, for the same reason backend/tests does this: a Postgres/PostGIS
    instance is real infrastructure, not something a test suite should require
    to answer "is the code correct."
    """
    return {}


@pytest.fixture
def backend_app(monkeypatch, report_store: dict[str, dict]):
    """A real FastAPI app (protidhoni_api.main.create_app()) with only the
    database layer replaced by an in-memory dict, shared by every test in this
    file via `report_store`.
    """

    async def fake_insert_report(pool, report):
        if report.message_id in report_store:
            return "duplicate"
        report_store[report.message_id] = report.model_dump(mode="json")
        return "accepted"

    async def fake_report_exists(pool, *, message_id):
        return message_id in report_store

    async def fake_list_reports(pool, *, since, bbox, limit):
        del since, bbox
        return {"reports": list(report_store.values())[:limit], "next_since": None}

    monkeypatch.setattr(db_module, "insert_report", fake_insert_report)
    monkeypatch.setattr(db_module, "report_exists", fake_report_exists)
    monkeypatch.setattr(db_module, "list_reports", fake_list_reports)

    app = create_app()
    app.dependency_overrides[get_db_pool] = lambda: object()
    return app


@pytest.fixture
async def backend_client(backend_app) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=backend_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend.test") as client:
        yield client


@pytest.fixture
def live_backend_url(backend_app) -> Iterator[str]:
    """A real backend listening on a real localhost TCP port.

    hardware/gateway's BackendClient is deliberately a *synchronous* httpx
    client — it is called from Meshtastic's synchronous TCP callback API in
    production — and httpx.ASGITransport only supports async clients cleanly.
    Rather than force an unsupported combination, this runs the same real,
    DB-mocked `backend_app` as a genuine live server, which is what
    BackendClient talks to in every real deployment anyway.
    """
    config = uvicorn.Config(backend_app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("live backend did not start within 10 seconds")
        time.sleep(0.02)

    port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    deadline = time.monotonic() + 10.0
    while True:
        try:
            if httpx.get(f"{base_url}/health", timeout=1.0).status_code == 200:
                break
        except httpx.TransportError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError("live backend never answered /health")
        time.sleep(0.02)

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


SMS_WEBHOOK_TOKEN = "s" * 32
USSD_WEBHOOK_TOKEN = "u" * 32
PHONE_PEPPER = "p" * 32


@pytest.fixture
def gateway_env(monkeypatch):
    """Enable the SMS/USSD gateway with a fresh signing identity for one test.

    The gateway's per-caller rate limiter (`gateway_routes._phone_limiter`) is a
    process-global singleton, and every test in this file uses the same fixed
    caller number — without clearing it, a test's quota usage leaks into the
    next test in the same session and produces a spurious 429.
    """
    from protidhoni_api import gateway_routes
    from protidhoni_api.config import get_settings

    seed = _b64url(Ed25519PrivateKey.generate().private_bytes_raw())
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PRIVATE_KEY", seed)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", SMS_WEBHOOK_TOKEN)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN", USSD_WEBHOOK_TOKEN)
    monkeypatch.setenv("PROTIDHONI_GATEWAY_PHONE_PEPPER", PHONE_PEPPER)
    get_settings.cache_clear()
    gateway_routes._phone_limiter._events.clear()
    yield
    get_settings.cache_clear()
