# Protidhoni

**An offline-first crisis communication system: a phone with no internet, or a feature phone with no app at all, can still get a report to a responder's map.**

Built for the July Hackathon 2026, Crisis Tech track.

---

## 1. What it does

Three separate paths carry the same piece of information into one pool of data:

1. **A phone with the Protidhoni app**, completely offline, can create a structured crisis report (SOS, medical need, resource need, safety status, shelter info, hazard update, safe route request) and hand it to nearby phones over Bluetooth/Wi‑Fi Direct — hop by hop, with no internet at any point — until one of those phones regains connectivity and uploads the whole queue.
2. **A feature phone with no app and no internet**, just SMS or a short USSD code, gets understood the same way — the message becomes the exact same signed report shape as the app path, via a gateway that authenticates itself and signs on the sender's behalf.
3. A **zero-cost LoRa transport simulation** (Phase 5) proves the same signed report can also survive being split into small radio-sized fragments, carried across a multi-hop Meshtastic-style mesh, and reassembled byte-for-byte before reaching the backend — software/protocol readiness evidence for a future real-radio build, not a hardware claim.

A cloud backend deduplicates, rate-limits, and stores every report; an isolated AI service classifies urgency and (optionally) translates Bangla ↔ English; a responder dashboard shows everything on a map, colour-coded by priority, with a verification workflow (`unverified → corroborated → verified/disputed`) so a responder can triage hundreds of reports instead of reading each one blind.

## 2. Architecture

```
 Phone (app, offline) ──┐
                        │  Bluetooth / Wi-Fi Direct mesh, store-and-forward
 Phone (app, offline) ──┤  (mobile-client/)
                        │
 Feature phone (SMS/USSD) ── gateway (backend/) ─┐
                                                  │
 LoRa transport simulation (hardware/) ───────────┤
                                                  ▼
                                     Backend + PostgreSQL/PostGIS (backend/)
                                                  │
                                     AI/NLP service (ai-service/)
                                                  │
                                     Responder dashboard (dashboard/)
```

