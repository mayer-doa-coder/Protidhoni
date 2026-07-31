# Mobile client — Person B

Phase 2 extends the core offline path to every user-creatable report type while preserving the Phase 1 signed-message, SQLite queue, mesh relay, and sync behavior.

## What's implemented

- **Identity & signing** (`src/crypto/`) — a real Ed25519 keypair is generated on first launch (`@noble/ed25519` + `@noble/hashes`, not the Node/browser WebCrypto API, which Hermes doesn't reliably provide) and every report is canonicalized (RFC 8785 JCS, via the `canonicalize` package) and signed exactly as `contracts/README.md`'s signing rule requires. This was cross-validated against the real Python backend during development: a report signed here with these exact libraries was verified successfully by `backend/src/protidhoni_api/crypto.py`, and a tampered copy was correctly rejected.
- **Local queue** (`src/db/`) — SQLite via `@op-engineering/op-sqlite`, one `report_queue` table keyed by `message_id`. Enqueueing is idempotent (`INSERT OR IGNORE`), which is what makes mesh dedup and repeated sync attempts safe.
- **Configuration-driven report forms** (`src/forms/`, `src/screens/ReportFormScreen.tsx`) — one reusable UI creates SOS, medical need, resource need, shelter information, hazard update, safety status, and safe-route reports. Each type configures its own labels, guidance, and structured need options without duplicated screens. Language, affected-person count, description, selected needs, and GPS/manual/no-location input are validated before signing.
- **My reports** (`src/screens/MyReportsScreen.tsx`) — every locally-known report with a human-readable report type, creation timestamp, `sync_status` (local / relayed / synced), last delivery attempt, and durable accepted/duplicate/rejected/offline feedback.
- **Mesh relay** (`src/mesh/relay.ts`, `android/.../NearbyConnectionsModule.kt`) — advertises, discovers, and auto-requests connections to discovered endpoints; every *incoming* connection now waits for an explicit accept/decline (see "Phase 3 security hardening" below) before any payload is exchanged. Once connected, it exchanges queued reports as BYTES payloads, decrements `ttl_hops`, appends this device's identity to `relay_path`, and relies on `message_id`-keyed dedup to avoid re-relaying what it's already seen.
- **Sync when online** (`src/sync/sync.ts`) — `@react-native-community/netinfo` triggers a `POST /reports` of the whole unsynced queue whenever connectivity is (re)gained. Accepted/duplicate reports become synced; rejected reports stay queued for retry because the frozen backend response cannot distinguish permanent signature rejection from temporary rate limiting. HTTP, network, malformed-response, and omitted-result feedback is stored for the user instead of being silently discarded.
- **Data-preserving Phase 2 migration** (`src/db/queue.ts`) — the queue adds delivery metadata only when the columns are absent. Existing Phase 1 reports are retained.
- **Complete Bangla/English interface** (`src/i18n/`, `src/ui/`) — one persisted application-language setting drives every tab, report form, validation alert, Nearby status, connection prompt, delivery state, date, number, and placeholder. The language control is available globally and in the report form; changing either updates the whole application immediately without restarting or disconnecting Nearby. User-authored report text is never machine-translated or modified.
- **Bilingual typography** (`assets/fonts/`) — Bangla uses Anek Bangla and English uses Anek Latin, coordinated members of Ek Type's Anek multiscript family. The variable source fonts and Android's generated 700-weight instances are bundled under SIL OFL 1.1, so the UI does not depend on network font downloads or device-specific Bengali fallback fonts.

## Phase 3 security hardening

- **Private key wrapping via Android Keystore** (`android/.../security/KeystoreWrapModule.kt`, `src/native/KeystoreWrap.ts`, `src/crypto/identity.ts`) — the device's Ed25519 secret key is no longer stored in plaintext. It's wrapped with a Keystore-backed AES-256-GCM key (StrongBox-backed on devices that support it, falling back to TEE-backed otherwise) before being persisted; the raw key exists in JS memory only for the duration of an unwrap. A pre-Phase-3 plaintext (`v1`) identity is migrated to the wrapped (`v2`) format transparently on next load, reusing the exact same key bytes — regenerating would change `sender_pubkey_hash` and invalidate every prior relay/sync history.
- **Nearby Connections pairing confirmation** (`android/.../nearby/NearbyConnectionsModule.kt`, `src/native/NearbyConnections.ts`, the **Nearby** tab in `App.tsx`) — incoming connections no longer auto-accept. `onConnectionInitiated` emits a `connectionRequested` event instead of calling `acceptConnection` immediately; the Nearby tab shows each pending request with Accept/Decline buttons, calling the new `respondToConnection(endpointId, accept)` native method once the user responds. This was already known not to weaken message authenticity either way — every report is Ed25519-signed by its original sender and verified by the backend independent of who relayed it — so this change is about not burning battery/bandwidth on unwanted strangers, not about message trust.

## Offline map and local assistant

Two fully offline features, added after Phase 3, that never depend on `ai-service` or the backend being reachable:

- **Offline map with peer-visible marks** (`src/screens/MapScreen.tsx`, `src/contracts/mark.ts`, `src/crypto/mark.ts`, `src/db/marks.ts`) — a bundled, zoom-0-10 vector tile package for all of Bangladesh (`assets/maps/bangladesh.mbtiles`, generated with [planetiler](https://github.com/onthegomap/planetiler) from the Geofabrik Bangladesh OSM extract; **5.6MB**, far smaller than the ~150-250MB originally estimated, because capping detail at zoom 10 drops almost all building/POI-level features). Place labels prefer the `name:bn` OpenStreetMap tag over `name` (`["coalesce", ["get", "name:bn"], ["get", "name"]]` in the style), so Bangladesh place names render in Bangla wherever OSM has that tag. Long-press the map to drop a mark (hazard / safe route / shelter / resource / other); it is Ed25519-signed with the same on-device identity reports use (`crypto/mark.ts`), stored locally, and relayed mesh-to-mesh through the same `NearbyConnections` transport reports use (`mesh/relay.ts`). Marks have no backend, so **this relay is the only place a mark's signature is ever checked** — unlike reports (where the backend re-verifies independently and the relay deliberately skips it), an unsigned or tampered mark is dropped here and never stored or forwarded.
- **Offline local chat + report prioritization** (`src/llm/localAssistant.ts`, `src/screens/ChatScreen.tsx`) — Qwen2.5-1.5B-Instruct (Q4_K_M GGUF, ~1GB) running fully on-device via [`llama.rn`](https://github.com/mybigday/llama.rn)/llama.cpp. "Which report should I work on first?" is answered by a **deterministic** sort (`prioritizeReports`: `priority` field, then recency) — the model is only asked to *phrase* an answer about that already-computed list, never to invent its own ordering; a 1-2B on-device model is not reliable enough to trust with that judgment call directly.

**Honest caveats, not glossed over:**
- Every open-weight model in this size class (1-2B parameters) produces noticeably weaker Bangla output than English — this is a real limitation of the size class, not specific to Qwen2.5. `ChatScreen` shows this caveat to the user directly (`chat.caveat`).
- The map's `mbtiles://<path>` local-file vector source is documented, long-standing MapLibre/Mapbox Native functionality, but **has not been visually verified on a device or emulator in this session** (see "what's unverified" below) — check that the map actually renders before relying on it for a demo.
- Rendered tiles are © OpenMapTiles © OpenStreetMap contributors (ODbL); the style's `attribution` field and `Map`'s `attribution` prop must stay wired up.

**Bundling:** neither the GGUF checkpoint nor the mbtiles file is committed to git (both are large binaries — see `.gitignore`). Run `scripts/prepare-offline-assets.ps1` once to download/generate and copy both into `android/app/src/main/assets/`; `android/app/build.gradle`'s `noCompress` entries for `gguf`/`mbtiles` keep AAPT from compressing them so llama.cpp (mmap) and MapLibre (opens the file as SQLite) can read them directly. Both are copied out from the APK's assets to a real file in app storage on first use (`src/offline/assetStorage.ts`, via `@dr.pogodin/react-native-fs`'s `copyFileAssets`) — native asset-manager URIs are not `mmap`-able, and SQLite needs a real file path too.

**JDK note:** the script's map-tile step needs a JDK 21+ install (`-PlanetilerJavaHome`, only to run the standalone `planetiler.jar` tool) because planetiler v0.10.2 cannot run on JDK 17 (`UnsupportedClassVersionError`, confirmed directly). This is completely separate from — and has no effect on — the Android app build itself, which stays hard-pinned to JDK 17 by the `android/build.gradle` check described below; `llama.rn`'s and MapLibre's native builds were confirmed to link correctly under that same JDK 17 build.

## Remaining deliberate simplifications

- **The mesh does not re-verify signatures before relaying.** Per `contracts/README.md` and Protidhoni_Roadmap.md §5.5, a relay does not need to be trusted — the backend is the enforcement point. Re-checking here would only duplicate that check at Phase 1's expense.
- **Backend selection is local and configurable.** A debug build infers the computer running Metro; the Android-emulator fallback is `http://10.0.2.2:8000`. On a physical phone, open **Nearby → Backend connection**, enter the computer's LAN origin (for example `http://192.168.1.20:8000`), and save it. The app validates and persists the origin locally; no team member's LAN address is hard-coded.

## Run and verify on devices

The complete Windows guide for configuring JDK/Android SDK tools, installing on
two explicitly selected phones, testing offline relay, generating a private
upload key, and building/verifying APK and AAB artifacts is
[`../docs/android-two-device-and-release.md`](../docs/android-two-device-and-release.md).

Use JDK 17 for Android builds; it is the runtime validated with this project's native SQLite/CMake dependency. Android's build guidance explains that terminal Gradle uses `JAVA_HOME` and recommends keeping the IDE and terminal on the same JDK. Confirmed directly with a clean build (`rm -rf android/app/.cxx && ./gradlew assembleDebug`, no Gradle/CMake cache reuse): under JDK 25, `configureCMakeDebug` fails with `WARNING: A restricted method in java.lang.System has been called` — the Android Gradle Plugin's CMake integration has not been validated against JDK's newer restricted-method enforcement (JEP 472 and later). Under JDK 17, the identical clean build completes `assembleDebug` and produces a working `app-debug.apk`. Set `JAVA_HOME` before running Gradle or the React Native Android command.

`android/build.gradle` now checks the running JDK before anything else and fails immediately with an actionable message naming the exact JDK it found, instead of failing 20+ seconds in with the cryptic CMake error above. If you see that message, it means `JAVA_HOME` is unset or points at the wrong JDK for the *current terminal session* — setting it in one shell does not persist to a new one.

```powershell
$env:JAVA_HOME = "C:\path\to\jdk-17"
npm ci
npx react-native run-android
```

Install on two physical Android devices with current Google Play services, both with internet off (airplane mode with Wi-Fi/Bluetooth re-enabled, or just no SIM/data):

1. Put phone A in airplane mode, re-enable Bluetooth only, and use **Create** to save one report of each type: SOS, medical, resources, shelter, hazard, safety, and safe route. Exercise GPS, manual coordinates, and no-location across the set.
2. Open **My reports** and confirm all seven show their type, creation time, and `local` status after closing and reopening the app.
3. On both phones, open **Nearby** and tap **Start nearby discovery**. Whichever phone receives the incoming request should show it under "Connection requests" with the other phone's name — confirm **Decline** on one attempt makes the request disappear without any payload exchange, then let a later attempt connect via **Accept**. Once connected, phone A's queue should be sent to phone B; phone B should list the reports and phone A's copies should become `relayed`.
4. Give either phone internet access. Auto-sync should POST its queue to the reachable backend. Pull to refresh **My reports** and confirm accepted/duplicate items become `synced`; rejection or connection failures remain queued and display explicit feedback.
5. Reinstall the app (or clear its storage) to confirm a fresh identity is wrapped on first launch, not stored in plaintext — there is no way to inspect this from the UI, but a `logcat` check confirms no `KeystoreWrap`-related crash and that reports keep signing/verifying correctly across app restarts.

Do not use an emulator as evidence of Bluetooth/Wi-Fi peer discovery or relay — the whole point is proving it works with real radios and no infrastructure.

## Testing

```powershell
npm run typecheck
npm test
```

143 tests, all self-contained (no device/emulator/native build required). `npm run typecheck`, `npx eslint .`, and `npx jest` are all green as of this change, including the 6 new map-mark relay tests (sign, relay, receive, reject-tampered, dedupe, ttl) and 2 new backend-URL error-translation tests; the offline map/assistant screens themselves are not unit-tested beyond typecheck, since MapLibre/llama.rn are mocked out in `__tests__/App.test.tsx` and real rendering needs a device — see "Offline map and local assistant" above for what remains unverified.
- `src/crypto/__tests__/` — UTF-8 and base64/base64url encoders verified against Node's own implementations, JCS canonicalization behavior, device identity generation/persistence, full sign-then-verify round trips (including a tampering-must-fail check), and the v1-plaintext-to-v2-wrapped identity migration (with `KeystoreWrap` mocked — a real Android Keystore can't run under Jest; see `src/native/__mocks__/KeystoreWrap.ts`).
- `src/db/__tests__/queue.test.ts` — the actual queue SQL run against Node's built-in `node:sqlite`, not a hand-rolled fake, so real SQL bugs would actually surface.
- `src/forms/__tests__/reportFormModel.test.ts` — every report type is validated, genuinely Ed25519-signed, and inserted into real in-memory SQLite without network access; invalid text, counts, selections, and locations are rejected before signing.
- `src/mesh/__tests__/relay.test.ts` — relay/dedup/ttl/relay_path logic with `NearbyConnections` mocked.
- `src/sync/__tests__/sync.test.ts` — sync, batching, accepted/duplicate/rejected handling, retry retention, and failure feedback with `NetInfo` and `fetch` mocked.
- `src/screens/__tests__/`, `__tests__/App.test.tsx` — all configured form variants and populated/empty My Reports output are rendered and inspected with React's test renderer, including the Nearby tab's connection-request accept/decline flow.
- `src/i18n/__tests__/` — English/Bangla catalog parity, interpolation, and Bangla-script coverage; the app tests also verify language persistence and that toggling languages does not stop an active Nearby session.

## Why the native bridge exists

React Native owns the UI and typed report model. `android/.../NearbyConnectionsModule.kt` owns Nearby Connections because device discovery, permissions, connection lifecycle, and payload transfer are Android-native APIs with no JS equivalent. Its `P2P_CLUSTER` strategy gives the app direct M-to-N nearby links; `src/mesh/relay.ts` implements the store-and-forward queue logic above those direct links.
