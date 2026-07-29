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
