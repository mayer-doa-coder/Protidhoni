# Backend — Person A

Phase 2 adds authenticated responder operations to the Phase 1 report ingestion/retrieval backend. See `../contracts/openapi.yaml` and the Phase 1/2 addenda in `../contracts/README.md`.

## Endpoints

- `GET /health` — process health, no database required.
- `POST /reports` — batch, idempotent by `message_id`. Each report is independently signature-verified (Ed25519 over the RFC 8785 canonical signed subset) and per-sender rate-limited (10/minute by default, keyed by `sender_pubkey_hash`); a report failing either check is marked `"rejected"` in that item's result without failing the rest of the batch. Structurally invalid JSON (fails `message-schema.json`) fails the whole batch with `400`.
- `GET /reports?since=&bbox=&limit=` — `since` filters on server ingestion time (`received_at`), not the client's `created_at` (mesh-relayed reports arrive late and device clocks aren't trusted). `bbox` is `minLng,minLat,maxLng,maxLat` (WGS84) and uses the PostGIS `&&` bounding-box operator against the `reports.location` geography column.
- `PATCH /reports/{id}` — responder-only verification transition. It persists the optional responder note without adding it to the public report contract; invalid/regressive transitions return `409`.
- `POST /instructions` — responder-only signed `INSTRUCTION` or `SAFE_ROUTE` message. It verifies Ed25519 identity, persists the message idempotently, and creates an `outbound_instructions` queue entry.
- `POST /translations` — responder-only request containing a stored `message_id` and `bn`/`en` target language. The backend reads the report itself, then sends its text to the isolated AI service; it never accepts browser-provided report text or exposes translation-provider credentials.
- `POST /gateway/sms` — Twilio-facing. One authenticated inbound SMS becomes one signed report; the response is empty TwiML (`<Response/>`). Idempotent by the provider's `MessageSid`.
- `POST /gateway/ussd` — offline-simulator-facing. Advances one USSD menu turn, returning plain text (`CON …` to continue, `END …` to finish) and storing a report only when the session completes. Idempotent by `sessionId`. A live USSD provider needs its own adapter.
- `POST /ai/classify` — implemented by the separate AI service, not this process.

Database-backed endpoints require `PROTIDHONI_DATABASE_URL`. The three responder-only endpoints additionally require `PROTIDHONI_RESPONDER_TOKEN` and the matching `X-Responder-Token` header. If the server token is unset, access remains disabled with `503`; missing/incorrect request credentials return `401`. Set `PROTIDHONI_CORS_ORIGINS` to a comma-separated allow-list of dashboard origins; wildcards and URL paths are rejected.

Translation also requires a non-blank 32-character-or-longer `PROTIDHONI_AI_INTERNAL_TOKEN` shared only with the AI service and `PROTIDHONI_AI_SERVICE_URL` (Compose default: `http://ai-service:8001`). A missing/unsafe internal credential or unreachable AI/provider returns `503`; malformed AI replies return `502` without exposing internal details.

Generate a token from at least 32 cryptographically random bytes, store it only in `.env`/your deployment secret manager, and give it only to the responder dashboard deployment:

