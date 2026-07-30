# Cross-service integration and system tests

Shared, cross-cutting territory (like `/docs`) — not owned by one person, per
`Protidhoni_Roadmap.md`'s Phase 6 framing: "All three: run the full path
together." Every per-project test suite (`backend/tests`, `ai-service/tests`,
`mobile-client`'s jest suite, `hardware/*/tests`) mocks the *other* side of
every boundary it touches — that's correct and necessary for fast, isolated
unit testing, but it means none of them can prove that two real
implementations actually agree with each other. This directory exists for
exactly that gap. Every test here uses at least two of the real, installed
packages together, and mocks only what a genuinely offline/CI environment
cannot provide — a real Postgres instance, a real Twilio/telco account, a real
Meshtasticator radio simulation — never a second project's own code.

## What's covered

| File | Proves |
|---|---|
| `test_mesh_report_flow.py` | A signed report round-trips through the real `POST /reports` → `GET /reports` path: real Pydantic validation, real Ed25519 verification, real idempotency, real rejection of tampered/misattributed reports, and that the stored shape carries every field `dashboard/src/api.ts`'s `CrisisReport` type requires. |
| `test_lora_transport_chain.py` | The full Phase 5 chain in one test: sign → `hardware/protocol`'s `encode_report` → `Reassembler` → `hardware/gateway`'s `BackendClient` → the real backend's ingestion and signature verification. Also proves a corrupted fragment is rejected before ever reaching the backend. |
| `test_gateway_sms_ussd.py` | Real HTTP requests against `/gateway/sms` and `/gateway/ussd`, signed with the real webhook-signature functions each adapter verifies against: acceptance, idempotency by provider id, independent adapter authentication, and that the caller's phone number never reaches storage. |
| `test_backend_ai_translation.py` | Backend's translation client and ai-service's real FastAPI app, talking to each other over `httpx.ASGITransport` (two real codebases, one process, no socket): successful round-trip via the provider's identity shortcut, and that an unconfigured/misauthenticated ai-service fails closed on the backend side. |
| `test_crypto_cross_language.py` | Shells out to Node once, running mobile-client's *actual* `canonicalize` and `@noble/ed25519` packages, and checks the output against backend's actual `rfc8785` and `cryptography` libraries: byte-identical RFC 8785 canonicalization, and a signature produced by one language's library verified by the other's. Skipped (not failed) if Node or `mobile-client/node_modules` aren't present. |

## Setup

```powershell
cd tests/system
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ..\..\backend -e ..\..\ai-service -e ..\..\hardware\protocol -e ..\..\hardware\gateway pytest pytest-asyncio httpx uvicorn ruff
```

The four `-e` installs are genuinely necessary, not incidental — this suite exists specifically to run backend, ai-service, hardware/protocol, and hardware/gateway's real code together in one process. Their dependency ranges (`fastapi>=0.115,<1.0`, `pydantic-settings>=2.7,<3.0`, etc.) were checked for compatibility before this was built; no version pin needed loosening.

## Run

```powershell
python -m pytest -q
ruff check .
```

`test_crypto_cross_language.py` additionally needs `npm install` to have been run inside `mobile-client/` at least once — it imports that directory's real `node_modules` via `mobile-client/scripts/crypto_bridge_for_system_tests.mjs` rather than shipping its own copy of the same npm packages, so there is exactly one place their versions can drift.

## Why a sync `httpx.Client` fixture exists (`live_backend_url`)

`hardware/gateway`'s `BackendClient` is deliberately synchronous — it's called from Meshtastic's synchronous TCP callback API in production — and `httpx.ASGITransport` only supports async clients cleanly (a sync `httpx.Client` bound to it can send requests but breaks on `.close()`, since `ASGITransport` only implements `aclose()`). Rather than force an unsupported combination or change production code to make it more testable, `conftest.py`'s `live_backend_url` fixture runs the same DB-mocked `backend_app` as a genuine live server on a real localhost port in a background thread — exactly what `BackendClient` talks to in every real deployment anyway.

## What this suite deliberately does not cover

- **A real Postgres/PostGIS instance.** Every test replaces `protidhoni_api.db`'s SQL execution with an in-memory dict, exactly like `backend/tests` does. This proves the ingestion *logic* (validation, crypto, idempotency, rate limiting) is correct; it does not prove a real SQL query or PostGIS geography column behaves correctly. Run the full Docker Compose stack for that.
- **A real Twilio account or a real Meshtasticator Docker simulation.** Both require external infrastructure this suite should not need to answer "is the code correct." `backend/scripts/simulate_sms_gateway.py` and `hardware/simulation/`'s scenario tooling cover those separately, against real running services.
- **The mobile-client app itself.** `test_crypto_cross_language.py` exercises its actual crypto *libraries*, not the React Native app; mobile-client's own jest suite (116 tests) is the place that exercises its screens, forms, and native module bridges.
