# Dashboard — Person C

Phase 1 polls the real backend `GET /reports` endpoint every 15 seconds and renders every geolocated report as a Leaflet map pin. Pins are colour-coded by priority (including a distinct unscored state) and open a responder popup with the report text, people count, needs, verification state, and creation time. Summary cards keep reports without coordinates visible in the overall counts instead of silently dropping them.

The browser uses a same-origin `/api` path. Vite proxies it to `http://localhost:8000` during development, and the dashboard's Nginx container proxies it to the Compose `backend` service in production. This avoids depending on cross-origin browser access that the current backend does not enable.

```powershell
npm install
npm run dev
```

Set `VITE_API_BASE_URL` only when intentionally bypassing the included proxy.

```powershell
npm run typecheck
npm test
npm run build
```
