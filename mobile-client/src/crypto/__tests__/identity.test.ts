import AsyncStorage from "@react-native-async-storage/async-storage";

import { _resetDeviceIdentityCacheForTests, getOrCreateDeviceIdentity } from "../identity";

describe("getOrCreateDeviceIdentity", () => {
  beforeEach(async () => {
    _resetDeviceIdentityCacheForTests();
    await AsyncStorage.clear();
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
});
