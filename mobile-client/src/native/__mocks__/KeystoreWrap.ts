/**
 * Manual Jest mock for the native KeystoreWrap module. A real Android
 * Keystore can't run under Jest, so this stands in with a simple reversible
 * marker — enough to prove wrap/unwrap round trips and the v1-to-v2
 * migration path in identity.ts; the real hardware-backed encryption is
 * exercised on-device (see mobile-client/README.md). Jest does not apply
 * local (non-node_modules) manual mocks automatically — every consuming
 * test file must still call `jest.mock(".../native/KeystoreWrap")`.
 */
export const KeystoreWrap = {
  wrapKey: jest.fn(async (rawKeyBase64: string) => `wrapped:${rawKeyBase64}`),
  unwrapKey: jest.fn(async (wrappedBlobBase64: string) => wrappedBlobBase64.replace(/^wrapped:/, "")),
};