Every arrow into the backend carries the **same signed report shape**, frozen in `contracts/message-schema.json` on hour 0 of the build and never broken — only ever additively clarified (see `contracts/README.md`'s phase addenda). That single frozen contract is what let three people build the mesh client, the backend, and the AI/dashboard side in parallel without merge conflicts, and it's why a mesh-relayed report, a gateway-transcribed SMS, and a LoRa-reassembled report all pass through the exact same ingestion, signature verification, and deduplication code.

## 3. Repository map

```
/contracts/        Frozen message schema + OpenAPI contract. Nobody edits without team agreement.
/backend/          FastAPI + PostgreSQL/PostGIS. Report ingestion, verification, translation proxy,
                    SMS/USSD gateway, encryption at rest, rate limiting.
/mobile-client/    React Native (Android). Offline report creation, Ed25519 signing, SQLite queue,
                    Nearby Connections mesh relay, sync-on-reconnect.
/ai-service/       Isolated FastAPI microservice. Bilingual classification, translation.
/dashboard/        React + Leaflet. Map view, filters, verification workflow, channel provenance.
/hardware/         Phase 5: zero-cost LoRa transport simulation and hardware-readiness evidence.
  /protocol/         Frozen frame codec + golden vectors (Person B).
  /gateway/          Simulated-radio-to-real-backend bridge (Person A).
  /simulation/       Meshtasticator scenarios, Site Planner study, evidence tooling (Person C).
  /evidence/         Generated, non-sensitive scenario/propagation evidence.
/tests/system/     Cross-service integration and system tests (all three, shared territory).
/docs/              Architecture, demo runbook, and acceptance records.
Protidhoni_Roadmap.md   The full build plan this repository implements, phase by phase.
```

## 4. Implementation status

The implementation and automated-test status is separated from manual or external acceptance below. A passing unit/system suite does not prove a physical radio, hosted account, live telco, or published submission asset.

| Phase | Scope | Status |
|---|---|---|
| **0** | Frozen contract and all four project scaffolds | ⚠️ Code complete; hosted health check and physical two-device discovery pending |
| **1** | `POST/GET /reports`, mobile SOS creation + queue + mesh relay + sync, basic classifier, map dashboard | ⚠️ Code/tests complete; physical offline phone A → B → dashboard acceptance pending |
| **2** | All 7 report types, `PATCH /reports/{id}` verification workflow, `POST /instructions`, translation, dedup/clustering, dashboard filters | ✅ Done |
| **3** | Device keypair + Keystore wrapping, Nearby pairing confirmation, backend signature verification, encryption at rest, data-minimisation pass | ✅ Done |
| **4** | SMS + offline-USSD-simulator gateway, gateway-signed reports, independent adapter auth, phone-number minimisation | ✅ Code/tests complete; live telco traffic is not claimed |
| **5** | Frozen LoRa transport frame, simulated Meshtastic sender/gateway/reassembly, Meshtasticator scenario matrix + Site Planner propagation study | ⚠️ Simulation/tests complete; Site Planner input binding must be recaptured |
| **6** | Integration/system testing, demo, and submission packaging | ⚠️ Automated suite complete; physical/live two-run acceptance and publishing remain |

## 5. Tech stack

| Layer | Choice |
|---|---|
| Mobile client | React Native (TypeScript), Android-first; Kotlin native modules for Nearby Connections and Keystore |
| Mesh transport | Google Nearby Connections API, `P2P_CLUSTER` strategy |
| Local storage | SQLite via `@op-engineering/op-sqlite` |
| Backend | Python + FastAPI |
| Database | PostgreSQL + PostGIS |
| AI/NLP | Separate FastAPI microservice; bilingual TF-IDF + rules classifier (BanglaBERT fine-tuning path available, disclosed as optional) |
| Dashboard | React + Leaflet (OpenStreetMap tiles) |
| Signing | Ed25519 (`@noble/ed25519` on-device, `cryptography` on the backend), RFC 8785 (JCS) canonicalization |
| SMS/USSD gateway | Twilio-compatible SMS adapter + an explicitly-labelled offline USSD simulator |
| LoRa simulation | Meshtasticator (pinned commit + digest-pinned daemon image) + Meshtastic Site Planner |
| Deployment | Docker Compose locally; Render/Railway/Fly.io for the live demo |

## 6. Testing — unit, integration, and system

Every project has its own fast, isolated unit suite. On top of that, `tests/system/` exists specifically to catch the class of bug no single project's own tests can see: two independently built implementations disagreeing about a wire format, a signed byte layout, or an HTTP contract.

| Suite | Count | What it proves |
|---|---:|---|
| `backend/tests` | 183 | Signing, ingestion, rate limiting, encryption, gateway adapters, responder auth, HTTP contract |
| `ai-service/tests` | 28 | Classification, translation boundary/origin validation, internal-token auth |
| `dashboard` (vitest) | 26 | Filtering, clustering, channel provenance, API typing |
| `mobile-client` (jest) | 124 | Signing, canonicalization, SQLite queue, mesh relay, forms, configurable backend connection, sync, screens |
| `hardware/protocol/tests` | 58 | Frame codec, golden-vector round trips, boundary sizes, corruption |
| `hardware/gateway/tests` | 44 | Bounded reassembly, backend submission, retry/timeout/capacity limits |
| `hardware/simulation/tests` | 8 | Scenario/evidence tooling correctness |
| **`tests/system`** | **30** | **Cross-service: frozen-contract/runtime drift; real signed report through real `POST /reports`; the full sign→LoRa-encode→reassemble→real-backend chain in one process; real SMS/USSD HTTP requests against the gateway; backend's translation client against ai-service's real FastAPI app; mobile-client's actual `@noble/ed25519`/`canonicalize` libraries cross-verified against backend crypto** |
| **Total** | **501** | |

Run everything:

```powershell
# Backend
& .\backend\.venv\Scripts\python.exe -m pytest .\backend\tests -q
& .\backend\.venv\Scripts\ruff.exe check .\backend

# AI service
& .\ai-service\.venv\Scripts\python.exe -m pytest .\ai-service\tests -q
& .\ai-service\.venv\Scripts\ruff.exe check .\ai-service

# Dashboard
npm --prefix .\dashboard test
npm --prefix .\dashboard run typecheck

# Mobile client
npm --prefix .\mobile-client test -- --runInBand
npm --prefix .\mobile-client run lint
npm --prefix .\mobile-client run typecheck

# Phase 5 package tests (see hardware/README.md for the complete validation gate)
& .\hardware\protocol\.venv\Scripts\python.exe -m pytest .\hardware\protocol\tests -q
& .\hardware\gateway\.venv\Scripts\python.exe -m pytest .\hardware\gateway\tests -q
& .\hardware\simulation\.runtime\.venv\Scripts\python.exe -m unittest discover .\hardware\simulation\tests -v

# Cross-service integration/system suite — see tests/system/README.md for setup
& .\tests\system\.venv\Scripts\python.exe -m pytest .\tests\system -q
& .\tests\system\.venv\Scripts\ruff.exe check .\tests\system
```

Three specific things were proven, not assumed, during this system-level pass (see `tests/system/`):

- **Cross-language signature interoperability.** A report signed by mobile-client's actual `@noble/ed25519` + `canonicalize` libraries verifies against the backend's actual `cryptography` + `rfc8785` libraries — checked with a byte-for-byte diff of the canonical JSON and a real signature verification, not two separate unit tests that each mock the other side.
- **The full Phase 5 chain**, end to end, in one test: a signed report is fragmented by the real LoRa codec, reassembled by the real `Reassembler`, submitted through the real `BackendClient`, and accepted by the real backend after real Ed25519 verification — with idempotent replay and corrupted-fragment rejection both covered.
- **A real cross-platform build reproducibility bug**, found and fixed during this pass: `git config core.autocrlf=true` (the common Windows default) could rewrite Phase 5 evidence-file line endings on checkout and invalidate recorded SHA-256 hashes. `.gitattributes` now pins those byte-preserved paths to `-text`. This is separate from the disclosed Site Planner source-input mismatch, which still requires a fresh capture.

## 7. Running the full stack

```powershell
copy .env.example .env
# edit .env: replace every value beginning with "replace-" and set a real
# translation provider URL (the API key may stay blank when the provider has none)
docker compose up --build
```

This starts Postgres+PostGIS, the backend, the AI service, and the dashboard together. See each directory's own `README.md` for standalone development instructions, and `backend/README.md` for the full environment variable reference (responder token, AI internal token, encryption key, and the four SMS/USSD gateway secrets).

### Android

```powershell
$env:JAVA_HOME = "C:\path\to\jdk-17"
cd mobile-client
npm install
npx react-native run-android
```

The app automatically uses the Metro development server's host on a real debug device and `http://10.0.2.2:8000` on the Android emulator. Open the **Nearby** tab to review or change the backend URL; the value is validated and stored locally, so no contributor-specific LAN address is compiled into the app.

**JDK 17 is required, not JDK 25 or later.** This was diagnosed concretely during this pass, not assumed from a changelog: a truly clean build (`rm -rf android/app/.cxx`, no stale CMake cache) fails under JDK 25 with `configureCMakeDebug` throwing `WARNING: A restricted method in java.lang.System has been called` — the Android Gradle Plugin's native CMake integration has not been validated against newer JDKs' restricted-method enforcement. The identical clean build under JDK 17 completes `assembleDebug` and produces a working `app-debug.apk`. `mobile-client/android/build.gradle` now checks the running JDK before anything else and fails immediately with an actionable message naming the exact JDK it found, instead of failing 20+ seconds in with the cryptic native error above.

## 8. Security model

- **Identity is cryptographic, never transport-derived.** Every device generates its own Ed25519 keypair on first launch; `sender_pubkey_hash` is `SHA-256(sender_pubkey)`, never a Bluetooth MAC, phone number, or session ID. This is the specific lesson from Bridgefy's 2021 security failure (`Protidhoni_Roadmap.md` §8), and it's the reason a mesh relay never needs to be trusted — the backend verifies every report's signature independently of who carried it.
- **Every report is signed**, over the RFC 8785 canonical JSON of a fixed signed subset (`contracts/README.md`). Relay/server-owned fields (`ttl_hops`, `relay_path`, `sync_status`, `priority`, `verification`) are deliberately excluded and must never be presented as sender-authenticated.
- **The gateway signs on the sender's behalf, honestly.** A feature phone can't sign anything, so SMS/USSD reports are signed with the gateway's own key and share one `sender_pubkey_hash`, published on `GET /health` so the dashboard can label them "Gateway-attested" rather than implying they're device-verified.
- **Rate limiting** is per verified signer identity (mesh/app path) or per peppered caller pseudonym (gateway path), independent of which device's HTTP call carries the report.
- **Data minimisation**: no phone numbers, contact lists, MAC addresses, or real names are ever persisted. The gateway path is handed a caller number and reduces it to a discarded HMAC used only for in-memory rate limiting.
- **Encryption at rest**: `SOS`/`MEDICAL_NEED` report text and exact coordinates are Fernet-encrypted in Postgres; other types are plaintext JSONB, legible to responders without a decrypt step. A fail-closed, transactional migration script exists for databases created before encryption was added.

## 9. Known limitations, said out loud

- **Android is the only mobile target.** Nearby Connections supports iOS, but the implemented bridge targets Android; the required physical two-device acceptance is still recorded as pending in `docs/phase-0-acceptance.md`.
- **The SMS/USSD gateway's USSD adapter is an explicitly labelled offline simulator**, not a live telco integration; the SMS adapter uses Twilio's real signature scheme and can point at a real Twilio trial number, but no traffic has traversed a real Bangladeshi short code.
- **Phase 5 is software/protocol simulation and hardware-readiness evidence, not a hardware claim.** It proves the signed report survives fragmentation and multi-hop reassembly through a real (simulated) Meshtastic mesh and reaches the real backend unchanged. It does not validate a real antenna, RF range, electrical design, battery life, enclosure, or a phone-to-radio BLE/USB link — all of that remains explicit future work.
- **One unresolved Phase 5 evidence gap, disclosed rather than silently fixed**: the checked-in Site Planner evidence's recorded input hash does not match any committed version of its input file — the propagation model's parameters were refined after the browser-based capture ran, and the capture was never re-run against the final input. Fixing this requires a human to re-visit the Site Planner and recapture; fabricating a matching hash would have been exactly the kind of evidence integrity violation the roadmap warns against, so it was left as a known, disclosed gap instead.
- **The classification dataset is hackathon-scale.** The default classifier is a transparent bilingual TF-IDF + rules model; a real BanglaBERT fine-tuning path exists and is documented in `ai-service/README.md` but is not the default, and is disclosed as a proof of concept either way.

## 10. Team and ownership

| Person | Owns | Also owns in Phase 5 |
|---|---|---|
| A | `backend/`, security | `hardware/gateway/` |
| B | `mobile-client/` | `hardware/protocol/` |
| C | `ai-service/`, `dashboard/` | `hardware/simulation/`, `hardware/evidence/` |

`contracts/` is frozen after hour 0 and changed only by synchronous team agreement. `tests/system/` and `docs/` are shared, cross-cutting territory nobody exclusively owns.

See `docs/phase-6-acceptance.md` for the exact automated results and the manual/external work that must be completed before calling the hackathon submission finished. `docs/demo-script.md` is the corresponding three-minute recording runbook.

## 11. License

MIT — see `LICENSE`.
