# Backend — Person A

Phase 1 implements report ingestion and retrieval against the frozen contract in `../contracts/openapi.yaml` (see `../contracts/README.md` for the Phase 1 addendum: the `rejected` outcome value and the `since`/rate-limiting semantics).

## Endpoints

- `GET /health` — process health, no database required.
- `POST /reports` — batch, idempotent by `message_id`. Each report is independently signature-verified (Ed25519 over the RFC 8785 canonical signed subset) and per-sender rate-limited (10/minute by default, keyed by `sender_pubkey_hash`); a report failing either check is marked `"rejected"` in that item's result without failing the rest of the batch. Structurally invalid JSON (fails `message-schema.json`) fails the whole batch with `400`.
- `GET /reports?since=&bbox=&limit=` — `since` filters on server ingestion time (`received_at`), not the client's `created_at` (mesh-relayed reports arrive late and device clocks aren't trusted). `bbox` is `minLng,minLat,maxLng,maxLat` (WGS84) and uses the PostGIS `&&` bounding-box operator against the `reports.location` geography column.
- `POST /instructions`, `PATCH /reports/{id}`, `POST /ai/classify` — contract-defined, not yet implemented (Phase 2).

Both endpoints require `PROTIDHONI_DATABASE_URL` to be configured; without it they return `503` (health still works, so the process can start and be probed before the database is ready).

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:PYTHONPATH = "src"
uvicorn protidhoni_api.main:app --reload
```

Check `GET http://localhost:8000/health`. The containerized full stack (Postgres+PostGIS, backend, AI service, dashboard) is started from the repository root with `docker compose up --build` after copying `.env.example` to `.env` and setting real local-only values. `.env.example`'s `DATABASE_URL` uses a plain `postgresql://` scheme — this project talks to Postgres directly through `psycopg`, not SQLAlchemy, so a SQLAlchemy-style `postgresql+psycopg://` DSN will fail to parse.

## Testing

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests -q
```

All 32 tests are self-contained (no live database required) — `POST`/`GET /reports` are tested against the real signing/rate-limiting/validation logic with the database layer mocked out. They were additionally verified end-to-end against a real `postgis/postgis:16-3.4` container during development (genuinely signed reports, tampered-signature rejection, per-sender rate-limit tripping, bbox spatial filtering, and UTF-8 Bangla text round-tripping through Postgres all confirmed) — that run isn't automated here since it needs Docker Desktop running, but is the recommended manual check before considering a change to `db.py` or the SQL in it verified.

## Deployment hand-off

The Docker image is deployment-ready. Person A must connect this repository to the selected Render, Railway, or Fly.io project and set `PROTIDHONI_DATABASE_URL` and `PROTIDHONI_AI_INTERNAL_TOKEN` as platform secrets; that account-level action is intentionally not performed from this repository.
