import AsyncStorage from "@react-native-async-storage/async-storage";

import { base64Encode } from "../base64";
import { base64UrlEncode } from "../base64url";

jest.mock("../../native/KeystoreWrap");

import { KeystoreWrap } from "../../native/KeystoreWrap";
import { _resetDeviceIdentityCacheForTests, getOrCreateDeviceIdentity } from "../identity";

const STORAGE_KEY_V1 = "protidhoni.device_identity.v1";
const STORAGE_KEY_V2 = "protidhoni.device_identity.v2";

describe("getOrCreateDeviceIdentity", () => {
  beforeEach(async () => {
    _resetDeviceIdentityCacheForTests();
    await AsyncStorage.clear();
    (KeystoreWrap.wrapKey as jest.Mock).mockClear();
    (KeystoreWrap.unwrapKey as jest.Mock).mockClear();
  });

  it("generates a 32-byte public key and a 32-byte pubkey hash", async () => {
    const identity = await getOrCreateDeviceIdentity();
    expect(identity.publicKey).toHaveLength(32);
    expect(identity.publicKeyB64).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(identity.pubkeyHashB64).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("persists the identity across cache resets (simulating app restart)", async () => {
    const first = await getOrCreateDeviceIdentity();
    _resetDeviceIdentityCacheForTests();
    const second = await getOrCreateDeviceIdentity();
    expect(second.publicKeyB64).toBe(first.publicKeyB64);
  });

  it("generates a different identity per device (no shared/hardcoded key)", async () => {
    const first = await getOrCreateDeviceIdentity();
    await AsyncStorage.clear();
    _resetDeviceIdentityCacheForTests();
    const second = await getOrCreateDeviceIdentity();
    expect(second.publicKeyB64).not.toBe(first.publicKeyB64);
  });

  it("concurrent callers before first resolution get the same identity", async () => {
    const [a, b] = await Promise.all([getOrCreateDeviceIdentity(), getOrCreateDeviceIdentity()]);
    expect(a.publicKeyB64).toBe(b.publicKeyB64);
  });

  it("stores a fresh identity wrapped (v2), never in plaintext (v1)", async () => {
    await getOrCreateDeviceIdentity();

    expect(KeystoreWrap.wrapKey).toHaveBeenCalledTimes(1);
    expect(await AsyncStorage.getItem(STORAGE_KEY_V1)).toBeNull();
    expect(await AsyncStorage.getItem(STORAGE_KEY_V2)).toEqual(expect.stringMatching(/^wrapped:/));
  });

  it("migrates a v1 plaintext identity to wrapped v2 storage, keeping the same public key", async () => {
    const secretKeyBytes = new Uint8Array(32).fill(7);
    await AsyncStorage.setItem(STORAGE_KEY_V1, base64UrlEncode(secretKeyBytes));

    const migrated = await getOrCreateDeviceIdentity();

    expect(KeystoreWrap.wrapKey).toHaveBeenCalledWith(base64Encode(secretKeyBytes));
    expect(await AsyncStorage.getItem(STORAGE_KEY_V1)).toBeNull();
    expect(await AsyncStorage.getItem(STORAGE_KEY_V2)).toEqual(expect.stringMatching(/^wrapped:/));

    _resetDeviceIdentityCacheForTests();
    const reloaded = await getOrCreateDeviceIdentity();
    expect(reloaded.publicKeyB64).toBe(migrated.publicKeyB64);
    expect(reloaded.pubkeyHashB64).toBe(migrated.pubkeyHashB64);
  });

  it("an existing v2 wrapped identity is unwrapped, not re-wrapped, on load", async () => {
    const first = await getOrCreateDeviceIdentity();
    _resetDeviceIdentityCacheForTests();
    (KeystoreWrap.wrapKey as jest.Mock).mockClear();

    const second = await getOrCreateDeviceIdentity();

    expect(second.publicKeyB64).toBe(first.publicKeyB64);
    expect(KeystoreWrap.wrapKey).not.toHaveBeenCalled();
    expect(KeystoreWrap.unwrapKey).toHaveBeenCalledTimes(1);
  });
});
