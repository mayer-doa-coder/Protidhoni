import { NativeModules } from "react-native";

type KeystoreWrapNativeModule = {
  wrapKey(rawKeyBase64: string): Promise<string>;
  unwrapKey(wrappedBlobBase64: string): Promise<string>;
};

const nativeModule = NativeModules.KeystoreWrap as KeystoreWrapNativeModule | undefined;

if (!nativeModule) {
  throw new Error("KeystoreWrap native module is not registered. Rebuild the Android app.");
}

export const KeystoreWrap = {
  wrapKey: (rawKeyBase64: string) => nativeModule.wrapKey(rawKeyBase64),
  unwrapKey: (wrappedBlobBase64: string) => nativeModule.unwrapKey(wrappedBlobBase64),
};
