# Mobile client — Person B

The mobile client is React Native with Android-native Kotlin only where the platform requires it. Phase 0 is intentionally limited to advertising and discovering nearby devices through Google Nearby Connections; it does not connect to peers, relay reports, or claim a completed mesh.

## Why the native bridge exists

React Native owns the UI and typed report model. `android/.../NearbyConnectionsModule.kt` owns Nearby Connections because device discovery, permissions, and radio APIs are Android-native. Its `P2P_CLUSTER` strategy gives the app direct M-to-N nearby links. Phase 1 will add authenticated user-approved connections and application-level store-and-forward relay logic above those direct links.

## Run and verify on devices

```powershell
npm install
npx react-native run-android
```

Install the app on two physical Android devices with current Google Play services. On both devices:

1. Turn off Wi-Fi and mobile data; leave Bluetooth enabled.
2. Allow every requested Nearby/Bluetooth permission.
3. Tap **Start nearby discovery**.
4. Confirm that each device appears in the other device’s list.

The app deliberately rejects connection attempts in Phase 0. Do not use an emulator as evidence of Bluetooth/Wi-Fi peer discovery.
