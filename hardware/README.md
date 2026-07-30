# Phase 5: zero-cost LoRa simulation

This phase provides **software/protocol simulation and hardware-readiness
evidence**. It does not prove physical hardware, RF range, antennas, electrical
design, power life, enclosures, regulatory compliance, or the phone-to-radio
BLE/USB link.

## Ownership and prerequisites

- Person B owns `hardware/protocol`; Person A owns `hardware/gateway`.
- Person C owns `hardware/simulation`, `hardware/evidence`, and this file.
- Run end-to-end scenarios only after the Person A and Person B Phase 5 commits
  are merged with this branch.
- Install Git, Docker Desktop with Linux containers, and 64-bit Python 3.12.

The setup is pinned to Meshtasticator commit
`17ceb8231079d87b070abc6132181e4c6b20202d`, Meshtastic Python `2.7.11`, and
daemon image `meshtastic/meshtasticd:2.7.26` by immutable image-index digest.
The complete machine-readable pins are in `simulation/versions.json`.

The reviewed Meshtasticator source uses TCP ports **4404, 4405, and 4406** for
nodes 0, 1, and 2. Earlier upstream prose and the current sender/gateway default
examples say 4403; always pass the explicit ports below until those two branch
defaults are corrected.

## One-command simulator setup

From the repository root in PowerShell:

```powershell
.\hardware\simulation\scripts\setup.ps1
```

This creates only ignored state under `hardware/simulation/.runtime`, checks out
the exact upstream commit, injects the digest-pinned daemon image into that
generated checkout, installs pinned direct dependencies in an isolated Python
3.12 environment, records `pip freeze`, pulls the image, validates the frozen
fixture, and checks both topologies. Expected final line:

```text
Phase 5 simulator is ready.
```

Start the required-relay topology:

```powershell
.\hardware\simulation\scripts\start-mesh.ps1 -Topology relay-required -SkipSetup
```

Keep that terminal open. Expected ports are sender `4404`, relay `4405`, and
gateway `4406`. The synthetic 0-to-2 link is deliberately outside the pinned
model while 0-to-1 and 1-to-2 have positive modelled margins.

## Integrated signed-report run

After all Phase 5 branches are merged, create a separate integration environment:

```powershell
py -3.12 -m venv .\hardware\.venv
.\hardware\.venv\Scripts\python.exe -m pip install -e .\hardware\protocol -e .\hardware\gateway
docker compose up -d backend
```

Use three PowerShell terminals.

Terminal 1 — simulator:

```powershell
.\hardware\simulation\scripts\start-mesh.ps1 -Topology relay-required -SkipSetup
```

Terminal 2 — gateway on node 2:

```powershell
.\hardware\.venv\Scripts\python.exe -m protidhoni_lora_gateway.cli `
  --meshtastic-host 127.0.0.1 --meshtastic-port 4406 `
  --backend-url http://127.0.0.1:8000
```

Terminal 3 — sender on node 0:

```powershell
.\hardware\.venv\Scripts\python.exe -m protidhoni_lora_protocol.sender `
  .\hardware\simulation\.runtime\signed-report.json `
  --host 127.0.0.1 --port 4404 --destination '^all' --hop-limit 3
```

The sender should report a validated message ID and fragment count. The gateway
should report an accepted or idempotent duplicate report without printing its
content. The backend must accept the original signed bytes; no relay re-signs
the fixture. Stop the gateway with `Ctrl+C`, type `exit` in Meshtasticator, and
remove a stranded simulator container only when needed:

```powershell
.\hardware\simulation\scripts\stop-mesh.ps1
```

## Scenario checklist

The exact matrix and expectations are in `simulation/scenarios.json`.

- Direct delivery: use `direct`, send once with hop limit 3.
- Required multi-hop: use `relay-required`, send once with hop limit 3.
- Duplicate reception: send the unchanged fixture twice; backend idempotency
  must prevent a second stored report.
- Loss/resend: run with collision observation enabled, record loss only if it is
  actually observed, and resend unchanged. The sender uses `wantAck=false`, so
  this is an application resend—not proof of acknowledged radio retry.
- Relay outage: in the simulator console enter `remove 1`, then send; node 2
  must not receive in the required-relay topology.
- Hop exhaustion: restart `relay-required` and send with `--hop-limit 1`; it
  must not reach node 2.
- Recovery: restart all three nodes, reconnect the gateway, and resend with hop
  limit 3; delivery must recover.

Capture start/end UTC timestamps and observed metrics, then use
`simulation/scripts/record-evidence.ps1`. The validator requires delivery,
duplicate count, latency for delivery, route/hops when available, reassembly
outcome, and backend outcome. Validate everything with:

```powershell
.\hardware\simulation\scripts\validate.ps1
py -3.12 -m unittest discover .\hardware\simulation\tests -v
```

Generated evidence is kept in `hardware/evidence/generated`; source definitions
stay outside it. Never manually rewrite a run record or Site Planner export.

## Site Planner

Follow `simulation/site-planner/README.md`. The representative study remains
marked `not-run` until the official browser tool actually produces a coverage
export and point-to-point result. Predictions are not measurements, and the
modelled frequency/power are not a regulatory approval.

## Troubleshooting

- **Docker engine unavailable:** start Docker Desktop and select Linux containers.
- **Container `Meshtastic` exists:** exit the old simulator or run `stop-mesh.ps1`.
- **Port 4404–4406 in use:** stop the previous simulator/process; preflight fails
  rather than connecting to an unknown service.
- **Python 3.12 missing:** install it, then verify `py -3.12 --version`.
- **Gateway/sender module missing:** merge Person A and B, recreate
  `hardware/.venv`, and rerun the editable installs.
- **No delivery immediately after startup:** wait for all node daemons to finish
  exchanging NodeInfo before sending, and verify gateway=4406/sender=4404.
- **No deterministic loss:** collision observation does not guarantee a loss;
  never claim one unless a run records it.

## Future physical acceptance checklist and documentation-only BOM

No purchase is required for this hackathon. A future physical build would need
three mutually compatible Meshtastic-supported LoRa boards, three region-correct
antennas/connectors, safe USB power/data cables, power supplies or protected
batteries, enclosures, and one host/phone connection for sender and gateway
roles. Exact part numbers must be chosen only after regional radio requirements
and supported firmware targets are reviewed.

Before any “hardware proven” claim, test: firmware flashing and rollback;
phone-to-radio BLE/USB transport; three-node signed-report delivery with a
required physical relay; corruption/loss/outage/recovery; measured current and
battery life; antenna matching and safe connector handling; thermal/enclosure
behaviour; measured range in permitted locations; backend idempotency and
signature preservation; and current Bangladesh spectrum, power, licensing, and
deployment requirements with the relevant authority.
