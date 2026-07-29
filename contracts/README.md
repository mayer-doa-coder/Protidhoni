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

## Phase 1 addendum (added when report ingestion was implemented)

These are additive clarifications to the frozen Phase 0 contract, not schema-breaking changes — every Phase 0-conformant message is still accepted unchanged.

- **`IngestResult.outcome` gains a third value: `rejected`.** A batch is only rejected outright with `400` when it is not valid JSON against `message-schema.json` (a client bug). A structurally valid report whose `sender_pubkey_hash` does not equal `SHA-256(sender_pubkey)`, whose Ed25519 signature does not verify, or whose sender has exceeded its per-minute rate limit is accepted at the HTTP level (`202`) but marked `rejected` for that individual item. Rationale: one bad or over-quota report in a 100-report batch (exactly the bursty, multi-source, multi-relay-path situation this endpoint exists for) must not block the other 99 genuine reports.
- **`GET /reports`'s `since` filter compares against the server's ingestion time (`received_at`), not the client's `created_at`.** Mesh-relayed reports can arrive long after their `created_at` and client clocks are not trusted for ordering; `received_at` is what makes `since`/`next_since`-based polling actually converge.
- **Per-sender rate limiting** is enforced by `sender_pubkey_hash` (the signer), independent of which device's HTTP call carries the report — a relay forwarding someone else's messages is never penalized for their volume, only the original signer's own identity accrues against its own quota.
