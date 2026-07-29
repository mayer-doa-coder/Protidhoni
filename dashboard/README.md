# Dashboard — Person C

Phase 0 establishes a map shell and verifies that the browser can reach the backend health endpoint. It intentionally does not fabricate report pins before `GET /reports` exists in Phase 1.

```powershell
npm install
npm run dev
```

Set `VITE_API_BASE_URL` when the API is not on `http://localhost:8000`.
