# Android setup, two-device testing, and release

This is the Windows runbook for the bare React Native app in `mobile-client`.
It covers a clean machine, two simultaneously connected Android phones, an
offline Nearby Connections acceptance test, and signed APK/AAB production
artifacts.

## 1. Fixed project toolchain

Use the versions below. They are the versions currently validated by a clean
debug build and a complete signed APK/AAB verification build.

| Component | Version |
| --- | --- |
| React Native | 0.86.2 |
| React | 19.2.8 |
| Node.js | 20.19.4+, 22.13.0+, or 24.3.0+ in the supported release lines |
| JDK | Temurin/OpenJDK 17 |
| Gradle wrapper | 9.5.1 |
| Android Gradle Plugin | 8.12.0, owned by React Native 0.86.2 |
| Kotlin / KSP | 2.3.20 / 2.3.9 |
| Android compile/target SDK | 36 / 36 |
| Android Build Tools | 36.0.0 |
| Android NDK | 27.1.12297006 |
| CMake | 3.22.1 |
| Minimum Android API | 24 (Android 7.0) |

Do not use the globally installed legacy Expo CLI. This is not an Expo app.

Gradle 9.5.1 embeds Kotlin 2.3.20, while the React Native 0.86.2 Gradle plugin
was published with Kotlin 2.1.20 and API level 1.8. `npm ci` applies the small
versioned patch in `mobile-client/patches` so the included plugin compiles with
Gradle 9.5.1. Do not remove `patch-package` or skip the post-install script.

## 2. Install the software from scratch

Open PowerShell and install Git, Node.js, Android Studio, and JDK 17. If Git,
Node, and Android Studio are already installed, keep them and install only the
missing parts.

Install JDK 17:

```powershell
winget install --id EclipseAdoptium.Temurin.17.JDK --exact --accept-source-agreements --accept-package-agreements
```

Install a supported Node LTS release from the Node.js site or with your normal
version manager. Verify it:

```powershell
node --version
npm --version
git --version
```

In Android Studio, open **Settings > Languages & Frameworks > Android SDK** and
install:

1. **SDK Platforms**: Android API 36.
2. **SDK Tools**, with **Show Package Details** enabled:
   Android SDK Build-Tools 36.0.0, Android SDK Platform-Tools, Android SDK
   Command-line Tools (latest), NDK 27.1.12297006, and CMake 3.22.1.

The normal Windows SDK location is
`C:\Users\<you>\AppData\Local\Android\Sdk`.

## 3. Configure the current PowerShell session

From the repository root, dot-source the checked-in helper. Dot-sourcing is
important because the variables must remain in the current terminal:

```powershell
cd D:\Protidhoni\mobile-client
. .\scripts\android-env.ps1
```

If JDK or the SDK is in a custom directory:

```powershell
. .\scripts\android-env.ps1 `
  -Jdk17Path "D:\Tools\jdk-17" `
  -AndroidSdkPath "D:\Android\Sdk"
```

Confirm that JDK 17 is first on `PATH`:

```powershell
where.exe java
java -version
adb version
```

`java -version` must report 17. A separate system Java 25 installation is fine
as long as this terminal finds JDK 17 first.

To persist the two directory variables for future terminals:

```powershell
[Environment]::SetEnvironmentVariable(
  "JAVA_HOME",
  "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.8-hotspot",
  "User"
)
[Environment]::SetEnvironmentVariable(
  "ANDROID_HOME",
  (Join-Path $env:LOCALAPPDATA "Android\Sdk"),
  "User"
)
```

Open a new terminal after changing persistent variables. Continue to use the
helper when another Java installation appears earlier on the combined Windows
`PATH`.

## 4. Install and verify the project

Use `npm ci`, not `npm update`, for a reproducible install from the lockfile:

```powershell
cd D:\Protidhoni\mobile-client
npm ci
npm run verify
.\android\gradlew.bat --version
npm run doctor:android
```

Expected results:

- 14 Jest suites and 124 tests pass.
- TypeScript and ESLint pass.
- The wrapper reports Gradle 9.5.1 and JVM 17.
- The doctor may report that Metro is stopped and no Android device is
  connected. Those are expected until the next steps.

Do not run `npm audit fix --force`. npm currently proposes incompatible
downgrades/major changes for parts of React Native's build and test toolchain.

## 5. Prepare both physical phones

Repeat these steps on phone A and phone B:

1. Install all Android and Google Play system updates.
2. Open **Settings > About phone** and tap **Build number** seven times.
3. Open **Developer options** and enable **USB debugging**.
4. Connect the phone by a data-capable USB cable.
5. Unlock it and accept the computer's RSA debugging prompt.

Check both devices:

