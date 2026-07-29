# Dashboard — Person C

The dashboard polls the real backend `GET /reports` endpoint every 15 seconds and renders conservative incident clusters as Leaflet pins. A cluster joins reports only when their declared type, location (within 750 m), and text/need tokens agree. Each cluster shows report count, independent sender count, and the backend’s reported corroboration count; unrelated emergencies are deliberately left separate rather than being over-grouped.

Filters cover report type, verification state, and priority. Pins remain colour-coded by priority (including a distinct unscored state), and each popup keeps the original Bangla or English text, people count, needs, verification state, and creation time visible. Summary cards keep reports without coordinates visible in the overall counts instead of silently dropping them.

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
