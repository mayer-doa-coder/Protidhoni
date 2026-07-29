# Protidhoni

An Android-first, offline-first crisis communication prototype for the July Hackathon 2026 Crisis Tech track.

## Phase 0 status

The repository now has a frozen message/API contract and independently runnable foundations for the backend, React Native mobile client, AI service, and responder dashboard. No report creation, relay, persistence, classifier, or responder workflow is claimed as implemented until Phase 1.

| Owner | Directory | Phase 0 responsibility |
|---|---|---|
| Person A | `contracts/`, `backend/`, `compose.yaml` | Frozen interfaces, FastAPI health foundation, PostGIS schema foundation, deployment configuration |
| Person B | `mobile-client/` | React Native client and Android Nearby Connections discovery bridge |
| Person C | `ai-service/`, `dashboard/` | Isolated model-runtime foundation and React/Leaflet dashboard shell |

Every person works from their own feature branch and only changes their assigned directories. `contracts/` changes require agreement from all three people before a new schema version is introduced.

## Local Phase 0 checks

```powershell
# Backend
$env:PYTHONPATH = "backend/src"
python -m pytest backend/tests -q

# AI service
$env:PYTHONPATH = "ai-service/src"
python -m pytest ai-service/tests -q

# Dashboard
cd dashboard
npm install
npm run build
```

For the Docker stack, copy `.env.example` to `.env`, replace every placeholder secret, then run `docker compose up --build`. Do not use `.env.example` credentials outside local development.

## Required manual acceptance checks

- **Nearby discovery:** Build `mobile-client` with Android Studio or `npx react-native run-android` on two physical Android devices with Google Play services. Grant every permission prompt, start discovery on both, and confirm that each device lists the other. Turn off internet access to prove discovery does not depend on it.
- **Deployment:** Person A connects the backend Docker image to the team’s chosen Render, Railway, or Fly.io account and configures production database and internal-service secrets. This requires team-owned account authority and is not performed by repository code.
- **AI model:** From `ai-service`, install `.[model]` and run `python -m protidhoni_ai.model_probe --download`. The probe only validates the pretrained runtime; it does not validate crisis-classification quality.
