# Phase 0 acceptance record

## Automated checks

- JSON Schema parsed and a representative SOS message validated with Draft 2020-12 validation and date-time format checks.
- OpenAPI YAML parsed and required contract paths verified.
- Backend source compiled; its FastAPI health endpoint was exercised through its test client.
- AI source compiled; its FastAPI health endpoint was exercised through its test client.
- The selected official `csebuetnlp/banglabert` model was explicitly downloaded and loaded locally. The probe tokenized a Bangla emergency sentence and loaded **110,026,752** parameters.
- Dashboard TypeScript typecheck and production Vite build completed.
- Mobile TypeScript typecheck completed, including the contract types and React Native native-module boundary.
- `docker compose --env-file .env.example config` completed. Image build could not run because Docker Desktop’s Linux daemon is not running in this workspace.

## Manual checks pending

1. ~~Native Android Gradle build: this workspace has no Android SDK/Gradle environment.~~ **Resolved and verified** during the Phase 0–6 system audit: a truly clean `assembleDebug` (with `android/app/.cxx` removed to force a fresh CMake configure) fails under JDK 25 with a `configureCMakeDebug` restricted-method error, and succeeds under JDK 17, producing a working `app-debug.apk`. `android/build.gradle` now fails fast with an actionable message on the wrong JDK. See the top-level `README.md` §7 and `mobile-client/README.md`.
2. Physical two-device Nearby advertising/discovery, including runtime permissions and offline test. **Still pending** — requires two physical Android devices, which this environment does not have.
3. Hosted backend health deployment: requires the team's deployment account and secrets. **Still pending** — requires account-level authority not available to this environment.
4. ~~Mobile Jest rendering test: npm repeatedly extracted incomplete third-party package contents in this workspace...~~ **Resolved and verified**: the full mobile-client jest suite now runs cleanly (116 tests passing, 13 suites) and `tsc --noEmit` is clean. See `README.md` §6 for the current count.

These checks are intentionally recorded as pending rather than replaced with mocks or false green status. Items 2 and 3 remain genuinely pending because they require physical hardware or account access this environment does not have — not because they were untested by choice.
