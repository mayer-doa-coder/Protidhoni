import * as ed from "@noble/ed25519";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { canonicalizeToBytes } from "../canonical";
import { _resetDeviceIdentityCacheForTests, getOrCreateDeviceIdentity } from "../identity";
import { createSignedReport } from "../sign";
import { base64UrlDecode } from "../base64url";

const SIGNED_SUBSET_KEYS = [
  "schema_version",
  "message_id",
  "type",
  "sender_pubkey",
  "sender_pubkey_hash",
  "created_at",
  "language",
  "location",
  "payload",
];

const draft = {
  type: "SOS" as const,
  language: "bn" as const,
  location: { lat: 23.81, lng: 90.41, accuracy_m: 5.0, source: "gps" as const },
  payload: { text: "সাহায্য দরকার", people_count: 2, needs: ["water"], attachment_ref: null },
};

describe("createSignedReport", () => {
  beforeEach(async () => {
    _resetDeviceIdentityCacheForTests();
    await AsyncStorage.clear();
  });

  it("produces a self-consistent, verifiable Ed25519 signature", async () => {
    const report = await createSignedReport(draft);
    const identity = await getOrCreateDeviceIdentity();

    const signedSubset: Record<string, unknown> = {};
    for (const key of SIGNED_SUBSET_KEYS) {
      signedSubset[key] = (report as unknown as Record<string, unknown>)[key];
    }
    const canonicalBytes = canonicalizeToBytes(signedSubset);
    const signatureBytes = base64UrlDecode(report.signature.value);

    expect(ed.verify(signatureBytes, canonicalBytes, identity.publicKey)).toBe(true);
  });

  it("fails verification if a signed field is tampered with after signing", async () => {
    const report = await createSignedReport(draft);
    const identity = await getOrCreateDeviceIdentity();

    const tampered: Record<string, unknown> = {};
    for (const key of SIGNED_SUBSET_KEYS) {
      tampered[key] = (report as unknown as Record<string, unknown>)[key];
    }
    tampered.payload = { ...report.payload, text: "different text" };

    const canonicalBytes = canonicalizeToBytes(tampered);
    const signatureBytes = base64UrlDecode(report.signature.value);

    expect(ed.verify(signatureBytes, canonicalBytes, identity.publicKey)).toBe(false);
  });

  it("does not cover ttl_hops/relay_path/priority/verification/sync_status in the signature", async () => {
    const report = await createSignedReport(draft);
    const identity = await getOrCreateDeviceIdentity();

    const signedSubset: Record<string, unknown> = {};
    for (const key of SIGNED_SUBSET_KEYS) {
      signedSubset[key] = (report as unknown as Record<string, unknown>)[key];
    }
    const canonicalBytes = canonicalizeToBytes(signedSubset);
    const signatureBytes = base64UrlDecode(report.signature.value);

    // Mutating only the excluded, mutable fields must not affect verifiability
    // of the ORIGINAL signed subset (they were never part of it).
    const mutated = { ...report, ttl_hops: report.ttl_hops - 1, relay_path: ["A".repeat(43)] };
    expect(mutated.ttl_hops).not.toBe(report.ttl_hops);
    expect(ed.verify(signatureBytes, canonicalBytes, identity.publicKey)).toBe(true);
  });

  it("generates a fresh UUID message_id for every report", async () => {
    const first = await createSignedReport(draft);
    const second = await createSignedReport(draft);
    expect(first.message_id).not.toBe(second.message_id);
    expect(first.message_id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("sets Phase 1 defaults: local sync_status, unverified verification, no relay hops taken yet", async () => {
    const report = await createSignedReport(draft);
    expect(report.sync_status).toBe("local");
    expect(report.verification).toEqual({ status: "unverified", corroboration_count: 0 });
    expect(report.relay_path).toEqual([]);
    expect(report.priority).toBeNull();
  });
});
