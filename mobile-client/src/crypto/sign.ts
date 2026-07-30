import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha2.js";

import type { CrisisReport, ReportType } from "../contracts/report";
import { base64UrlEncode } from "./base64url";
import { canonicalizeToBytes } from "./canonical";
import { getOrCreateDeviceIdentity } from "./identity";
import { randomUuidV4 } from "./uuid";

ed.hashes.sha512 = sha512;

/** Forwarding budget for a report created on this device. Modest relative to
 * the schema's max of 16 — hackathon-scale mesh hops, not a hard guarantee. */
const DEFAULT_TTL_HOPS = 8;

export type ReportDraft = {
  type: ReportType;
  language: "bn" | "en";
  location: CrisisReport["location"];
  payload: CrisisReport["payload"];
};

/** The exact object shape covered by the signature — must match
 * contracts/README.md's "Report signing rule" and backend/.../models.py's
 * `Report.signed_subset()` field-for-field, including key names. */
type SignedSubset = {
  schema_version: "1.0.0";
  message_id: string;
  type: ReportType;
  sender_pubkey: string;
  sender_pubkey_hash: string;
  created_at: string;
  language: "bn" | "en";
  location: CrisisReport["location"];
  payload: CrisisReport["payload"];
};

export async function createSignedReport(draft: ReportDraft): Promise<CrisisReport> {
  const identity = await getOrCreateDeviceIdentity();

  const signedSubset: SignedSubset = {
    schema_version: "1.0.0",
    message_id: randomUuidV4(),
    type: draft.type,
    sender_pubkey: identity.publicKeyB64,
    sender_pubkey_hash: identity.pubkeyHashB64,
    created_at: new Date().toISOString(),
    language: draft.language,
    location: draft.location,
    payload: draft.payload,
  };

  const canonicalBytes = canonicalizeToBytes(signedSubset);
  const signatureBytes = ed.sign(canonicalBytes, identity.secretKey);

  return {
    ...signedSubset,
    priority: null,
    ttl_hops: DEFAULT_TTL_HOPS,
    signature: { algorithm: "Ed25519", value: base64UrlEncode(signatureBytes) },
    relay_path: [],
    sync_status: "local",
    verification: { status: "unverified", corroboration_count: 0 },
  };
}
