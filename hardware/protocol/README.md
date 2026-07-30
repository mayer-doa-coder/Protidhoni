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

The fixed keys in the vector generator are public test material. They must never
be copied into an application, simulator secret, or Meshtastic channel.

## Ownership

Person B owns this directory on `feature/client`. Persons A and C consume the
specification, package, and vectors read-only after Phase 5A is merged. Changing
any version-1 byte, limit, or rule requires a team decision and a new protocol
version; silently changing a golden vector is forbidden.