```powershell
adb devices -l
```

There must be two different serial numbers with status `device`. If a phone is
`unauthorized`, unlock it, revoke USB debugging authorizations, reconnect it,
and accept the prompt again.

Store the serials in terminal variables for convenience. Replace the examples:

```powershell
$phoneA = "PHONE_A_SERIAL"
$phoneB = "PHONE_B_SERIAL"
adb -s $phoneA get-state
adb -s $phoneB get-state
```

Never omit `-s <serial>` while both devices are connected; otherwise adb will
fail with “more than one device/emulator.”

## 6. Build and install the debug APK on both phones

Build once:

```powershell
npm run build:debug-apk
```

The output is:

```text
mobile-client\android\app\build\outputs\apk\debug\app-debug.apk
```

Install the identical APK on both phones:

```powershell
$debugApk = "D:\Protidhoni\mobile-client\android\app\build\outputs\apk\debug\app-debug.apk"
adb -s $phoneA install -r $debugApk
adb -s $phoneB install -r $debugApk
```

Map each device's port 8081 to Metro on the computer:

```powershell
adb -s $phoneA reverse tcp:8081 tcp:8081
adb -s $phoneB reverse tcp:8081 tcp:8081
adb -s $phoneA reverse --list
adb -s $phoneB reverse --list
```

Start Metro in terminal 1 and leave it running:

```powershell
cd D:\Protidhoni\mobile-client
npm start -- --reset-cache
```

Launch both apps from terminal 2:

```powershell
adb -s $phoneA shell am start -n com.protidhonimobile/.MainActivity
adb -s $phoneB shell am start -n com.protidhonimobile/.MainActivity
```

For device-specific logs:

```powershell
adb -s $phoneA logcat ReactNativeJS:V AndroidRuntime:E '*:S'
adb -s $phoneB logcat ReactNativeJS:V AndroidRuntime:E '*:S'
```

## 7. Debug backend configuration

For a backend on the same computer, start the backend first. With USB connected,
reverse its port on both phones:

```powershell
adb -s $phoneA reverse tcp:8000 tcp:8000
adb -s $phoneB reverse tcp:8000 tcp:8000
```

In each app, open **Nearby > Backend connection**, enter
`http://127.0.0.1:8000`, and save it. Alternatively, when the phones and
computer share Wi-Fi, use the computer's LAN address such as
`http://192.168.1.20:8000` and allow TCP 8000 through Windows Firewall.

Debug builds allow HTTP for local development. Release builds intentionally
disable cleartext HTTP; a release build must use an HTTPS backend with a valid
certificate.

## 8. Two-phone offline Nearby acceptance test

Do not use an emulator for this test. It is meant to prove real Bluetooth/Wi-Fi
radio discovery and relay.

1. On phone A, create at least one report while online and confirm it appears
   under **My reports** with `local` status.
2. Close and reopen phone A. Confirm the report persists.
3. Put both phones in airplane mode.
4. Re-enable Bluetooth and Wi-Fi on both phones, but do not connect to an
   internet-providing network. Nearby Connections may use both radios.
5. Keep Location enabled where the Android version/device requires it.
6. Open **Nearby** on both phones and press **Start nearby discovery**.
7. Grant every Bluetooth, nearby-device, Wi-Fi, and location permission that
   Android requests. Denying any required permission prevents discovery.
8. On the receiving phone, compare the authentication digits shown for the
   connection. First press **Decline** and confirm no report transfers.
9. Start discovery again, compare the digits, and press **Accept**.
10. Confirm phone B receives phone A's report and phone A changes it to
    `relayed`. Repeating discovery must not create duplicate reports.
11. Stop discovery, restart both apps, and confirm the stored queue/statuses
    remain intact.
12. Give phone B internet access and set a reachable backend URL. Confirm its
    queue synchronizes and accepted/duplicate records become `synced`.
13. Confirm the backend/dashboard shows the same `message_id` and that the
    signature verifies.

Also exercise these cases before release:

- All seven report types.
- GPS, manual coordinates, and no-location input.
- TTL exhaustion and duplicate relay handling.
- Permission denial followed by permission grant.
- Bluetooth/Wi-Fi toggled off and back on.
- App process killed during a queued report.
- Wrong/unreachable backend and recovery after correcting it.
- Two independently generated device identities; clearing app storage should
  create a new identity.

Record phone models, Android versions, timestamp, permission state, radio state,
backend URL, and screenshots/logs in `docs/phase-6-acceptance.md`.

## 9. Decide permanent release identity before publishing

Before generating a real release, confirm these values in
`mobile-client/android/app/build.gradle`:

