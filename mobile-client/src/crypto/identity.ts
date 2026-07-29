import * as ed from "@noble/ed25519";
import { sha256, sha512 } from "@noble/hashes/sha2.js";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { base64UrlDecode, base64UrlEncode } from "./base64url";

ed.hashes.sha512 = sha512;

const STORAGE_KEY = "protidhoni.device_identity.v1";

export type DeviceIdentity = {
  secretKey: Uint8Array;
  publicKey: Uint8Array;
  publicKeyB64: string;
  pubkeyHashB64: string;
};

let cached: DeviceIdentity | null = null;
let pending: Promise<DeviceIdentity> | null = null;

function deriveIdentity(secretKey: Uint8Array): DeviceIdentity {
  const publicKey = ed.getPublicKey(secretKey);
  return {
    secretKey,
    publicKey,
    publicKeyB64: base64UrlEncode(publicKey),
    pubkeyHashB64: base64UrlEncode(sha256(publicKey)),
  };
}

/**
 * Loads the device's persistent Ed25519 identity, generating one on first
 * launch. contracts/README.md requires `sender_pubkey_hash` to be derived
 * from a real cryptographic key generated on-device — never a MAC address,
 * phone number, or Bluetooth session id (the Bridgefy lesson in
 * Protidhoni_Roadmap.md §8).
 *
 * Phase 1 simplification, deliberately not hardened yet: the private key is
 * stored base64url-encoded in AsyncStorage (app-sandboxed but unencrypted
 * plain storage), not Android Keystore-backed secure storage. Moving it
 * behind Keystore/EncryptedSharedPreferences is Phase 3 security-hardening
 * work, not Phase 1 scope.
 */
export async function getOrCreateDeviceIdentity(): Promise<DeviceIdentity> {
  if (cached) return cached;
  if (pending) return pending;

  pending = (async () => {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (stored) {
      cached = deriveIdentity(base64UrlDecode(stored));
      return cached;
    }
    const secretKey = ed.utils.randomSecretKey();
    await AsyncStorage.setItem(STORAGE_KEY, base64UrlEncode(secretKey));
    cached = deriveIdentity(secretKey);
    return cached;
  })();

  try {
    return await pending;
  } finally {
    pending = null;
  }
}

export function _resetDeviceIdentityCacheForTests(): void {
  cached = null;
  pending = null;
}
