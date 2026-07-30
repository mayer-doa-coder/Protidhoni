# Phase 5: zero-cost LoRa simulation

Phase 5 provides **software/protocol simulation and hardware-readiness
evidence**. It does not prove physical radios, RF range, antennas, electrical
design, battery life, enclosures, regulatory compliance, or a phone-to-radio
BLE/USB link.

## Delivered components and ownership

- Person B: frozen framing, golden vectors, and sender in `hardware/protocol`.
- Person A: bounded reassembly and backend bridge in `hardware/gateway`.
- Person C: deterministic mesh scenarios, evidence, and this runbook in
  `hardware/simulation` and `hardware/evidence`.

The end-to-end simulator exposed a pre-release protocol limit that required a
reviewed cross-owner correction: although the firmware protobuf field permits
233 bytes and the pinned daemon accepts 231 bytes, the pinned Meshtasticator
relay path does not reliably relay that size. Protocol version 1 therefore uses
a measured conservative ceiling of **224 application bytes**, documented in
`protocol/SPEC.md` and enforced by regenerated golden vectors.

The setup pins Meshtasticator commit
`17ceb8231079d87b070abc6132181e4c6b20202d`, Meshtastic Python `2.7.11`, and
daemon image `meshtastic/meshtasticd:2.7.26` by immutable digest. Exact pins and
the synthetic `SHORT_FAST` radio model are machine-readable in
`simulation/versions.json`.

## Reproduce the complete scenario matrix

Prerequisites: Git, Docker Desktop using Linux containers, PowerShell, and
64-bit Python 3.12. From the repository root:

```powershell
.\hardware\simulation\scripts\setup.ps1
docker compose up -d postgres backend
.\hardware\simulation\scripts\run-scenarios.ps1
.\hardware\simulation\scripts\validate.ps1 -RequireEvidenceArtifacts
```

`setup.ps1` creates only ignored state under `hardware/simulation/.runtime`,
checks out the exact upstream commit, applies two verified compatibility edits
to that generated checkout (digest-pinned daemon image and `SHORT_FAST`),
installs pinned dependencies in an isolated environment, writes the canonical
signed fixture, and validates the source definitions. Its final line is:

```text
Phase 5 simulator is ready.
```

The scenario runner starts a fresh Meshtasticator instance for each case, lets
nodes exchange routing information, sends the original signed fixture, feeds
gateway-node packet events through the real bounded gateway processor and
backend client, and records only sanitized outcomes. Expected result lines are:

```text
PASS direct-delivery
PASS required-multi-hop
PASS duplicate-reception
PASS loss-and-application-resend
PASS relay-outage
PASS hop-limit-exhaustion
PASS recovery
```

The pinned daemon permits one TCP API client per simulated node. A second
external sender or gateway connection evicts Meshtasticator's own client and
invalidates the radio path. The integrated runner therefore uses the simulator's
already-connected Meshtastic Python node interfaces while exercising the real
sender plan, gateway processor, reassembler, backend client, and `POST /reports`
path. The standalone TCP sender and receiver adapters are covered separately by
their package tests.

To run selected cases, repeat `-Scenario`:

```powershell
.\hardware\simulation\scripts\run-scenarios.ps1 `
  -Scenario required-multi-hop,hop-limit-exhaustion
```

The runner requires an available backend at `http://127.0.0.1:8000` by default;
use `-BackendUrl` only for an explicitly selected local integration target.

## What the scenarios prove

- `direct`: sender, passive relay node, and gateway are in direct range.
- `relay-required`: only 0–1 and 1–2 have positive modelled margins, so delivery
  to the gateway requires node 1.
- `two-relay-required`: only adjacent links are available across nodes 0–3. A
  hop limit of 1 can cross one relay but cannot cross both, proving exhaustion.
- Duplicate reception resends the exact signed fixture and observes duplicate
  suppression; backend outcome may be accepted on a clean database or duplicate
  when the fixture already exists.
