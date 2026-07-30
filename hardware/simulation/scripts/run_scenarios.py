"""Run the reviewed Phase 5 matrix against Meshtasticator and the real backend.

The runner deliberately uses Meshtasticator's existing node interfaces. The
pinned daemon accepts only one TCP API client per node, so opening a second TCP
client would evict the simulator and invalidate the radio-path result.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import phase5_tools as tools

RUNTIME_ROOT = tools.SIMULATION_ROOT / ".runtime"
CHECKOUT = RUNTIME_ROOT / "Meshtasticator"
FIXTURE_PATH = RUNTIME_ROOT / "signed-report.json"
GENERATED_ROOT = tools.EVIDENCE_ROOT / "generated" / "scenarios"
FRAME_INTERVAL_SECONDS = 3.0
RADIO_WARMUP_SECONDS = 40.0
DELIVERY_TIMEOUT_SECONDS = 75.0
NON_DELIVERY_OBSERVATION_SECONDS = 25.0


class ScenarioRunError(RuntimeError):
    """A real scenario failed its reviewed expectation."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _remove_stale_container() -> None:
    result = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=^/Meshtastic$", "--format", "{{.Names}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip() == "Meshtastic":
        subprocess.run(
            ["docker", "rm", "-f", "Meshtastic"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _load_runtime() -> SimpleNamespace:
    if not CHECKOUT.is_dir() or not FIXTURE_PATH.is_file():
        raise ScenarioRunError("run setup.ps1 before the integrated scenario runner")
    os.environ.setdefault("MPLBACKEND", "Agg")
    sys.path.insert(0, str(CHECKOUT))
    from lib.interactive import InteractiveSim
    from protidhoni_lora_gateway.backend import BackendClient
    from protidhoni_lora_gateway.processor import GatewayProcessor
    from protidhoni_lora_gateway.receiver import extract_private_app_payload
    from protidhoni_lora_gateway.runtime import FrameWorker
    from protidhoni_lora_protocol.sender import build_send_plan
    from pubsub import pub

    return SimpleNamespace(
        InteractiveSim=InteractiveSim,
        pub=pub,
        BackendClient=BackendClient,
        GatewayProcessor=GatewayProcessor,
        FrameWorker=FrameWorker,
        build_send_plan=build_send_plan,
        extract_private_app_payload=extract_private_app_payload,
    )


def _wait_for_report(processor: Any, *, timeout: float) -> float | None:
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        metrics = processor.metrics
        if metrics.reports_accepted + metrics.reports_duplicate > 0:
            return (time.monotonic() - started) * 1000
        if metrics.reports_rejected > 0:
            return (time.monotonic() - started) * 1000
        time.sleep(0.25)
    return None


def _send_pass(interface: Any, plan: Any, *, hop_limit: int, indexes: list[int]) -> None:
    for offset, index in enumerate(indexes):
        interface.sendData(
            plan.frames[index],
            "^all",
            portNum=256,
            wantAck=False,
            channelIndex=0,
            hopLimit=hop_limit,
        )
        if offset + 1 < len(indexes):
            time.sleep(FRAME_INTERVAL_SECONDS)
    time.sleep(FRAME_INTERVAL_SECONDS)


def _disconnect_relay(simulator: Any) -> None:
    relay = next((node for node in simulator.nodes if node.nodeid == 1), None)
    if relay is None or relay.iface is None:
        raise ScenarioRunError("relay node 1 is not available for outage injection")
    relay.iface.localNode.exitSimulator()
    relay.iface.close()
    relay.iface = None
    simulator.nodes.remove(relay)


def _safe_metrics(metrics: Any) -> dict[str, int]:
    return {
        "packets_received": metrics.frames_received,
        "packets_rejected": metrics.frames_rejected,
        "duplicate_fragments": metrics.duplicate_fragments,
        "duplicate_messages": metrics.duplicate_messages,
        "reports_accepted": metrics.reports_accepted,
        "reports_duplicate": metrics.reports_duplicate,
        "reports_rejected": metrics.reports_rejected,
        "pending_reports": metrics.reports_deferred,
    }


def _write_artifact(
    scenario: dict[str, Any], topology: dict[str, Any], observations: dict[str, Any], metrics: Any
) -> Path:
    output = GENERATED_ROOT / f"{scenario['id']}.log"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Protidhoni Phase 5 sanitized automated run",
        f"scenario: {scenario['id']}",
        f"topology: {topology['topology_id']}",
        f"radio preset: {tools.validate_versions()['radio_model']['modem_preset']}",
        f"expected links: {len(topology['expected_links'])}",
        f"required absent links: {len(topology['required_absent_links'])}",
        f"delivery: {str(observations['delivery']).lower()}",
        f"route hops: {observations['route_hops']}",
        f"latency ms: {observations['latency_ms']}",
        f"reassembly outcome: {observations['reassembly_outcome']}",
        f"backend outcome: {observations['backend_outcome']}",
    ]
    if observations.get("first_pass_incomplete") is not None:
        lines.append(
            "first pass incomplete: "
            f"{str(observations['first_pass_incomplete']).lower()}"
        )
    lines.extend(f"{key.replace('_', ' ')}: {value}" for key, value in _safe_metrics(metrics).items())
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


def run_scenario(runtime: SimpleNamespace, scenario: dict[str, Any], backend_url: str) -> Path:
    topology_path = tools.SIMULATION_ROOT / "topologies" / f"{scenario['topology']}.json"
    topology = tools.validate_topology(topology_path)
    runtime_topology = CHECKOUT / "out" / "nodeConfig.yaml"
    tools.write_meshtasticator_yaml(topology_path, runtime_topology)
    _remove_stale_container()

    previous_directory = Path.cwd()
    simulator = backend = worker = None
    subscribed = False
    started_at = _utc_now()
    route_hops: list[int] = []
    first_send_started: float | None = None
    first_pass_incomplete: bool | None = None
    try:
        os.chdir(CHECKOUT)
        simulator = runtime.InteractiveSim(
            argparse.Namespace(
                script=False,
                docker=True,
                forward=False,
                collisions=False,
                from_file=True,
                nrNodes=0,
                verbose=False,
                program=str(CHECKOUT),
            )
        )
        time.sleep(RADIO_WARMUP_SECONDS)

        backend = runtime.BackendClient(
            base_url=backend_url,
            timeout_seconds=10.0,
            attempts=3,
            retry_delay_seconds=0.5,
        )
        processor = runtime.GatewayProcessor(backend)
        stop_event = threading.Event()
        worker = runtime.FrameWorker(processor, capacity=256, stop_event=stop_event)
        worker.start()
        gateway_port = 4403 + len(topology["nodes"])

        def on_receive(packet: object, interface: object | None = None) -> None:
            if interface is None or getattr(interface, "portNumber", None) != gateway_port:
                return
            payload = runtime.extract_private_app_payload(packet)
            if payload is None:
                return
            if isinstance(packet, dict):
                hop_start = packet.get("hopStart")
                remaining = packet.get("hopLimit")
                if type(hop_start) is int and type(remaining) is int:
                    route_hops.append(max(1, hop_start - remaining + 1))
            worker.submit(payload)

        runtime.pub.subscribe(on_receive, "meshtastic.receive")
        subscribed = True
        report = tools.load_json(FIXTURE_PATH)
        plan = runtime.build_send_plan(report)
        sender = next(node for node in simulator.nodes if node.nodeid == 0).iface

        if scenario["id"] == "relay-outage":
            _disconnect_relay(simulator)

        first_send_started = time.monotonic()
        all_indexes = list(range(plan.frame_count))
        if scenario["id"] == "loss-and-application-resend":
            missing_index = plan.frame_count // 2
            _send_pass(
                sender,
                plan,
                hop_limit=scenario["hop_limit"],
                indexes=[index for index in all_indexes if index != missing_index],
            )
            time.sleep(NON_DELIVERY_OBSERVATION_SECONDS)
            first_pass_incomplete = (
                processor.metrics.reports_accepted == 0
                and processor.metrics.reports_duplicate == 0
                and processor.metrics.reports_rejected == 0
                and processor.metrics.frames_received > 0
            )
            if not first_pass_incomplete:
                raise ScenarioRunError(
                    "loss-and-application-resend did not observe a safe incomplete first pass"
                )
            _send_pass(sender, plan, hop_limit=scenario["hop_limit"], indexes=all_indexes)
        else:
            _send_pass(sender, plan, hop_limit=scenario["hop_limit"], indexes=all_indexes)
            if scenario["id"] == "duplicate-reception":
                time.sleep(5.0)
                _send_pass(sender, plan, hop_limit=scenario["hop_limit"], indexes=all_indexes)

        latency_tail = None
        if scenario["expected_delivery"]:
            latency_tail = _wait_for_report(processor, timeout=DELIVERY_TIMEOUT_SECONDS)
        else:
            time.sleep(NON_DELIVERY_OBSERVATION_SECONDS)
        delivered = processor.metrics.reports_accepted + processor.metrics.reports_duplicate > 0
        if delivered != scenario["expected_delivery"]:
            raise ScenarioRunError(
                f"{scenario['id']} delivery={delivered}, expected={scenario['expected_delivery']}"
            )

        metrics = processor.metrics
        if metrics.reports_accepted:
            backend_outcome = "accepted"
        elif metrics.reports_duplicate:
            backend_outcome = "duplicate"
        elif metrics.reports_rejected:
            backend_outcome = "rejected"
        else:
            backend_outcome = "not-reached"
        if backend_outcome not in scenario["expected_backend_outcomes"]:
            raise ScenarioRunError(
                f"{scenario['id']} backend outcome {backend_outcome!r} was not expected"
            )
        duplicates = metrics.duplicate_fragments + metrics.duplicate_messages + metrics.reports_duplicate
        if scenario["id"] == "duplicate-reception" and duplicates < 1:
            raise ScenarioRunError("duplicate-reception did not observe a duplicate")
        observed_hops = max(route_hops) if route_hops else None
        minimum_hops = scenario["minimum_hops"]
        if delivered and minimum_hops is not None and (observed_hops or 0) < minimum_hops:
            raise ScenarioRunError(
                f"{scenario['id']} observed {observed_hops} hops; expected at least {minimum_hops}"
            )
        latency_ms = None
        if delivered and first_send_started is not None:
            latency_ms = round((time.monotonic() - first_send_started) * 1000, 3)
            if latency_tail is None:
                raise ScenarioRunError(f"{scenario['id']} delivered without a measured completion")
        observations = {
            "delivery": delivered,
            "route_hops": observed_hops,
            "route_source": "daemon-log" if observed_hops is not None else "not-available",
            "duplicate_count": duplicates,
            "latency_ms": latency_ms,
            "reassembly_outcome": (
                "accepted"
                if metrics.reports_accepted
                else "duplicate"
                if metrics.reports_duplicate
                else "incomplete"
                if metrics.frames_received
                else "not-observed"
            ),
            "backend_outcome": backend_outcome,
            "first_pass_incomplete": first_pass_incomplete,
            "notes": "Automated signed-fixture run; no report content or radio frame bytes retained.",
        }
        artifact = _write_artifact(scenario, topology, observations, metrics)
        ended_at = _utc_now()
        output = GENERATED_ROOT / f"{scenario['id']}.json"
        output.unlink(missing_ok=True)
        args = argparse.Namespace(
            scenario=scenario["id"],
            started_at=_timestamp(started_at),
            ended_at=_timestamp(ended_at),
            delivery="delivered" if delivered else "not-delivered",
            route_hops=observed_hops,
            route_source=observations["route_source"],
            duplicate_count=duplicates,
            latency_ms=latency_ms,
            reassembly_outcome=observations["reassembly_outcome"],
            backend_outcome=backend_outcome,
            notes=observations["notes"],
            artifact=[str(artifact)],
            output=str(output),
        )
        return tools.record_evidence(args)
    finally:
        if subscribed:
            runtime.pub.unsubscribe(on_receive, "meshtastic.receive")
        if worker is not None:
            worker.stop()
        if backend is not None:
            backend.close()
        if simulator is not None:
            simulator.close_nodes()
        os.chdir(previous_directory)
        _remove_stale_container()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Phase 5 Meshtasticator scenarios")
    parser.add_argument("--scenario", action="append", help="scenario ID; repeatable")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    tools.validate_source()
    manifest = tools.load_scenarios()
    requested = set(args.scenario or [item["id"] for item in manifest["scenarios"]])
    unknown = requested - {item["id"] for item in manifest["scenarios"]}
    if unknown:
        parser.error(f"unknown scenarios: {', '.join(sorted(unknown))}")
    runtime = _load_runtime()
    for scenario in manifest["scenarios"]:
        if scenario["id"] not in requested:
            continue
        path = run_scenario(runtime, scenario, args.backend_url)
        print(f"PASS {scenario['id']}: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
