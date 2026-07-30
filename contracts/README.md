# Frozen contract: Phase 0

These files are the only boundary shared by the mobile client, backend, AI service, dashboard, and future SMS gateway. They are frozen after Phase 0. A change requires synchronous agreement from Persons A, B, and C, a schema-version decision, and a new contract-validation run.

## Report signing rule

An Ed25519 signature covers the RFC 8785 JSON Canonicalization Scheme (JCS) representation of an object containing exactly these members:

```json
{
  "schema_version": "1.0.0",
  "message_id": "…",
  "type": "…",
  "sender_pubkey": "…",
  "sender_pubkey_hash": "…",
  "created_at": "…",
  "language": "…",
  "location": { "…": "…" },
  "payload": { "…": "…" }
}
```

`ttl_hops`, `relay_path`, `sync_status`, `priority`, and `verification` are deliberately excluded because relays and the backend update them. They must never be represented to responders as sender-authenticated claims. The backend must additionally verify that `sender_pubkey_hash` equals the SHA-256 hash of `sender_pubkey` before accepting a signature.

## API conventions

- `POST /reports` is batch-oriented and idempotent by `message_id`.
- The client may submit local `sync_status`, but the server ignores it; only server response delivery results are authoritative.
- `GET /reports` accepts an ISO-8601 `since` timestamp and a WGS84 bounding box formatted `minLng,minLat,maxLng,maxLat`.
- The internal AI endpoint is not public. It is protected by a separately configured service token in later phases.
- `PATCH /reports/{message_id}`, `POST /instructions`, and `POST /translations` deny access unless the caller supplies the configured `X-Responder-Token`. The backend reads that secret only from `PROTIDHONI_RESPONDER_TOKEN`; an unset credential keeps every responder route disabled.

## Phase 1 addendum (added when report ingestion was implemented)

These are additive clarifications to the frozen Phase 0 contract, not schema-breaking changes — every Phase 0-conformant message is still accepted unchanged.

- **`IngestResult.outcome` gains a third value: `rejected`.** A batch is only rejected outright with `400` when it is not valid JSON against `message-schema.json` (a client bug). A structurally valid report whose `sender_pubkey_hash` does not equal `SHA-256(sender_pubkey)`, whose Ed25519 signature does not verify, or whose sender has exceeded its per-minute rate limit is accepted at the HTTP level (`202`) but marked `rejected` for that individual item. Rationale: one bad or over-quota report in a 100-report batch (exactly the bursty, multi-source, multi-relay-path situation this endpoint exists for) must not block the other 99 genuine reports.
- **`GET /reports`'s `since` filter compares against the server's ingestion time (`received_at`), not the client's `created_at`.** Mesh-relayed reports can arrive long after their `created_at` and client clocks are not trusted for ordering; `received_at` is what makes `since`/`next_since`-based polling actually converge.
- **Per-sender rate limiting** is enforced by `sender_pubkey_hash` (the signer), independent of which device's HTTP call carries the report — a relay forwarding someone else's messages is never penalized for their volume, only the original signer's own identity accrues against its own quota.

## Phase 2 addendum (responder operations)

- **Responder authorization is deny-by-default.** `PATCH /reports/{message_id}` and `POST /instructions` require `X-Responder-Token` to match the secret configured in `PROTIDHONI_RESPONDER_TOKEN`. Missing, shorter-than-32-character, or whitespace-padded server configuration returns `503`; missing or incorrect caller credentials return `401`. The token is never committed to the repository.
- **Verification transitions are forward-only and idempotent.** `unverified` may become `corroborated`, `verified`, or `disputed`; `corroborated` may become `verified` or `disputed`; repeating a state is allowed. `verified` and `disputed` are terminal, and an invalid transition returns `409`.
- **Instructions remain signed contract messages.** Only `INSTRUCTION` and `SAFE_ROUTE` reports with a valid Ed25519 signature can enter the outbound queue. Retrying identical signed content is idempotent; reusing a `message_id` for different content returns `409`.
- **Translation is a versioned additive extension (`1.2.0-phase2`).** `POST /translations` is responder-only and accepts exactly a stored `message_id` and `target_language`; it never accepts client-supplied crisis text. The backend retrieves the report, then sends its text only to the isolated `POST /ai/translate` AI-service endpoint using `X-Internal-Service-Token`. The returned rendering is not written into or represented as part of the signed report, and provider credentials never reach a browser. The dashboard keeps the original labelled text visible.
- **Translation failures fail closed.** An unavailable internal service/provider returns `503`; a malformed or language-mismatched internal response returns `502`. The backend does not forward internal/provider error detail to responders.