- Loss/resend deterministically omits one middle fragment, verifies incomplete
  reassembly, then performs a complete application resend. It is not an
  acknowledged radio retry because `wantAck=false`.
- Relay outage removes node 1; recovery uses a fresh topology with the relay
  restored.

Evidence in `evidence/generated/scenarios` records timestamps, route hops where
exposed, duplicates, latency, reassembly/backend outcome, pinned versions, and
SHA-256 hashes of sanitized logs. It contains no report content, frame bytes,
exact incident coordinates, signatures, keys, or tokens.

## Manual topology exploration

For visual/manual exploration only:

```powershell
.\hardware\simulation\scripts\start-mesh.ps1 -Topology relay-required -SkipSetup
```

Nodes start at TCP ports 4404 onward. A three-node topology uses gateway port
4406; the four-node topology uses gateway port 4407. Type `plot` for simulator
route data, `remove 1` for an outage, or `exit` to stop. Clean up a stranded
container with `simulation/scripts/stop-mesh.ps1`.

## Site Planner evidence

The official hosted Meshtastic Site Planner was run using the reviewed synthetic
inputs in `simulation/site-planner/study-input.json`. The byte-preserved GeoJSON,
point-to-point PNG, hash-bound manifest, observed summaries, and modelling
limitations are under `evidence/generated/site-planner`.

The representative prediction reported 78.9 km² at or above -130 dBm within the
requested extent. Its 2.37 km point-to-point path reported -98.4 dBm and +31.6 dB
margin, but only 5% first-Fresnel clearance and a marginal verdict. These values
are predictions, not field measurements. The Site Planner study uses its named
LongFast sensitivity profile; the deterministic packet scenarios deliberately
use SHORT_FAST for practical multi-fragment test duration. Neither setting is a
legal authorization to transmit.

## Validation commands

```powershell
.\hardware\simulation\.runtime\.venv\Scripts\python.exe -m pytest .\hardware\protocol\tests .\hardware\gateway\tests
.\hardware\simulation\.runtime\.venv\Scripts\python.exe -m ruff check .\hardware\protocol .\hardware\gateway .\hardware\simulation
.\hardware\simulation\.runtime\.venv\Scripts\python.exe .\hardware\protocol\scripts\generate_vectors.py --check .\hardware\protocol\vectors\golden-v1.json
.\hardware\simulation\.runtime\.venv\Scripts\python.exe -m unittest discover .\hardware\simulation\tests -v
.\hardware\simulation\scripts\validate.ps1 -RequireEvidenceArtifacts
```

## Troubleshooting

- Docker unavailable: start Docker Desktop and select Linux containers.
- `Meshtastic` container exists: run `simulation/scripts/stop-mesh.ps1`.
- Port 4404–4407 is occupied: stop the old simulator/process; preflight fails
  closed rather than connecting to an unknown service.
- Python 3.12 is missing: install it and verify `py -3.12 --version`.
- Backend unavailable: run `docker compose up -d postgres backend`, inspect
  `docker compose logs backend`, and confirm its required local environment.
- Immediate no-delivery: do not reduce the 40-second routing warm-up; verify the
  pinned generated checkout has only the two setup-managed compatibility edits.

## Future physical acceptance checklist and documentation-only BOM

No purchase is required for this hackathon. A future build would need three
mutually compatible Meshtastic-supported LoRa boards; three region-correct
antennas/connectors; safe USB power/data cables; power supplies or protected
batteries; enclosures; and one supported host/phone connection for sender and
gateway roles. Choose exact parts only after current regional radio requirements
and supported firmware targets are reviewed.

Before any “hardware proven” claim, test firmware flashing/rollback;
phone-to-radio BLE/USB; required-relay signed delivery; corruption, loss,
outage, and recovery; measured current and battery life; antenna matching and
connector safety; thermal/enclosure behaviour; range and interference in
permitted locations; signature preservation and backend idempotency; and
current Bangladesh spectrum, power, licensing, and deployment requirements
with the relevant authority.
