# Protidhoni LoRa transport protocol

This directory is the frozen Phase 5A interface between the sender, simulated
Meshtastic network, and uplink gateway. It is transport-layer framing only: it
does not change `contracts/message-schema.json`, the report signing rule, or any
public backend endpoint.

The normative format is in [`SPEC.md`](SPEC.md). `versions.json` records the
official upstream versions and source used to determine the byte budget. The
Python package is the executable reference implementation; other languages must
produce and consume the same bytes as `vectors/golden-v1.json`.

## Local validation

From this directory:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
python scripts/generate_vectors.py --check vectors/golden-v1.json
```

## Send a signed report to a simulated node

Install the exactly pinned Meshtastic client alongside the protocol package:

```powershell
python -m pip install -e ".[sender]"
```

Validate and inspect a non-sensitive transmission summary without opening a
network connection:

```powershell
protidhoni-lora-send .\signed-report.json --dry-run
```

Send the report to Meshtasticator node 0. At the frozen simulator commit,
`lib/interactive.py` defines `TCP_PORT_OFFSET = 4404`, so node 0 listens on
port `4404`:

```powershell
protidhoni-lora-send .\signed-report.json `
  --host 127.0.0.1 `
  --port 4404 `
  --destination '^all' `
  --channel-index 0 `
  --hop-limit 3
```

The command sends binary `PRIVATE_APP` packets, never text messages. It does not
generate, load, or re-sign with a private key. Its output contains only the
message ID and byte/fragment counts; report text, coordinates, keys, digests,
and frame bodies are never printed. The Meshtastic channel must be configured
with a non-default key outside this command and outside Git.

For reproducible scripts, the same entry point is available without relying on
the shell-installed command name:

```powershell
python -m protidhoni_lora_protocol.sender .\signed-report.json --dry-run
```

The fixed keys in the vector generator are public test material. They must never
be copied into an application, simulator secret, or Meshtastic channel.

## Ownership

Person B owns this directory on `feature/client`. Persons A and C consume the
specification, package, and vectors read-only after Phase 5A is merged. Changing
any version-1 byte, limit, or rule requires a team decision and a new protocol
version; silently changing a golden vector is forbidden.