```powershell
[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

## Data minimisation

Per `Protidhoni_Roadmap.md` §5.5, this service states plainly what it collects and why, rather than silently accumulating more than the mission needs.

**Collected, and why each field exists:**
- `sender_pubkey_hash` — a pseudonymous device identity derived from an on-device Ed25519 key (`SHA-256(sender_pubkey)`). Needed to attribute a report to a consistent identity for rate limiting and corroboration counting, without ever knowing who that identity actually belongs to.
- `payload.text` — the free-text report body a person chooses to write. Needed because it's the actual crisis content responders and the AI classifier act on.
- `location.lat/lng` (optional, user- or GPS-supplied) — needed for the map view and bbox queries responders use to triage by area.
- `payload.people_count` / `payload.needs` (optional) — structured hints (e.g. "medical", "shelter") needed so responders and the classifier can triage without re-reading full text every time.

**Provider metadata not persisted by this backend:** carrier-supplied phone numbers, contact lists, device MAC addresses, and real names. The SMS/USSD path is handed a caller number; it normalizes it, reduces it to a peppered HMAC used only for in-memory rate limiting, and discards the original. User-entered `payload.text` is retained as submitted and can contain a phone number or name if the user deliberately types one. `sender_pubkey_hash` is cryptographic and is not derived from carrier or transport identity.

**Logging:** this service currently emits no application logs at all (`grep`-confirmed: no `logging`/`print` calls exist in `src/`). If logging is added later, `payload.text`, `location`, and `sender_pubkey` must never appear in a log line — log identifiers (`message_id`, outcome, HTTP status) instead.

## SMS/USSD gateway (Phase 4)

The third path into the system: a phone with no app, no internet, and no ability to sign anything still reaches responders. See the Phase 4 addendum in `../contracts/README.md` for the contract implications.

**The gateway signs on the sender's behalf.** The frozen schema requires a valid Ed25519 signature on every report and a feature phone can produce none, so the gateway holds its own keypair and signs the transcribed report itself. That signature attests *"this gateway received this SMS/USSD session and transcribed it"* — **not** *"this device authored this content"*, which is what a mesh report's signature attests. Every report from this path therefore shares one `sender_pubkey_hash`, published as `gateway_pubkey_hash` on `GET /health` so the dashboard can label the channel honestly.

**Provider-supplied caller metadata is never stored.** Each adapter receives a caller number, requires canonical E.164 form, and HMACs it with `PROTIDHONI_GATEWAY_PHONE_PEPPER` for an in-memory limit of five new reports per minute. Provider retries are recognized before consuming quota. The original number is discarded and never copied into a report. A number deliberately typed in SMS `Body` remains part of the user's report text; the tests cover both sides of this boundary.

**One ingestion policy.** Both gateway routes and `POST /reports` use `ingestion.ingest_signed_report`, which verifies the Ed25519 signature before applying the appropriate limiter and calling the database. Device reports are limited by verified signer hash; gateway reports are limited by the peppered caller pseudonym because all gateway reports share one signing identity.

**No synchronous AI dependency.** Gateway reports are stored with `priority: null`. The ingestion request does not call the AI service, so an unavailable AI container cannot drop an incoming crisis message. Any future enrichment worker is a separate pipeline and is not claimed as part of Phase 4.

**Location honesty.** Coordinates typed into an SMS (`23.8103,90.4125` anywhere in the body) are recorded as `source: "manual"` — a human assertion, never a device measurement, so `"gps"` is never claimed. USSD menus cannot practically capture coordinates on a feature phone, so those reports carry `source: "none"` rather than a fabricated position.

Set `PROTIDHONI_GATEWAY_PRIVATE_KEY`, `PROTIDHONI_GATEWAY_WEBHOOK_TOKEN`, `PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN`, and `PROTIDHONI_GATEWAY_PHONE_PEPPER`; leaving the credential required by an adapter blank disables that adapter with `503`. The SMS and USSD secrets must be different. Generate the signing seed and pepper with:

```powershell
python .\backend\scripts\configure_gateway_env.py
```

The helper fills only missing or blank values in the ignored `.env`, preserves all existing settings, and never prints a secret. For the zero-cost simulator, the generated `GATEWAY_WEBHOOK_TOKEN` acts as the local Twilio-signature test secret. For a real Twilio number, replace only that value with the Account Auth Token from Twilio Console; the gateway never receives it from an incoming request.

### Exercising it at zero cost

`scripts/simulate_sms_gateway.py` exercises both paths without mocking backend behavior. Its SMS request uses Twilio's documented form-signature algorithm. Its USSD request uses Protidhoni's separate local-simulator signature and is not represented as Twilio or as a live aggregator. No telco account, credit card, or tunnel is required.

```powershell
python .\backend\scripts\simulate_sms_gateway.py sms
python .\backend\scripts\simulate_sms_gateway.py ussd
python .\backend\scripts\simulate_sms_gateway.py sms --body "সাহায্য দরকার! ৩ জন আটকা পড়েছি, পানি নেই"
```

For local use the simulator reads the generated values directly from the ignored root `.env`; it never displays them. Explicit `PROTIDHONI_GATEWAY_WEBHOOK_TOKEN` and `PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN` process variables override the file when needed.

The `sms` run also replays its own callback to prove provider retries deduplicate instead of putting the same incident on a responder's map twice.

**Disclosed limitation, per `Protidhoni_Roadmap.md` §9:** no traffic has traversed a real Bangladeshi short code or USSD aggregator. A Twilio SMS trial can use the existing SMS adapter after configuring its Auth Token and public HTTPS callback URL. A local USSD provider requires a small adapter for that provider's documented field names, response convention, and authentication method; it is not honestly a configuration-only change. Live-provider interoperability remains a manual check.

## Encryption at rest

`payload.text` and exact `location.lat`/`location.lng` are encrypted (Fernet, AES128-CBC + HMAC-SHA256) before being stored in the `reports.raw_message` and `reports.payload` JSONB columns, but **only** for `SOS` and `MEDICAL_NEED` reports — the two types most likely to carry a specific vulnerable person's situation and exact whereabouts. Other report types are stored as plaintext JSONB, since they're meant to be broadly legible to responders without a decrypt step. Encryption/decryption is transparent to callers: `GET /reports`, `PATCH /reports/{id}`, and `POST /translations` all return decrypted plaintext to authorized callers exactly as before.

Set `PROTIDHONI_DATA_ENCRYPTION_KEY` (a 32-byte urlsafe-base64 Fernet key) before ingesting any `SOS`/`MEDICAL_NEED` report — an unset or malformed key raises immediately rather than silently storing plaintext. Generate one with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The parallel PostGIS `reports.location` geography column stays plaintext so `GET /reports?bbox=` can keep using PostGIS, but for `SOS` and `MEDICAL_NEED` reports it stores only coordinates rounded to two decimal places. The exact vulnerable-person coordinates remain available only in encrypted JSONB and are decrypted on authorized reads.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:PYTHONPATH = "src"
python -m protidhoni_api
```

