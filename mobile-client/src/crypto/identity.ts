import * as ed from "@noble/ed25519";
import { sha256, sha512 } from "@noble/hashes/sha2.js";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { KeystoreWrap } from "../native/KeystoreWrap";
import { base64Decode, base64Encode } from "./base64";
import { base64UrlDecode, base64UrlEncode } from "./base64url";

ed.hashes.sha512 = sha512;

const STORAGE_KEY_V1 = "protidhoni.device_identity.v1";
const STORAGE_KEY_V2 = "protidhoni.device_identity.v2";

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

async function storeWrapped(secretKey: Uint8Array): Promise<void> {
  const wrapped = await KeystoreWrap.wrapKey(base64Encode(secretKey));
  await AsyncStorage.setItem(STORAGE_KEY_V2, wrapped);
}

/**
 * Loads the device's persistent Ed25519 identity, generating one on first
 * launch. contracts/README.md requires `sender_pubkey_hash` to be derived
 * from a real cryptographic key generated on-device — never a MAC address,
 * phone number, or Bluetooth session id (the Bridgefy lesson in
 * Protidhoni_Roadmap.md §8).
 *
 * Phase 3: the raw secret key is never persisted in plaintext. It is wrapped
 * with a Keystore-backed AES-256-GCM key (StrongBox-backed where the device
 * supports it — see android/.../security/KeystoreWrapModule.kt) before being
 * stored, and exists in JS memory only for the duration of an unwrap. A v1
 * plaintext identity from before this change is migrated transparently on
 * first load, reusing the *same* secret key bytes — regenerating would
 * change sender_pubkey_hash and invalidate every prior relay/sync history.
 */
export async function getOrCreateDeviceIdentity(): Promise<DeviceIdentity> {
  if (cached) return cached;
  if (pending) return pending;

  pending = (async () => {
    const wrappedV2 = await AsyncStorage.getItem(STORAGE_KEY_V2);
    if (wrappedV2) {
      const rawKeyBase64 = await KeystoreWrap.unwrapKey(wrappedV2);
      cached = deriveIdentity(base64Decode(rawKeyBase64));
      return cached;
    }

    const plaintextV1 = await AsyncStorage.getItem(STORAGE_KEY_V1);
    if (plaintextV1) {
      const secretKey = base64UrlDecode(plaintextV1);
      await storeWrapped(secretKey);
      await AsyncStorage.removeItem(STORAGE_KEY_V1);
      cached = deriveIdentity(secretKey);
      return cached;
    }

    const secretKey = ed.utils.randomSecretKey();
    await storeWrapped(secretKey);
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
