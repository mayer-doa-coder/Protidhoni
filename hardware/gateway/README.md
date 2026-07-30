# Protidhoni simulated LoRa uplink gateway

This Person A package receives Protidhoni version-1 `PRIVATE_APP` frames from a
Meshtastic TCP node, reassembles the original signed report with the frozen
`hardware/protocol` codec, and submits it to the existing `POST /reports`
endpoint. It does not add a simulator-only backend endpoint and does not sign or
modify reports.

## Install

From `hardware/gateway`, install both local packages together so pip satisfies
the exact internal protocol dependency from this repository:

```powershell
python -m pip install -e ..\protocol -e ".[dev]"
```

## Run

Start the backend and the Meshtasticator scenario first, then run:

At the frozen Meshtasticator commit, node 2 is the uplink gateway and listens on
TCP port `4406` (`TCP_PORT_OFFSET` 4404 plus node index 2).

```powershell
protidhoni-lora-gateway `
  --meshtastic-host 127.0.0.1 `
  --meshtastic-port 4406 `
  --backend-url http://127.0.0.1:8000
```

Equivalent environment variables are:

```text
PROTIDHONI_LORA_MESHTASTIC_HOST=127.0.0.1
PROTIDHONI_LORA_MESHTASTIC_PORT=4406
PROTIDHONI_LORA_BACKEND_URL=http://127.0.0.1:8000
```

Optional bounded-runtime settings and their defaults:

| Environment variable | Default | Allowed range |
|---|---:|---:|
| `PROTIDHONI_LORA_CONNECT_TIMEOUT_SECONDS` | 30 | 1–300 seconds |
| `PROTIDHONI_LORA_HTTP_TIMEOUT_SECONDS` | 10 | 0.1–120 seconds |
| `PROTIDHONI_LORA_BACKEND_ATTEMPTS` | 3 | 1–10 attempts |
| `PROTIDHONI_LORA_BACKEND_RETRY_DELAY_SECONDS` | 0.5 | 0–60 seconds |
| `PROTIDHONI_LORA_FRAME_QUEUE_CAPACITY` | 512 | 1–4096 frames |
| `PROTIDHONI_LORA_PENDING_CAPACITY` | 32 | 1–32 reports |
| `PROTIDHONI_LORA_PENDING_RETRY_SECONDS` | 10 | 0.1–300 seconds |
| `PROTIDHONI_LORA_PENDING_TTL_SECONDS` | 3600 | 1–86400 seconds |

The pending TTL must be greater than the pending retry interval. Press `Ctrl+C`
for a clean shutdown after the simulation run.

`POST /reports` is the existing public signed-report ingestion endpoint, so the
gateway does not use a responder token. Signature verification, schema
validation, sender rate limiting, encryption at rest, and idempotency remain
backend responsibilities.

The gateway logs only message IDs, fragment counts, outcomes, and aggregate
counters. It never logs report text, coordinates, frame bytes, digests, keys, or
tokens. Pending submissions exist only in bounded process memory and expire; no
sensitive spool file is created.

## Test

```powershell
python -m pytest -q
python -m ruff check .
```

This is software/protocol simulation. It does not validate RF range, antennas,
electrical wiring, power consumption, regulatory compliance, or the future
phone-to-radio BLE/USB link.