Check `GET http://localhost:8000/health`. Use the package command above on Windows: it selects the `SelectorEventLoop` required by async Psycopg without relying on Python's deprecated global event-loop policy. The containerized full stack (Postgres+PostGIS, backend, AI service, dashboard) is started from the repository root with `docker compose up --build` after copying `.env.example` to `.env` and setting real local-only values. `.env.example`'s `DATABASE_URL` uses a plain `postgresql://` scheme — this project talks to Postgres directly through `psycopg`, not SQLAlchemy, so a SQLAlchemy-style `postgresql+psycopg://` DSN will fail to parse.

For an existing Phase 1 database volume, apply the Phase 2 migration once before starting the updated backend:

```powershell
Get-Content .\backend\db\migrations\002_phase2.sql -Raw |
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U protidhoni -d protidhoni -f -
```

Use your configured `POSTGRES_USER`/`POSTGRES_DB` instead of `protidhoni` if they differ.

## Manual responder check

First retrieve a real report identifier. Do not use the literal text
`<existing-report-uuid>`: it is only documentation notation, not a valid UUID.
If your local API has no reports yet, seed one valid development report first:

```powershell
$env:PYTHONPATH = ".\backend\src"
$reportId = python .\backend\scripts\submit_demo_report.py
```

The seeder creates a fresh ephemeral Ed25519 identity and submits one signed,
unverified SOS report. It is development-only and does not replace the mobile
client's persistent device identity.

```powershell
$reports = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/reports?limit=1"
if ($reports.reports.Count -eq 0) {
  throw "No report is available to update. Sync or submit a valid signed report first."
}
$reportId = $reports.reports[0].message_id
$token = Read-Host -MaskInput "Responder token"

Invoke-RestMethod `
  -Method Patch `
  -Uri "http://localhost:8000/reports/$reportId" `
  -Headers @{"X-Responder-Token" = $token} `
  -ContentType "application/json" `
  -Body '{"status":"corroborated","responder_note":"Confirmed by responder"}'
```

The report must have a current verification state that can transition to
`corroborated`; use a newly ingested `unverified` report for this check.

## Testing

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -q
```

The self-contained suite covers signing, shared ingestion, provider-bound authentication, request limits, idempotent retries, phone-metadata minimisation, report validation, rate limiting, responder authentication, verification transitions, instruction validation, and HTTP response behavior. Phase 2 was additionally exercised against a real `postgis/postgis:16-3.4` container.

## Deployment hand-off

The Docker image is deployment-ready. Person A must connect this repository to the selected host and set the database, AI, responder, encryption, gateway signing, Twilio SMS, simulated-USSD, and phone-pepper values as platform secrets. `PROTIDHONI_GATEWAY_PUBLIC_BASE_URL` must be the externally configured HTTPS origin when a proxy changes the URL seen by FastAPI.

**TLS:** production traffic terminates TLS at the chosen host's edge (Render/Fly.io/Railway all provision this automatically for their default domains) — no backend code change is needed for the hackathon scope. Internal traffic between the backend, AI service, and Postgres stays on the private Docker Compose network and is not separately encrypted; this is a documented hackathon-scale tradeoff, not an oversight.
