# Protidhoni Meshtastic application framing, version 1

Status: **frozen Phase 5A internal interface**

This specification carries one complete Protidhoni report through Meshtastic
application data packets. It does not replace the frozen report schema and does
not create a public API. A gateway reconstructs the original report and submits
it through the existing `POST /reports` endpoint, where normal schema, identity,
signature, idempotency, and rate-limit checks still apply.

## 1. Pinned compatibility profile

- Meshtastic firmware: `v2.7.26.54e0d8d`, commit
  `54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`.
- Meshtasticator: commit
  `17ceb8231079d87b070abc6132181e4c6b20202d`.
- Meshtastic Python client: `2.7.11`.
- Meshtastic application port: `PRIVATE_APP` (`256`). The official protobuf
  definition reserves values `256`–`511` for private applications.
- The pinned firmware's generated `meshtastic_Constants_DATA_PAYLOAD_LEN` is
  233 bytes. The pinned daemon accepts at most 231 `PRIVATE_APP` bytes for port
  256, while the pinned Meshtasticator relay path accepts 225 but not 231. The
  version-1 ceiling is therefore **224 application bytes**, leaving one byte
  below the stricter observed simulation boundary.

The evidence run must print and record its actual firmware, simulator, and Python
client versions. A different version is not automatically incompatible, but it
must pass the complete golden-vector and simulator suite before its results are
accepted.

## 2. Report serialization

1. The input must be a JSON object containing one complete report.
2. `message_id` must be the canonical lowercase, hyphenated text form of a UUID.
   The framing accepts any UUID version already accepted by the frozen contract;
   it does not incorrectly reject the gateway's deterministic UUIDs.
3. Serialize the **complete report object** with RFC 8785 JSON Canonicalization
   Scheme (JCS), then UTF-8 encode it. This byte sequence is the canonical
   payload. No whitespace, alternate key order, or alternate numeric rendering
   is permitted on the wire.
4. The canonical payload must be between 1 and 16,384 bytes. This transport cap
   bounds memory and airtime; it is an additional LoRa-path constraint, not a
   change to the public report schema.
5. Compute SHA-256 over the complete canonical payload. The full 32-byte digest
   is repeated in each fragment.

Version 1 does not compress payloads. This removes decompression-bomb and
cross-language ambiguity from the first hardware-readiness test.

The existing Ed25519 signature still covers only the immutable signed subset
defined in `contracts/README.md`. Canonicalizing the complete envelope for
fragmentation neither re-signs it nor expands that trust claim.

## 3. Frame layout

All integers use network byte order (big-endian). Offsets are zero-based.

| Offset | Size | Field | Version-1 rule |
|---:|---:|---|---|
| 0 | 2 | magic | ASCII `PD` (`0x50 0x44`) |
| 2 | 1 | version | `0x01` |
| 3 | 1 | flags | `0x00`; every other value is rejected |
| 4 | 16 | message UUID | UUID bytes in RFC 4122/network order |
| 20 | 32 | payload digest | SHA-256 of the complete canonical payload |
| 52 | 2 | total payload length | unsigned 16-bit integer, `1..16384` |
| 54 | 1 | fragment index | unsigned, zero-based |
| 55 | 1 | fragment count | unsigned, `1..98` |
| 56 | 0..168 | chunk | the fragment's consecutive payload bytes |

The header is exactly 56 bytes and the chunk budget is exactly `224 - 56 = 168`
bytes. `fragment_count` must equal `ceil(total_payload_length / 168)`. Every
non-final chunk must contain 168 bytes; the final chunk must contain precisely
the remaining `1..168` bytes. Empty, padded, short intermediate, oversized, and
extra trailing data are rejected.

## 4. Reassembly and duplicate rules

- Key active work by `message_id`. All fragments for that ID must agree on
  digest, total length, and count.
- Accept fragments in any order.
- An exact repeat of an already stored fragment is a harmless duplicate and
  does not extend the assembly lifetime.
- Reusing an index with different bytes, or reusing a message ID with different
  metadata/digest, is a conflict and is rejected without replacing valid state.
- Hold at most 32 active assemblies. At the maximum report size this caps chunk
  storage at 512 KiB, excluding small interpreter/object overhead.
- Expire an incomplete assembly after 600 seconds without a new fragment. A
  duplicate fragment is not progress.
- After all chunks arrive, concatenate by index, verify exact length and SHA-256,
  require strict UTF-8, parse one JSON object, require its bytes to already be
  RFC 8785 canonical, and require its `message_id` to match the frame UUID.
- Remember at most 256 completed `(message_id, digest)` entries for 3,600 seconds.
  A replay with the same digest is ignored; the same ID with another digest is a
  conflict. Backend idempotency remains the final replay control after this
  bounded local window expires.

## 5. Meshtastic envelope rules

- Send the binary frame with the Python API's `sendData`, port `PRIVATE_APP`
  (`256`). Do not send it as `TEXT_MESSAGE_APP` and do not UTF-8-decode a frame.
- Meshtastic's outer hop limit is transport metadata. It is configured by the
  simulation/sender and is not copied into, or allowed to mutate, the report's
  `ttl_hops` field.
- Use a non-default, randomly generated Meshtastic channel key for evidence
  runs. Keep it in ignored local configuration/environment only. Never commit it
  or print it in evidence logs.
- A channel key protects the Meshtastic channel; it does not replace the report's
  Ed25519 author signature. Conversely, the repeated SHA-256 digest detects
  corruption and mix-ups but is not authentication because an attacker can
  calculate another digest.
- Relays forward Meshtastic packets. They never receive a Protidhoni private key,
  re-sign a report, or claim authorship.

## 6. Failure behavior

Malformed or unsupported frames fail closed and must not be submitted to the
backend. Implementations must use explicit limits rather than unbounded maps or
buffers. They must not log report text, coordinates, public/private keys,
channel keys, raw canonical payloads, or frame bodies. Safe diagnostics are the
protocol version, message ID, fragment index/count, byte counts, result category,
and non-sensitive timing.

Receiving one bad frame must not crash the listener or discard unrelated active
assemblies. The caller handles a typed protocol error and continues processing
other packets; broad exception swallowing is not compliant.

## 7. Golden vectors and change control

`vectors/golden-v1.json` is normative. It contains valid signed reports,
canonical bytes, digests, and exact frame bytes. Implementations must both encode
to and decode from those bytes. `scripts/generate_vectors.py --check` proves the
file was not manually edited.

Any change to serialization, layout, byte order, constants, duplicate semantics,
limits, or security rules requires all three team members to agree, a new frame
version, and new vectors. Version 1 remains decodable after a later version is
introduced.

