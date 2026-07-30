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

## Phase 3 security hardening

- **Private key wrapping via Android Keystore** (`android/.../security/KeystoreWrapModule.kt`, `src/native/KeystoreWrap.ts`, `src/crypto/identity.ts`) — the device's Ed25519 secret key is no longer stored in plaintext. It's wrapped with a Keystore-backed AES-256-GCM key (StrongBox-backed on devices that support it, falling back to TEE-backed otherwise) before being persisted; the raw key exists in JS memory only for the duration of an unwrap. A pre-Phase-3 plaintext (`v1`) identity is migrated to the wrapped (`v2`) format transparently on next load, reusing the exact same key bytes — regenerating would change `sender_pubkey_hash` and invalidate every prior relay/sync history.
- **Nearby Connections pairing confirmation** (`android/.../nearby/NearbyConnectionsModule.kt`, `src/native/NearbyConnections.ts`, the **Nearby** tab in `App.tsx`) — incoming connections no longer auto-accept. `onConnectionInitiated` emits a `connectionRequested` event instead of calling `acceptConnection` immediately; the Nearby tab shows each pending request with Accept/Decline buttons, calling the new `respondToConnection(endpointId, accept)` native method once the user responds. This was already known not to weaken message authenticity either way — every report is Ed25519-signed by its original sender and verified by the backend independent of who relayed it — so this change is about not burning battery/bandwidth on unwanted strangers, not about message trust.

## Remaining deliberate simplifications

- **The mesh does not re-verify signatures before relaying.** Per `contracts/README.md` and Protidhoni_Roadmap.md §5.5, a relay does not need to be trusted — the backend is the enforcement point. Re-checking here would only duplicate that check at Phase 1's expense.
- **`API_BASE_URL` in `App.tsx` is a hardcoded constant**, not a settings screen. Update it before building for your demo network (see the comment at its definition — emulator vs. real device on the same Wi-Fi need different values).

## Run and verify on devices

Use JDK 17 for Android builds; it is the runtime validated with this project's native SQLite/CMake dependency. Android's build guidance explains that terminal Gradle uses `JAVA_HOME` and recommends keeping the IDE and terminal on the same JDK. On this project, JDK 25 fails during native dependency configuration, while JDK 17 completes `assembleDebug`. Set `JAVA_HOME` before running Gradle or the React Native Android command.

```powershell
$env:JAVA_HOME = "C:\path\to\jdk-17"
npm install
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

116 tests, all self-contained (no device/emulator/native build required):
- `src/crypto/__tests__/` — UTF-8 and base64/base64url encoders verified against Node's own implementations, JCS canonicalization behavior, device identity generation/persistence, full sign-then-verify round trips (including a tampering-must-fail check), and the v1-plaintext-to-v2-wrapped identity migration (with `KeystoreWrap` mocked — a real Android Keystore can't run under Jest; see `src/native/__mocks__/KeystoreWrap.ts`).
- `src/db/__tests__/queue.test.ts` — the actual queue SQL run against Node's built-in `node:sqlite`, not a hand-rolled fake, so real SQL bugs would actually surface.
- `src/forms/__tests__/reportFormModel.test.ts` — every report type is validated, genuinely Ed25519-signed, and inserted into real in-memory SQLite without network access; invalid text, counts, selections, and locations are rejected before signing.
- `src/mesh/__tests__/relay.test.ts` — relay/dedup/ttl/relay_path logic with `NearbyConnections` mocked.
- `src/sync/__tests__/sync.test.ts` — sync, batching, accepted/duplicate/rejected handling, retry retention, and failure feedback with `NetInfo` and `fetch` mocked.
- `src/screens/__tests__/`, `__tests__/App.test.tsx` — all configured form variants and populated/empty My Reports output are rendered and inspected with React's test renderer, including the Nearby tab's connection-request accept/decline flow.

## Why the native bridge exists

React Native owns the UI and typed report model. `android/.../NearbyConnectionsModule.kt` owns Nearby Connections because device discovery, permissions, connection lifecycle, and payload transfer are Android-native APIs with no JS equivalent. Its `P2P_CLUSTER` strategy gives the app direct M-to-N nearby links; `src/mesh/relay.ts` implements the store-and-forward queue logic above those direct links.
