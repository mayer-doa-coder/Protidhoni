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

1. Native Android Gradle build: this workspace has no Android SDK/Gradle environment.
2. Physical two-device Nearby advertising/discovery, including runtime permissions and offline test.
3. Hosted backend health deployment: requires the team’s deployment account and secrets.
4. Mobile Jest rendering test: npm repeatedly extracted incomplete third-party package contents in this workspace (the required `node-releases` data file is absent). This is an environment/package-manager issue; rerun `npm ci` in a normal team environment before the Android build.

These checks are intentionally recorded as pending rather than replaced with mocks or false green status.
