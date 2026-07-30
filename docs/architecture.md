# Architecture and trust boundaries

Protidhoni accepts crisis reports through three transports while keeping one
versioned report contract and one backend ingestion path.

```text
React Native app -- Nearby store-and-forward -- online app ----+
                                                               |
SMS / simulated USSD -- authenticated gateway adapter --------+--> POST /reports
                                                               |         |
signed fixture -- LoRa frames -- bounded gateway reassembly ---+         v
                                                                 PostgreSQL/PostGIS
                                                                         |
                                              +--------------------------+----+
                                              |                               |
                                      isolated AI service              dashboard
```

## Components

- `contracts/` is the public source of truth. `message-schema.json` defines the
  report envelope and `openapi.yaml` defines the HTTP boundary.
- `mobile-client/` creates and signs reports, persists them in SQLite, relays
  them through Nearby Connections, and uploads the queue when connectivity
  returns. A relay cannot alter sender-authenticated fields without invalidating
  the Ed25519 signature.
- `backend/` authenticates privileged operations, verifies signatures,
  deduplicates by message ID, rate-limits by verified identity, encrypts
  sensitive report fields, persists reports, and exposes responder operations.
- `ai-service/` is reachable by the backend through a separate internal token.
  Provider translation credentials exist only in this service.
- `dashboard/` reaches the backend through `/api`; it never receives database,
  encryption, gateway, responder, or AI-provider secrets at build time.
- `hardware/` is a software simulation boundary. Its gateway reconstructs the
  original signed JSON and calls the existing `POST /reports`; it does not have
  a simulator-only backend endpoint.

## Trust boundaries

1. Device identity is an Ed25519 public-key hash, never a phone number, MAC
   address, Nearby endpoint ID, or network address.
2. `X-Responder-Token` protects verification updates, instructions, and report
   translation. Missing or insecure server configuration fails closed.
3. `X-Internal-Service-Token` is shared only by backend and AI service. The
   translation provider URL/key belongs only to the AI service.
4. SMS and simulated USSD use independent webhook credentials. The gateway
   signs the resulting report with its disclosed gateway identity; it does not
   pretend that the feature phone signed the message.
5. Exact coordinates and text for sensitive report types are encrypted before
   database persistence. Caller numbers, private keys, tokens, and transport
   identifiers are not persisted.

## Ownership of signed and mutable fields

The signature covers the sender-owned subset documented in
`contracts/README.md`. Delivery state, relay path, TTL, AI priority, and
responder verification are mutable system metadata and must not be presented as
sender-authenticated. Canonical JSON follows RFC 8785 so the React Native and
Python implementations verify the same bytes.

## Failure behavior

- Offline reports remain queued; an HTTP failure does not mark them delivered.
- Duplicate uploads are idempotent.
- Invalid signatures, malformed frames, conflicting fragments, expired
  reassemblies, and capacity violations are rejected.
- An unavailable translation provider returns a bounded unavailable response;
  the backend does not leak provider details or silently invent a translation.
- Missing privileged credentials disable the privileged operation instead of
  allowing anonymous access.

Physical two-device Nearby acceptance, a hosted deployment, live telco traffic,
and real LoRa/RF behavior are deployment or hardware acceptance tasks, not facts
established by the automated repository tests.
