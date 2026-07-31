import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";

import type { MapMark, MarkCategory } from "../contracts/mark";
import { base64UrlDecode, base64UrlEncode } from "./base64url";
import { canonicalizeToBytes } from "./canonical";
import { getOrCreateDeviceIdentity } from "./identity";
import { randomUuidV4 } from "./uuid";

ed.hashes.sha512 = sha512;

/** Same forwarding budget as reports (crypto/sign.ts) — a hackathon-scale
 * mesh hop count, not a hard delivery guarantee. */
const DEFAULT_TTL_HOPS = 8;

export type MarkDraft = {
  lat: number;
  lng: number;
  category: MarkCategory;
  label: string;
};

/** The exact object covered by the signature. Must match verifyMark's
 * reconstruction field-for-field, including key names and order-independence
 * (canonicalizeToBytes applies RFC 8785 JCS, so key order in source doesn't
 * matter, but the *set* of included keys does). */
type SignedMarkSubset = {
  schema_version: "1.0.0";
  mark_id: string;
  sender_pubkey: string;
  sender_pubkey_hash: string;
  created_at: string;
  lat: number;
  lng: number;
  category: MarkCategory;
  label: string;
};

export async function createSignedMark(draft: MarkDraft): Promise<MapMark> {
  const identity = await getOrCreateDeviceIdentity();

  const signedSubset: SignedMarkSubset = {
    schema_version: "1.0.0",
    mark_id: randomUuidV4(),
    sender_pubkey: identity.publicKeyB64,
    sender_pubkey_hash: identity.pubkeyHashB64,
    created_at: new Date().toISOString(),
    lat: draft.lat,
    lng: draft.lng,
    category: draft.category,
    label: draft.label,
  };

  const canonicalBytes = canonicalizeToBytes(signedSubset);
  const signatureBytes = ed.sign(canonicalBytes, identity.secretKey);

  return {
    ...signedSubset,
    signature: { algorithm: "Ed25519", value: base64UrlEncode(signatureBytes) },
    ttl_hops: DEFAULT_TTL_HOPS,
    relay_path: [],
  };
}

/**
 * Unlike reports (crypto/sign.ts's relay deliberately skips verification
 * because a trusted backend re-verifies independently), a mark has no
 * backend — this device's own acceptance is the only check that ever runs.
 * Skipping it would let any peer plant an unsigned or forged pin that every
 * other nearby phone displays as if it were a real, attributable claim.
 * A valid signature only proves "this pseudonymous device authored this
 * claim" — it says nothing about whether the claim itself is true.
 */
export async function verifyMark(mark: MapMark): Promise<boolean> {
  try {
    const signedSubset: SignedMarkSubset = {
      schema_version: mark.schema_version,
      mark_id: mark.mark_id,
      sender_pubkey: mark.sender_pubkey,
      sender_pubkey_hash: mark.sender_pubkey_hash,
      created_at: mark.created_at,
      lat: mark.lat,
      lng: mark.lng,
      category: mark.category,
      label: mark.label,
    };
    const canonicalBytes = canonicalizeToBytes(signedSubset);
    const publicKey = base64UrlDecode(mark.sender_pubkey);
    const signatureBytes = base64UrlDecode(mark.signature.value);
    return ed.verify(signatureBytes, canonicalBytes, publicKey);
  } catch {
    return false; // malformed base64/signature from an incompatible or hostile peer
  }
}
