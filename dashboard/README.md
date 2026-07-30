# Dashboard — Person C

The dashboard polls the real backend `GET /reports` endpoint every 15 seconds and renders conservative incident clusters as Leaflet pins. A cluster joins reports only when their declared type, location (within 750 m), and text/need tokens agree. Each cluster shows report count, independent sender count, and the backend’s reported corroboration count; unrelated emergencies are deliberately left separate rather than being over-grouped.

Filters cover report type, verification state, priority, and arrival channel. Pins remain colour-coded by priority (including a distinct unscored state), and each popup keeps the original Bangla or English text, people count, needs, verification state, and creation time visible. Summary cards keep reports without coordinates visible in the overall counts instead of silently dropping them.

## Channel provenance (Phase 4)

Every report carries a signer-provenance badge: **Gateway-attested**, **Device-signed**, or **Signer unknown**. The dashboard also provides a gateway-attested summary tile and a Channel filter when the backend publishes its current gateway identity.

Detection needs no schema field. A feature phone cannot sign anything, so the Phase 4 gateway signs on its behalf and every report from that path shares one `sender_pubkey_hash` — the gateway's. The backend publishes that hash as `gateway_pubkey_hash` on `GET /health`, which the dashboard already polls, so the dashboard learns it at runtime with no build-time `VITE_` variable and no rebuild when the gateway is reconfigured.

**The badge deliberately says "Gateway-attested", never "via SMS" or "via USSD" and never anything implying a verified sender.** The report schema contains the gateway signer hash but does not encode which upstream adapter received the message. The gateway signature says nothing about who actually sent it, because SMS and USSD carry no cryptographic sender identity. See the Phase 4 addendum in `../contracts/README.md`.

When the backend reports no gateway identity (`null`, or an older backend that omits the field entirely), reports are marked **Signer unknown** and the Channel filter is disabled. The dashboard does not invent device provenance from missing configuration.

This requires the Phase 4 backend from `feature/backend`. Until those branches are merged, the field is absent, which the dashboard handles as unavailable attribution rather than as an error.

## Responder verification workflow

The dashboard implements the Phase 2 `PATCH /reports/{message_id}` workflow. Enter `X-Responder-Token` in the password field for the current browser session, choose one of the allowed state transitions, and optionally add a responder note. The token is never hard-coded, placed in a `VITE_` variable, persisted in browser storage, or sent with read-only requests; it is sent only in the PATCH header. Terminal `verified` and `disputed` reports cannot be changed by the UI.

This requires the Phase 2 backend/OpenAPI contract from `feature/backend`, which documents `X-Responder-Token`. Merge the three Phase 2 branches through the agreed integration process before trying the workflow against the local Compose stack.

The browser uses a same-origin `/api` path. Vite proxies it to `http://localhost:8000` during development, and the dashboard's Nginx container proxies it to the Compose `backend` service in production. This avoids depending on cross-origin browser access that the current backend does not enable.

```powershell
npm install
npm run dev
```

Set `VITE_API_BASE_URL` only when intentionally bypassing the included proxy.

Translation preserves the labelled original text and, after the approved `POST /translations` shared-contract extension is merged, lets an authorized responder request a Bangla or English rendering for one report. The dashboard sends only a report ID and desired language to the backend; the backend retrieves the stored report and invokes the internal AI adapter. As with verification, the session-only responder token is required and no text is sent directly to a third-party service by the browser.

```powershell
npm run typecheck
npm test
npm run build
```
