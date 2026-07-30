# Three-minute demo script

This is a recording runbook, not evidence that the manual run has happened.
Complete every preflight item twice before recording and replace bracketed
placeholders with real links or names.

## Preflight

- Start the configured Compose stack and confirm Postgres, backend, AI service,
  and dashboard are healthy.
- Put both Android devices in airplane mode, then enable only the radios needed
  by Nearby Connections. Confirm both devices show the expected pairing digits.
- Set the app's backend URL in the Nearby tab. On a real phone, use the demo
  computer's LAN address, such as `http://192.168.1.20:8000`.
- Clear or identify demo data so the report shown on the dashboard is
  unambiguous.
- Exercise the phone-mesh path, local SMS/USSD adapter path, backend/AI path,
  and dashboard verification path twice. If Phase 5 is shown, run its signed
  multi-hop scenario twice as a separate simulation.
- Record the date, participants, device models/Android versions, backend URL,
  and pass/fail result in `docs/phase-6-acceptance.md`.

## Recording timeline

**0:00–0:20 — Problem.** During a crisis, internet access is often the first
thing people lose. Protidhoni lets smartphones relay a structured, signed report
offline and lets feature phones enter the same responder workflow through an
authenticated gateway.

**0:20–1:10 — Offline phone path.** Show phone A creating a report while
offline. Show it queued locally. Pair phone A and phone B using the matching
Nearby confirmation digits, relay the report, then give only phone B backend
connectivity. Show the queued report become delivered.

**1:10–1:35 — Feature-phone path.** Submit one prepared SMS or explicitly
labelled offline-USSD-simulator request. State which adapter is being shown.
Show that it appears in the same report collection with gateway-attested
provenance; do not call the USSD simulator a live telco integration.

**1:35–2:15 — Responder workflow.** On the dashboard, filter by report type or
priority, inspect the report, optionally translate it through the configured
provider, then update verification using the responder credential. Do not show
any token, private key, caller number, or provider key on screen.

**2:15–2:40 — Resilience and security.** Briefly show local queue status,
signature verification, duplicate-safe ingestion, and the architecture diagram
in `docs/architecture.md`.

**2:40–2:55 — Optional Phase 5.** Show the recorded simulated required-relay
scenario and Site Planner prediction. Say “software/protocol simulation and
hardware-readiness evidence,” never “hardware proven.”

**2:55–3:00 — Close.** Show `[PUBLIC_REPOSITORY_URL]` and
`[DASHBOARD_OR_APK_URL]`.

## Recording safety

Use synthetic reports and locations. Blur notification trays, terminal history,
environment files, QR codes, LAN details not needed for the demo, and any
account information. Rotate any credential accidentally captured before
publishing.
