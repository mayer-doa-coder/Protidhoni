# Mobile client — Person B

Phase 1 implements the core offline path end to end: create a signed SOS report with no internet, queue it locally, relay it over the mesh to another phone, and sync it to the backend once any device in the chain regains connectivity.

## What's implemented

- **Identity & signing** (`src/crypto/`) — a real Ed25519 keypair is generated on first launch (`@noble/ed25519` + `@noble/hashes`, not the Node/browser WebCrypto API, which Hermes doesn't reliably provide) and every report is canonicalized (RFC 8785 JCS, via the `canonicalize` package) and signed exactly as `contracts/README.md`'s signing rule requires. This was cross-validated against the real Python backend during development: a report signed here with these exact libraries was verified successfully by `backend/src/protidhoni_api/crypto.py`, and a tampered copy was correctly rejected.
- **Local queue** (`src/db/`) — SQLite via `@op-engineering/op-sqlite`, one `report_queue` table keyed by `message_id`. Enqueueing is idempotent (`INSERT OR IGNORE`), which is what makes mesh dedup and repeated sync attempts safe.
- **SOS form** (`src/screens/SosFormScreen.tsx`) — the first structured report type (Protidhoni_Roadmap.md §7 Phase 1: "start with just SOS"). Location can be GPS (`@react-native-community/geolocation`), typed in manually, or omitted.
- **My reports** (`src/screens/MyReportsScreen.tsx`) — every locally-known report with its `sync_status` (local / relayed / synced), per Protidhoni_Roadmap.md §5.3.
- **Mesh relay** (`src/mesh/relay.ts`, `android/.../NearbyConnectionsModule.kt`) — Phase 0 only advertised and discovered; Phase 1 actually connects (auto-accept/auto-request, no pairing confirmation yet — see below), exchanges queued reports as BYTES payloads, decrements `ttl_hops`, appends this device's identity to `relay_path`, and relies on `message_id`-keyed dedup to avoid re-relaying what it's already seen.
- **Sync when online** (`src/sync/sync.ts`) — `@react-native-community/netinfo` triggers a `POST /reports` of the whole unsynced queue whenever connectivity is (re)gained; the response's per-report outcome (`accepted`/`duplicate`/`rejected`) updates local `sync_status` accordingly.

## Deliberate Phase 1 simplifications (not bugs, not forgotten)

- **No connection-pairing confirmation.** The native module auto-accepts every incoming connection and auto-requests a connection to every discovered endpoint. Comparing Nearby Connections' authentication digits between devices before accepting is Phase 3 security-hardening work. This does not weaken message authenticity — every report is still Ed25519-signed by its original sender and verified by the backend independent of who relayed it; a blindly-accepted connection can only carry already-signed data, not forge it.
- **The mesh does not re-verify signatures before relaying.** Per `contracts/README.md` and Protidhoni_Roadmap.md §5.5, a relay does not need to be trusted — the backend is the enforcement point. Re-checking here would only duplicate that check at Phase 1's expense.
- **The private key is stored in AsyncStorage** (app-sandboxed, unencrypted), not Android Keystore. Moving it behind Keystore/EncryptedSharedPreferences is Phase 3 scope.
- **`API_BASE_URL` in `App.tsx` is a hardcoded constant**, not a settings screen. Update it before building for your demo network (see the comment at its definition — emulator vs. real device on the same Wi-Fi need different values).

## Run and verify on devices

```powershell
npm install
npx react-native run-android
```

Install on two physical Android devices with current Google Play services, both with internet off (airplane mode with Wi-Fi/Bluetooth re-enabled, or just no SIM/data):

1. On phone A, open the **SOS** tab, fill in a report, and save it. Check the **My reports** tab — it should show `local`.
2. On both phones, open the **Nearby** tab and tap **Start nearby discovery**. Once they discover and auto-connect each other, phone A's queued report should be sent to phone B; phone B's **My reports** should now show that report too, and phone A's copy should flip to `relayed`.
3. Give phone B (or either phone) real internet access. Auto-sync should POST the queue to your running backend; **My reports** should show `synced` once that succeeds. Requires a real backend reachable at the `API_BASE_URL` configured in `App.tsx` — set that before this step.

Do not use an emulator as evidence of Bluetooth/Wi-Fi peer discovery or relay — the whole point is proving it works with real radios and no infrastructure.

## Testing

```powershell
npm run typecheck
npm test
```

85 tests, all self-contained (no device/emulator/native build required):
- `src/crypto/__tests__/` — UTF-8 and base64/base64url encoders verified against Node's own implementations, JCS canonicalization behavior, device identity generation/persistence, and full sign-then-verify round trips (including a tampering-must-fail check).
- `src/db/__tests__/queue.test.ts` — the actual queue SQL run against Node's built-in `node:sqlite`, not a hand-rolled fake, so real SQL bugs would actually surface.
- `src/mesh/__tests__/relay.test.ts` — relay/dedup/ttl/relay_path logic with `NearbyConnections` mocked.
- `src/sync/__tests__/sync.test.ts` — sync/batching/outcome-handling logic with `NetInfo` and `fetch` mocked.
- `src/screens/__tests__/`, `__tests__/App.test.tsx` — smoke renders (this project doesn't use `@testing-library/react-native`; its current major version pins a peer dependency, `test-renderer@^1`, that isn't compatible with this project's React 19 + `react-test-renderer` setup, so deeper interaction testing was deliberately left out rather than adding a dependency with an unresolved version conflict — the logic those interactions call into is already covered directly in the crypto/db/mesh/sync tests above).

## Why the native bridge exists

React Native owns the UI and typed report model. `android/.../NearbyConnectionsModule.kt` owns Nearby Connections because device discovery, permissions, connection lifecycle, and payload transfer are Android-native APIs with no JS equivalent. Its `P2P_CLUSTER` strategy gives the app direct M-to-N nearby links; `src/mesh/relay.ts` implements the store-and-forward queue logic above those direct links.
