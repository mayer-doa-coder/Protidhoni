# Backend — Person A

Phase 2 adds authenticated responder operations to the Phase 1 report ingestion/retrieval backend. See `../contracts/openapi.yaml` and the Phase 1/2 addenda in `../contracts/README.md`.

## Endpoints

- `GET /health` — process health, no database required.
- `POST /reports` — batch, idempotent by `message_id`. Each report is independently signature-verified (Ed25519 over the RFC 8785 canonical signed subset) and per-sender rate-limited (10/minute by default, keyed by `sender_pubkey_hash`); a report failing either check is marked `"rejected"` in that item's result without failing the rest of the batch. Structurally invalid JSON (fails `message-schema.json`) fails the whole batch with `400`.
- `GET /reports?since=&bbox=&limit=` — `since` filters on server ingestion time (`received_at`), not the client's `created_at` (mesh-relayed reports arrive late and device clocks aren't trusted). `bbox` is `minLng,minLat,maxLng,maxLat` (WGS84) and uses the PostGIS `&&` bounding-box operator against the `reports.location` geography column.
- `PATCH /reports/{id}` — responder-only verification transition. It persists the optional responder note without adding it to the public report contract; invalid/regressive transitions return `409`.
- `POST /instructions` — responder-only signed `INSTRUCTION` or `SAFE_ROUTE` message. It verifies Ed25519 identity, persists the message idempotently, and creates an `outbound_instructions` queue entry.
- `POST /translations` — responder-only request containing a stored `message_id` and `bn`/`en` target language. The backend reads the report itself, then sends its text to the isolated AI service; it never accepts browser-provided report text or exposes translation-provider credentials.
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

**Not collected, ever, by this backend:** phone numbers, contact lists, device MAC addresses, or real names. `sender_pubkey_hash` is cryptographic, not tied to hardware or carrier identity (see the Bridgefy lesson in `Protidhoni_Roadmap.md` §8) — a report can only reveal a real name or phone number if a user voluntarily types it into `payload.text`, in which case it's covered by the encryption-at-rest described below for the report types where that's most likely to matter.

**Logging:** this service currently emits no application logs at all (`grep`-confirmed: no `logging`/`print` calls exist in `src/`). If logging is added later, `payload.text`, `location`, and `sender_pubkey` must never appear in a log line — log identifiers (`message_id`, outcome, HTTP status) instead.

## Encryption at rest

`payload.text` and `location.lat`/`location.lng` are encrypted (Fernet, AES128-CBC + HMAC-SHA256) before being stored in the `reports.raw_message` and `reports.payload` JSONB columns, but **only** for `SOS` and `MEDICAL_NEED` reports — the two types most likely to carry a specific vulnerable person's situation and exact whereabouts. Other report types are stored as plaintext JSONB, since they're meant to be broadly legible to responders without a decrypt step. Encryption/decryption is transparent to callers: `GET /reports`, `PATCH /reports/{id}`, and `POST /translations` all return decrypted plaintext to authorized callers exactly as before.

Set `PROTIDHONI_DATA_ENCRYPTION_KEY` (a 32-byte urlsafe-base64 Fernet key) before ingesting any `SOS`/`MEDICAL_NEED` report — an unset or malformed key raises immediately rather than silently storing plaintext. Generate one with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Documented limitation:** the parallel PostGIS `reports.location` geography column (used for `GET /reports`' bbox filtering) is **not** encrypted — only the JSONB copies are. Encrypting it would break `ST_MakeEnvelope`/`&&` bbox queries entirely. This is a deliberate scope decision, not an oversight — the JSONB columns are what a database backup/dump or an at-rest storage compromise would expose first, and are the parts this change actually protects.

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

The self-contained suite covers signing, rate limiting, report validation, responder authentication, verification transitions, instruction validation, and HTTP response behavior. Phase 2 was additionally exercised against a real `postgis/postgis:16-3.4` container: migration, authenticated status changes, terminal-state rejection, signed instruction queuing, idempotent retry, UUID/content conflict rejection, and persisted audit/outbox state all passed.

## Deployment hand-off

The Docker image is deployment-ready. Person A must connect this repository to the selected Render, Railway, or Fly.io project and set `PROTIDHONI_DATABASE_URL`, `PROTIDHONI_AI_INTERNAL_TOKEN`, `PROTIDHONI_RESPONDER_TOKEN`, and `PROTIDHONI_DATA_ENCRYPTION_KEY` as platform secrets, plus set `PROTIDHONI_CORS_ORIGINS` to the deployed dashboard origin; that account-level action is intentionally not performed from this repository.

**TLS:** production traffic terminates TLS at the chosen host's edge (Render/Fly.io/Railway all provision this automatically for their default domains) — no backend code change is needed for the hackathon scope. Internal traffic between the backend, AI service, and Postgres stays on the private Docker Compose network and is not separately encrypted; this is a documented hackathon-scale tradeoff, not an oversight.
