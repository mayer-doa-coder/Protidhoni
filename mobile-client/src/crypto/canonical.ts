import canonicalize from "canonicalize";

import { utf8Encode } from "./utf8";

/**
 * RFC 8785 (JCS) canonical bytes of a JSON-serializable value. This MUST
 * produce byte-identical output to the backend's Python `rfc8785.dumps()`
 * for the same logical value — that cross-language compatibility was
 * verified directly against the real backend/src/protidhoni_api/crypto.py
 * during development (see project memory / PR notes), not just assumed.
 */
export function canonicalizeToBytes(value: unknown): Uint8Array {
  const json = canonicalize(value);
  if (json === undefined) {
    throw new Error("Value cannot be canonicalized to JSON (top-level undefined).");
  }
  return utf8Encode(json);
}
