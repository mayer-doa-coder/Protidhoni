# Phase 6 acceptance record

## Automated repository checks — 2026-07-30

- [x] Backend: 183 tests and Ruff pass.
- [x] AI service: 28 tests and Ruff pass.
- [x] Dashboard: 26 tests, TypeScript check, and production build pass.
- [x] Mobile: 124 tests, TypeScript check, and ESLint pass.
- [x] Android debug and release variants assemble successfully with JDK 17.
  The current release variant deliberately uses the debug signing key and is
  suitable only for a hackathon demo; generate and protect a real release key
  before any production distribution.
- [x] LoRa protocol: 58 tests pass.
- [x] LoRa gateway: 44 tests pass.
- [x] Simulation tooling: 8 tests and hardware Ruff pass.
- [x] Cross-service suite: 30 tests and Ruff pass, including frozen-contract/runtime drift checks.
- [x] Compose configuration renders from `.env.example` after placeholders are
  replaced as instructed.
- [ ] Compose runtime/real Postgres pass in this audit. Docker Desktop's Linux
  engine was not running; execute the command below once it is available.
- [ ] Phase 5 evidence validator passes. Scenario evidence passes, but the
  checked-in Site Planner manifest is not bound to the current reviewed input;
  a fresh official-planner capture is required.

## Manual end-to-end acceptance — required before submission

Record two independent rows for each path. A checkbox without the requested
notes is not acceptance evidence.

| Path | Run 1 | Run 2 | Required notes |
|---|---|---|---|
| Offline phone A → Nearby relay phone B → backend → dashboard | [ ] | [ ] | device models, Android versions, airplane-mode/radio state, timestamp |
| SMS adapter → gateway-signed report → backend → dashboard | [ ] | [ ] | provider or local simulator, timestamp, outcome |
| Explicit offline USSD simulator → backend → dashboard | [ ] | [ ] | label as simulator, timestamp, outcome |
| Backend → AI classification/translation → dashboard | [ ] | [ ] | model/provider configuration, no secrets, outcome |
| Signed report → required-relay mesh simulation → gateway → backend | [ ] | [ ] | scenario evidence directory, backend outcome |

## Packaging and external actions

- [ ] Hosted backend health endpoint recorded.
- [ ] Physical two-device Nearby discovery and offline relay accepted.
- [ ] Fresh Site Planner capture validates against the reviewed input.
- [ ] Public repository URL inserted in the submission.
- [ ] Deployed dashboard URL and/or installable APK published.
- [ ] Three-minute demo recorded and uploaded.
- [ ] Six-to-ten-slide PDF exported and checked on another device.
- [ ] Required public Facebook post published with `#JulyHackathon2026`.
- [ ] Team member names and roles entered.
- [ ] Third-party services, models, datasets, and AI coding assistance disclosed.

## Commands to finish local acceptance

```powershell
# After replacing every placeholder in .env and starting Docker Desktop:
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
Invoke-WebRequest http://localhost:5173

# Phase 5 integrity gate:
.\hardware\simulation\scripts\validate.ps1 -RequireEvidenceArtifacts
```

Do not mark Phase 6 complete until the two-run manual table and packaging list
are complete. Automated tests cannot substitute for physical radios, external
accounts, a published video, or public submission URLs.