- `applicationId`: currently `com.protidhonimobile`.
- `versionCode`: currently `1`; it must increase for every store upload.
- `versionName`: currently `0.1.0`; this is the user-visible version.

The Google Play package/application ID cannot be changed after the first
publication without creating a different app. Decide the final organization
domain and package ID before the first upload.

## 10. Generate and protect the permanent upload key

Create a secure directory outside Git and run `keytool`. Do not put the password
on the command line; let `keytool` prompt for it:

```powershell
New-Item -ItemType Directory -Path "D:\SecureKeys\Protidhoni" -Force
& "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -v `
  -storetype PKCS12 `
  -keystore "D:\SecureKeys\Protidhoni\protidhoni-upload-key.jks" `
  -alias "protidhoni-upload" `
  -keyalg RSA `
  -keysize 2048 `
  -validity 10000
```

Back up the `.jks` file and passwords in two secure locations. Never commit the
key, put it in chat, email it, or share it with APK recipients.

Create the ignored local signing file:

```powershell
Copy-Item .\android\keystore.properties.example .\android\keystore.properties
notepad .\android\keystore.properties
```

Fill it with your real values. Use forward slashes in the Windows path:

```properties
storeFile=D:/SecureKeys/Protidhoni/protidhoni-upload-key.jks
storePassword=YOUR_PRIVATE_STORE_PASSWORD
keyAlias=protidhoni-upload
keyPassword=YOUR_PRIVATE_KEY_PASSWORD
```

`android/keystore.properties`, `*.jks`, and `*.keystore` are ignored by Git.
Release tasks fail early if the file, required values, or key file is missing.

## 11. Build the production APK and AAB

Run the full verification and both release builds:

```powershell
npm ci
npm run verify
npm run build:release-apk
npm run build:release-aab
```

Outputs:

```text
mobile-client\android\app\build\outputs\apk\release\app-release.apk
mobile-client\android\app\build\outputs\bundle\release\app-release.aab
```

The universal APK is for direct two-phone installation and non-Play
distribution. Upload the AAB to Google Play so Play can deliver optimized APKs.

## 12. Verify signatures and hashes

```powershell
$sdk = $env:ANDROID_HOME
$releaseApk = "D:\Protidhoni\mobile-client\android\app\build\outputs\apk\release\app-release.apk"
$releaseAab = "D:\Protidhoni\mobile-client\android\app\build\outputs\bundle\release\app-release.aab"

& "$sdk\build-tools\36.0.0\apksigner.bat" verify --verbose --print-certs $releaseApk
& "$env:JAVA_HOME\bin\jarsigner.exe" -verify $releaseAab
Get-FileHash -Algorithm SHA256 $releaseApk
Get-FileHash -Algorithm SHA256 $releaseAab
```

Confirm that the APK certificate belongs to your permanent key, not `Android
Debug` and not `Temporary Build Verification`. Save the SHA-256 hashes with the
release notes.

## 13. Install the release APK on both phones

Debug and release certificates differ. Because Android will not replace an app
with another certificate, uninstall the debug app first. This erases its local
queue and identity, so finish debug acceptance and export any evidence first:

```powershell
adb -s $phoneA uninstall com.protidhonimobile
adb -s $phoneB uninstall com.protidhonimobile

$releaseApk = "D:\Protidhoni\mobile-client\android\app\build\outputs\apk\release\app-release.apk"
adb -s $phoneA install $releaseApk
adb -s $phoneB install $releaseApk
```

Launch both apps. Metro can be stopped; release builds contain the JavaScript
bundle. Repeat the full offline relay test and then test synchronization against
the production HTTPS backend.

## 14. Google Play release checklist

1. Create the Play Console app with the final package ID.
2. Enroll in Play App Signing and keep your upload key private.
3. Upload `app-release.aab` to Internal testing first.
4. Complete Data safety, permissions, privacy policy, content rating, target
   audience, screenshots, icon, and store listing.
5. Explain the nearby-device, Bluetooth/Wi-Fi, and location permissions in the
   listing and in-app disclosure where required.
6. Install the Play-delivered build on both phones and repeat the acceptance
   test.
7. Promote through closed/open testing only after crash, permission, offline,
   relay, and backend-sync evidence is complete.

Official references:

- React Native environment setup: https://reactnative.dev/docs/set-up-your-environment
- React Native device testing: https://reactnative.dev/docs/running-on-device
- React Native Android publishing: https://reactnative.dev/docs/signed-apk-android
- Android app signing: https://developer.android.com/studio/publish/app-signing
- Google Nearby Connections setup and permissions: https://developers.google.com/nearby/connections/android/get-started
- Gradle 9.x upgrade notes: https://docs.gradle.org/current/userguide/upgrading_version_9.html