## Phase 4 addendum (SMS/USSD gateway)

`contracts/message-schema.json` is **unchanged** by this phase. No new field, no version bump, no re-signing of any existing client. These are additive clarifications about a new *producer* of the existing shape.

- **Gateway-attested reports are signed by the gateway, not the sender.** The schema requires `sender_pubkey`, `sender_pubkey_hash`, and a valid Ed25519 `signature` on every report, and a feature phone can sign none of them. `POST /gateway/sms` and `POST /gateway/ussd` therefore assemble the report server-side and sign it with the gateway's *own* keypair. Every report from this path consequently shares one `sender_pubkey_hash` — the gateway's.
- **This is a different trust claim from a mesh report, and must not be presented as the same one.** A mesh report's signature attests *this device authored this content*. A gateway report's signature attests only *this gateway received this SMS/USSD session and transcribed it*. It says nothing about who actually sent the message, because the underlying channel offers no cryptographic sender identity at all. Responder tooling must not describe gateway reports as device-verified.
- **The shared gateway hash is the channel's provenance marker.** It is published as `gateway_pubkey_hash` on `GET /health` (null when the gateway is unconfigured) so the dashboard can label and filter feature-phone traffic at runtime, without a build-time environment variable and without adding a field to the frozen schema. Exposing it publicly is safe: it is a public-key hash that already appears in every gateway report returned by the public `GET /reports`.
- **Adapters authenticate independently and fail closed.** Twilio SMS requires `X-Twilio-Signature`, keyed by `PROTIDHONI_GATEWAY_WEBHOOK_TOKEN`. The offline USSD simulator uses `X-Protidhoni-Gateway-Signature` with a separate `PROTIDHONI_GATEWAY_USSD_WEBHOOK_TOKEN`; it is not represented as Twilio or as a live telco. An unconfigured secret returns `503`, while a missing or incorrect signature returns `401`. A real USSD aggregator requires an adapter for that provider's documented authentication and fields.
- **Gateway and device reports share one ingestion policy.** Both public `POST /reports` and the gateway call the same internal ingestion service, which verifies the report signature, applies the appropriate identity limiter, and then persists. Gateway traffic is limited by a peppered caller pseudonym because every gateway report shares the gateway signing identity.
- **Ingestion is idempotent by namespaced provider identifier.** `message_id` is a UUID v5 derived from a fixed namespace plus provider, channel, and provider message/session id. A sequential retry is recognized before rate limiting and returns `duplicate` without consuming another caller-quota event.
- **Provider phone metadata is never persisted.** The callback's caller number is normalized, HMAC'd with `PROTIDHONI_GATEWAY_PHONE_PEPPER` for in-memory rate limiting, and discarded. It is never signed or copied into a report. User-entered `payload.text` is retained as submitted and may contain a number if the user deliberately typed one.
- **Wire responses match each adapter.** Twilio SMS receives an empty TwiML response. The simulated USSD adapter receives `text/plain` beginning with `CON ` or `END `.
- **Gateway ingestion does not synchronously call AI.** Reports begin with `priority: null`; an unavailable AI service cannot prevent their persistence. No automatic post-ingestion scoring pipeline is claimed by Phase 4.
- **Location honesty.** An SMS sender may type coordinates, which are recorded as `source: "manual"` — a human assertion, never a device measurement, so `"gps"` is never claimed. A USSD menu cannot practically capture coordinates on a feature phone, so those reports carry `source: "none"` rather than a fabricated position.
- **`created_at` is server time** for this path. A feature phone has no trusted clock, and the gateway is the party actually attesting to when the message arrived.
