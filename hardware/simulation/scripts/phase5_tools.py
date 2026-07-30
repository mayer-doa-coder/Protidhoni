"""Validation and evidence helpers for the pinned Phase 5 simulation.

This module deliberately uses the standard library for validation. PyYAML is
imported only when converting a reviewed JSON topology into Meshtasticator's
runtime YAML format.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from uuid import UUID, uuid4

SIMULATION_ROOT = Path(__file__).resolve().parents[1]
HARDWARE_ROOT = SIMULATION_ROOT.parent
EVIDENCE_ROOT = HARDWARE_ROOT / "evidence"
PROTOCOL_ROOT = HARDWARE_ROOT / "protocol"

EXPECTED_MESHTASTICATOR_COMMIT = "17ceb8231079d87b070abc6132181e4c6b20202d"
EXPECTED_MESHTASTICD_IMAGE = (
    "meshtastic/meshtasticd:2.7.26@"
    "sha256:23e92b1331a3a471eaef0c63cbca4365ca40b3111a9781cfdbe5a5114e5773d4"
)
EXPECTED_MESHTASTIC_PYTHON = "2.7.11"
EXPECTED_PORTS = (4404, 4405, 4406, 4407)
EXPECTED_MODEM_PRESET = "SHORT_FAST"

# Pinned Meshtasticator commit defaults (lib/config.py), used only to prove
# whether the synthetic topology has the intended graph before it is launched.
MODEL_HEIGHT_M = 1.0

FORBIDDEN_EVIDENCE_KEYS = {
    "api_key",
    "authorization",
    "frame",
    "frames",
    "latitude",
    "longitude",
    "payload",
    "private_key",
    "report",
    "report_text",
    "secret",
    "signature",
    "token",
}
SAFE_ROUTE_SOURCES = {"meshtasticator-console", "daemon-log", "not-available"}
SAFE_REASSEMBLY_OUTCOMES = {
    "accepted",
    "duplicate",
    "rejected",
    "incomplete",
    "not-observed",
}
SAFE_BACKEND_OUTCOMES = {
    "accepted",
    "duplicate",
    "rejected",
    "unavailable",
    "not-reached",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ValidationError(ValueError):
    """A source or evidence artifact violates the frozen rules."""


def _reject_constant(value: str) -> NoReturn:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValidationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValidationError(f"cannot read {path}: {error}") from error
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValidationError(f"invalid UTF-8 JSON in {path}: {error}") from error


def _expect_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValidationError(f"{where} keys differ; missing={missing}, extra={extra}")


def _parse_utc(value: Any, where: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValidationError(f"{where} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValidationError(f"{where} is not a valid timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise ValidationError(f"{where} must be UTC")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path_loss_3gpp_suburban(
    distance_m: float, tx_height_m: float, rx_height_m: float, frequency_hz: float
) -> float:
    distance_m = max(distance_m, 0.001)
    return (
        (44.9 - 6.55 * math.log10(tx_height_m)) * (math.log10(distance_m) - 3.0)
        + 45.5
        + (35.46 - 1.1 * rx_height_m) * (math.log10(frequency_hz) - 6.0)
        - 13.82 * math.log10(rx_height_m)
        + 0.7 * rx_height_m
    )


def _link_margin(
    left: dict[str, Any], right: dict[str, Any], radio_model: dict[str, Any]
) -> float:
    distance = math.hypot(left["x_m"] - right["x_m"], left["y_m"] - right["y_m"])
    loss = _path_loss_3gpp_suburban(
        distance,
        left["height_m"],
        right["height_m"],
        radio_model["frequency_hz"],
    )
    gains = left["antenna_gain_dbi"] + right["antenna_gain_dbi"]
    return (
        radio_model["tx_power_dbm"]
        + gains
        - loss
        - radio_model["sensitivity_dbm"]
    )


def validate_versions() -> dict[str, Any]:
    versions = load_json(SIMULATION_ROOT / "versions.json")
    if not isinstance(versions, dict):
        raise ValidationError("simulation versions must be an object")
    if versions.get("schema_version") != 1:
        raise ValidationError("unsupported simulation versions schema")
    if (
        versions.get("meshtasticator", {}).get("commit")
        != EXPECTED_MESHTASTICATOR_COMMIT
    ):
        raise ValidationError("Meshtasticator commit differs from the frozen protocol")
    if versions.get("meshtastic_daemon", {}).get("image") != EXPECTED_MESHTASTICD_IMAGE:
        raise ValidationError("meshtastic daemon image is not digest-pinned")
    if versions.get("meshtastic_python") != EXPECTED_MESHTASTIC_PYTHON:
        raise ValidationError(
            "Meshtastic Python version differs from the frozen protocol"
        )
    radio_model = versions.get("radio_model")
    if radio_model != {
        "modem_preset": EXPECTED_MODEM_PRESET,
        "frequency_hz": 908_750_000.0,
        "tx_power_dbm": 30.0,
        "sensitivity_dbm": -121.5,
        "simulation_only": True,
    }:
        raise ValidationError("simulation radio model differs from reviewed SHORT_FAST settings")
    ports = tuple(item.get("port") for item in versions.get("tcp_nodes", []))
    if ports != EXPECTED_PORTS:
        raise ValidationError(f"simulator node ports must be {EXPECTED_PORTS}")

    protocol_versions = load_json(PROTOCOL_ROOT / "versions.json")
    if protocol_versions["meshtasticator"]["commit"] != EXPECTED_MESHTASTICATOR_COMMIT:
        raise ValidationError("protocol and simulation Meshtasticator commits differ")
    if protocol_versions["meshtastic_python"]["version"] != EXPECTED_MESHTASTIC_PYTHON:
        raise ValidationError(
            "protocol and simulation Meshtastic Python versions differ"
        )
    if protocol_versions["private_application_port"]["value"] != 256:
        raise ValidationError("protocol private application port is not 256")
    return versions


NODE_KEYS = {
    "index",
    "role",
    "x_m",
    "y_m",
    "height_m",
    "router",
    "repeater",
    "client_mute",
    "hop_limit",
    "antenna_gain_dbi",
    "neighbor_info",
}


def validate_topology(path: Path) -> dict[str, Any]:
    topology = load_json(path)
    if not isinstance(topology, dict):
        raise ValidationError(f"{path} must contain an object")
    _expect_keys(
        topology,
        {
            "schema_version",
            "topology_id",
            "description",
            "nodes",
            "expected_links",
            "required_absent_links",
        },
        path.name,
    )
    if topology["schema_version"] != 1 or not isinstance(topology["description"], str):
        raise ValidationError(f"{path} has invalid metadata")
    nodes = topology["nodes"]
    if not isinstance(nodes, list) or len(nodes) not in {3, 4}:
        raise ValidationError(f"{path} must contain three or four nodes")
    expected_indexes = tuple(range(len(nodes)))
    by_index: dict[int, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValidationError(f"{path} contains a non-object node")
        _expect_keys(node, NODE_KEYS, f"{path.name} node")
        index = node["index"]
        if type(index) is not int or index not in expected_indexes or index in by_index:
            raise ValidationError(
                f"{path} node indexes must be unique {', '.join(map(str, expected_indexes))}"
            )
        if node["role"] not in {"sender", "relay", "gateway"}:
            raise ValidationError(f"{path} contains an invalid node role")
        for key in ("x_m", "y_m", "height_m", "antenna_gain_dbi"):
            if type(node[key]) not in {int, float} or not math.isfinite(node[key]):
                raise ValidationError(f"{path} node {index} has invalid {key}")
        if node["height_m"] <= 0 or not 1 <= node["hop_limit"] <= 7:
            raise ValidationError(f"{path} node {index} has invalid height/hop limit")
        for key in ("router", "repeater", "client_mute", "neighbor_info"):
            if type(node[key]) is not bool:
                raise ValidationError(f"{path} node {index} has invalid {key}")
        by_index[index] = node
    expected_roles = ["sender"] + ["relay"] * (len(nodes) - 2) + ["gateway"]
    if [by_index[index]["role"] for index in expected_indexes] != expected_roles:
        raise ValidationError(
            f"{path} roles must be sender, one or two relays, then gateway"
        )

    def pairs(name: str) -> set[tuple[int, int]]:
        raw_pairs = topology[name]
        if not isinstance(raw_pairs, list):
            raise ValidationError(f"{path} {name} must be a list")
        output: set[tuple[int, int]] = set()
        for pair in raw_pairs:
            if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]:
                raise ValidationError(f"{path} contains an invalid {name} pair")
            normalized = tuple(sorted(pair))
            if any(
                type(item) is not int or item not in by_index for item in normalized
            ):
                raise ValidationError(f"{path} contains an unknown node in {name}")
            output.add(normalized)
        return output

    expected = pairs("expected_links")
    absent = pairs("required_absent_links")
    if expected & absent:
        raise ValidationError(f"{path} declares a link both present and absent")
    radio_model = validate_versions()["radio_model"]
    margins = {
        (left, right): _link_margin(by_index[left], by_index[right], radio_model)
        for left in expected_indexes
        for right in expected_indexes
        if left < right
    }
    for pair in expected:
        if margins[pair] < 0:
            raise ValidationError(
                f"{path} expected link {pair} has {margins[pair]:.2f} dB margin"
            )
    for pair in absent:
        if margins[pair] >= 0:
            raise ValidationError(
                f"{path} absent link {pair} has {margins[pair]:.2f} dB margin"
            )
    topology["calculated_link_margins_db"] = {
        f"{left}-{right}": round(margin, 3) for (left, right), margin in margins.items()
    }
    return topology


def load_scenarios() -> dict[str, Any]:
    manifest = load_json(SIMULATION_ROOT / "scenarios.json")
    if not isinstance(manifest, dict):
        raise ValidationError("scenario manifest must be an object")
    _expect_keys(
        manifest, {"schema_version", "fixture", "scenarios"}, "scenario manifest"
    )
    if manifest["schema_version"] != 1:
        raise ValidationError("unsupported scenario schema")
    fixture = manifest["fixture"]
    _expect_keys(fixture, {"vector_name", "message_id", "payload_sha256"}, "fixture")
    UUID(fixture["message_id"])
    if not SHA256_RE.fullmatch(fixture["payload_sha256"]):
        raise ValidationError("fixture payload hash is invalid")

    golden = load_json(PROTOCOL_ROOT / "vectors" / "golden-v1.json")
    matching = [
        item for item in golden["vectors"] if item["name"] == fixture["vector_name"]
    ]
    if len(matching) != 1:
        raise ValidationError(
            "scenario fixture does not uniquely match a golden vector"
        )
    vector = matching[0]
    if vector["report"]["message_id"] != fixture["message_id"]:
        raise ValidationError("scenario fixture message ID differs from golden vector")
    if vector["payload_sha256_hex"] != fixture["payload_sha256"]:
        raise ValidationError("scenario fixture digest differs from golden vector")

    required_ids = {
        "direct-delivery",
        "required-multi-hop",
        "duplicate-reception",
        "loss-and-application-resend",
        "relay-outage",
        "hop-limit-exhaustion",
        "recovery",
    }
    scenarios = manifest["scenarios"]
    ids = {scenario.get("id") for scenario in scenarios if isinstance(scenario, dict)}
    if ids != required_ids or len(scenarios) != len(required_ids):
        raise ValidationError("scenario matrix is incomplete or contains duplicate IDs")
    for scenario in scenarios:
        _expect_keys(
            scenario,
            {
                "id",
                "topology",
                "hop_limit",
                "operator_action",
                "expected_delivery",
                "expected_backend_outcomes",
                "minimum_hops",
            },
            f"scenario {scenario.get('id')}",
        )
        validate_topology(
            SIMULATION_ROOT / "topologies" / f"{scenario['topology']}.json"
        )
        if (
            type(scenario["hop_limit"]) is not int
            or not 1 <= scenario["hop_limit"] <= 7
        ):
            raise ValidationError(f"scenario {scenario['id']} has invalid hop limit")
        if type(scenario["expected_delivery"]) is not bool:
            raise ValidationError(
                f"scenario {scenario['id']} has invalid delivery expectation"
            )
        if not set(scenario["expected_backend_outcomes"]) <= SAFE_BACKEND_OUTCOMES:
            raise ValidationError(
                f"scenario {scenario['id']} has invalid backend expectation"
            )
    return manifest


def write_meshtasticator_yaml(topology_path: Path, output_path: Path) -> None:
    topology = validate_topology(topology_path)
    try:
        import yaml
    except ImportError as error:
        raise ValidationError(
            "PyYAML is required to prepare Meshtasticator runtime input"
        ) from error
    config: dict[int, dict[str, Any]] = {}
    for node in topology["nodes"]:
        config[node["index"]] = {
            "x": node["x_m"],
            "y": node["y_m"],
            "z": node["height_m"],
            "isRouter": node["router"],
            "isRepeater": node["repeater"],
            "isClientMute": node["client_mute"],
            "hopLimit": node["hop_limit"],
            "antennaGain": node["antenna_gain_dbi"],
            "neighborInfo": node["neighbor_info"],
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(config, sort_keys=True), encoding="utf-8", newline="\n"
    )


def _scan_forbidden_keys(value: Any, where: str = "evidence") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.casefold()
            if normalized in FORBIDDEN_EVIDENCE_KEYS or normalized.endswith("_token"):
                raise ValidationError(
                    f"{where} contains forbidden sensitive key {key!r}"
                )
            _scan_forbidden_keys(child, f"{where}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_keys(child, f"{where}[{index}]")


def _scenario_by_id(scenario_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_scenarios()
    for scenario in manifest["scenarios"]:
        if scenario["id"] == scenario_id:
            return manifest, scenario
    raise ValidationError(f"unknown scenario: {scenario_id}")


def validate_evidence(path: Path, *, require_artifacts: bool = False) -> dict[str, Any]:
    evidence = load_json(path)
    if not isinstance(evidence, dict):
        raise ValidationError(f"{path} must contain an evidence object")
    _scan_forbidden_keys(evidence)
    _expect_keys(
        evidence,
        {
            "schema_version",
            "run_id",
            "scenario_id",
            "recorded_at",
            "started_at",
            "ended_at",
            "recorder",
            "fixture_identity",
            "versions",
            "observations",
            "artifacts",
        },
        path.name,
    )
    if evidence["schema_version"] != 1 or evidence["recorder"] != "phase5_tools.py":
        raise ValidationError(f"{path} is not tool-generated Phase 5 evidence")
    try:
        UUID(evidence["run_id"])
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(f"{path} has an invalid run ID") from error
    recorded = _parse_utc(evidence["recorded_at"], "recorded_at")
    started = _parse_utc(evidence["started_at"], "started_at")
    ended = _parse_utc(evidence["ended_at"], "ended_at")
    if not started <= ended <= recorded:
        raise ValidationError(f"{path} timestamps are out of order")

    manifest, scenario = _scenario_by_id(evidence["scenario_id"])
    if evidence["fixture_identity"] != manifest["fixture"]:
        raise ValidationError(
            f"{path} fixture identity differs from the frozen manifest"
        )
    versions = validate_versions()
    expected_versions = {
        "meshtasticator_commit": versions["meshtasticator"]["commit"],
        "meshtasticd_image": versions["meshtastic_daemon"]["image"],
        "meshtastic_python": versions["meshtastic_python"],
    }
    if evidence["versions"] != expected_versions:
        raise ValidationError(f"{path} version identity differs from the frozen setup")

    observations = evidence["observations"]
    if not isinstance(observations, dict):
        raise ValidationError(f"{path} observations must be an object")
    _expect_keys(
        observations,
        {
            "delivery",
            "route_hops",
            "route_source",
            "duplicate_count",
            "latency_ms",
            "reassembly_outcome",
            "backend_outcome",
            "notes",
        },
        f"{path.name} observations",
    )
    delivery = observations["delivery"]
    if type(delivery) is not bool or delivery != scenario["expected_delivery"]:
        raise ValidationError(
            f"{path} delivery does not match the scenario expectation"
        )
    hops = observations["route_hops"]
    if hops is not None and (type(hops) is not int or hops < 0 or hops > 7):
        raise ValidationError(
            f"{path} route_hops must be null or an integer from 0 to 7"
        )
    if observations["route_source"] not in SAFE_ROUTE_SOURCES:
        raise ValidationError(f"{path} has an invalid route source")
    if hops is None and observations["route_source"] != "not-available":
        raise ValidationError(
            f"{path} route source must be not-available when hops are unknown"
        )
    minimum_hops = scenario["minimum_hops"]
    if hops is not None and minimum_hops is not None and hops < minimum_hops:
        raise ValidationError(f"{path} observed fewer hops than the topology permits")
    duplicate_count = observations["duplicate_count"]
    if type(duplicate_count) is not int or duplicate_count < 0:
        raise ValidationError(f"{path} duplicate count must be a non-negative integer")
    if scenario["id"] == "duplicate-reception" and duplicate_count < 1:
        raise ValidationError("duplicate-reception must observe at least one duplicate")
    latency = observations["latency_ms"]
    if delivery:
        if (
            type(latency) not in {int, float}
            or not math.isfinite(latency)
            or latency < 0
        ):
            raise ValidationError(
                f"{path} delivered result needs a non-negative latency"
            )
    elif latency is not None:
        raise ValidationError(f"{path} non-delivery result must use null latency")
    if observations["reassembly_outcome"] not in SAFE_REASSEMBLY_OUTCOMES:
        raise ValidationError(f"{path} has an invalid reassembly outcome")
    if observations["backend_outcome"] not in scenario["expected_backend_outcomes"]:
        raise ValidationError(f"{path} backend outcome does not match the scenario")
    notes = observations["notes"]
    if not isinstance(notes, str) or len(notes) > 500 or "=" in notes:
        raise ValidationError(
            f"{path} notes must be <=500 characters and contain no key=value data"
        )

    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, list) or (require_artifacts and not artifacts):
        raise ValidationError(f"{path} must list generated artifact hashes")
    for artifact in artifacts:
        _expect_keys(artifact, {"path", "sha256"}, f"{path.name} artifact")
        relative = PurePosixPath(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValidationError(f"{path} contains an unsafe artifact path")
        if not SHA256_RE.fullmatch(artifact["sha256"]):
            raise ValidationError(f"{path} contains an invalid artifact digest")
        local_path = EVIDENCE_ROOT.joinpath(*relative.parts)
        if not local_path.is_file() or _sha256(local_path) != artifact["sha256"]:
            raise ValidationError(
                f"{path} artifact is missing or its digest changed: {relative}"
            )
    return evidence


def _artifact_records(paths: list[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for raw in paths:
        candidate = Path(raw).resolve()
        try:
            relative = candidate.relative_to(EVIDENCE_ROOT.resolve())
        except ValueError as error:
            raise ValidationError(
                f"artifact must be inside {EVIDENCE_ROOT}: {candidate}"
            ) from error
        if not candidate.is_file():
            raise ValidationError(f"artifact does not exist: {candidate}")
        records.append({"path": relative.as_posix(), "sha256": _sha256(candidate)})
    return records


def record_evidence(args: argparse.Namespace) -> Path:
    manifest, scenario = _scenario_by_id(args.scenario)
    versions = validate_versions()
    started = _parse_utc(args.started_at, "started_at")
    ended = _parse_utc(args.ended_at, "ended_at")
    if started > ended:
        raise ValidationError("started_at must not be later than ended_at")
    recorded = datetime.now(timezone.utc)
    if ended > recorded:
        raise ValidationError("ended_at cannot be in the future")
    output = Path(args.output).resolve()
    generated_root = (EVIDENCE_ROOT / "generated").resolve()
    try:
        output.relative_to(generated_root)
    except ValueError as error:
        raise ValidationError(
            f"evidence output must be inside {generated_root}"
        ) from error
    if output.exists():
        raise ValidationError(f"refusing to overwrite existing evidence: {output}")

    data = {
        "schema_version": 1,
        "run_id": str(uuid4()),
        "scenario_id": scenario["id"],
        "recorded_at": recorded.isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        ),
        "started_at": started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "ended_at": ended.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "recorder": "phase5_tools.py",
        "fixture_identity": manifest["fixture"],
        "versions": {
            "meshtasticator_commit": versions["meshtasticator"]["commit"],
            "meshtasticd_image": versions["meshtastic_daemon"]["image"],
            "meshtastic_python": versions["meshtastic_python"],
        },
        "observations": {
            "delivery": args.delivery == "delivered",
            "route_hops": args.route_hops,
            "route_source": args.route_source,
            "duplicate_count": args.duplicate_count,
            "latency_ms": args.latency_ms,
            "reassembly_outcome": args.reassembly_outcome,
            "backend_outcome": args.backend_outcome,
            "notes": args.notes,
        },
        "artifacts": _artifact_records(args.artifact),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        validate_evidence(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return output


def validate_source() -> None:
    validate_versions()
    validate_topology(SIMULATION_ROOT / "topologies" / "direct.json")
    validate_topology(SIMULATION_ROOT / "topologies" / "relay-required.json")
    load_scenarios()
    study = load_json(SIMULATION_ROOT / "site-planner" / "study-input.json")
    if study.get("result_status") != "not-run":
        raise ValidationError(
            "source-controlled Site Planner input must remain marked not-run"
        )


def write_fixture(output_path: Path) -> None:
    manifest = load_scenarios()
    golden = load_json(PROTOCOL_ROOT / "vectors" / "golden-v1.json")
    vector = next(
        item
        for item in golden["vectors"]
        if item["name"] == manifest["fixture"]["vector_name"]
    )
    if output_path.exists():
        existing = load_json(output_path)
        if existing != vector["report"]:
            raise ValidationError(
                f"refusing to replace a different fixture: {output_path}"
            )
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(vector["report"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _geojson_positions(value: Any) -> list[tuple[float, float]]:
    positions: list[tuple[float, float]] = []
    if isinstance(value, list):
        if (
            len(value) >= 2
            and type(value[0]) in {int, float}
            and type(value[1]) in {int, float}
        ):
            positions.append((float(value[0]), float(value[1])))
        else:
            for child in value:
                positions.extend(_geojson_positions(child))
    elif isinstance(value, dict):
        for key, child in value.items():
            if key in {"coordinates", "geometry", "features"}:
                positions.extend(_geojson_positions(child))
    return positions


def _validate_site_artifacts(
    coverage_path: Path, p2p_path: Path, study: dict[str, Any]
) -> None:
    coverage = load_json(coverage_path)
    if not isinstance(coverage, dict) or coverage.get("type") not in {
        "Feature",
        "FeatureCollection",
    }:
        raise ValidationError(
            "coverage export is not a GeoJSON Feature/FeatureCollection"
        )
    positions = _geojson_positions(coverage)
    if not positions:
        raise ValidationError("coverage export contains no GeoJSON coordinates")
    transmitter = study["transmitter"]
    for longitude, latitude in positions:
        if (
            abs(longitude - transmitter["longitude"]) > 0.1
            or abs(latitude - transmitter["latitude"]) > 0.1
        ):
            raise ValidationError(
                "coverage coordinates differ from the reviewed synthetic study area"
            )

    try:
        png_header = p2p_path.read_bytes()[:24]
    except OSError as error:
        raise ValidationError(f"cannot read {p2p_path}: {error}") from error
    if (
        len(png_header) < 24
        or not png_header.startswith(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
        or int.from_bytes(png_header[16:20], "big") <= 0
        or int.from_bytes(png_header[20:24], "big") <= 0
    ):
        raise ValidationError(
            "point-to-point evidence must be a PNG screenshot with a valid IHDR"
        )


def _validate_summary(value: Any, where: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 500
        or "=" in value
    ):
        raise ValidationError(
            f"{where} must be 1..500 characters without key=value data"
        )


def validate_site_evidence(path: Path) -> dict[str, Any]:
    path = path.resolve()
    allowed_root = (EVIDENCE_ROOT / "generated" / "site-planner").resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError as error:
        raise ValidationError(
            f"Site Planner manifest must be inside {allowed_root}"
        ) from error
    if path.name != "manifest.json":
        raise ValidationError("Site Planner evidence must be named manifest.json")

    manifest = load_json(path)
    if not isinstance(manifest, dict):
        raise ValidationError(f"{path} must contain a Site Planner manifest object")
    _scan_forbidden_keys(manifest)
    _expect_keys(
        manifest,
        {
            "schema_version",
            "recorder",
            "study_id",
            "run_at",
            "captured_at",
            "planner_url",
            "browser",
            "input_sha256",
            "coordinate_classification",
            "regulatory_status",
            "observations",
            "artifacts",
            "limitations",
        },
        str(path),
    )
    if manifest["schema_version"] != 1 or manifest["recorder"] != "phase5_tools.py":
        raise ValidationError(f"{path} is not tool-generated Site Planner evidence")

    study_path = SIMULATION_ROOT / "site-planner" / "study-input.json"
    study = load_json(study_path)
    expected_values = {
        "study_id": study["study_id"],
        "planner_url": study["planner"]["official_url"],
        "input_sha256": _sha256(study_path),
        "coordinate_classification": study["coordinate_classification"],
        "regulatory_status": study["regulatory_status"],
        "limitations": study["limitations"],
    }
    for key, expected in expected_values.items():
        if manifest[key] != expected:
            raise ValidationError(f"{path} {key} differs from the reviewed study")

    run_at = _parse_utc(manifest["run_at"], "run_at")
    captured_at = _parse_utc(manifest["captured_at"], "captured_at")
    if not run_at <= captured_at <= datetime.now(timezone.utc):
        raise ValidationError(f"{path} timestamps are out of order or in the future")
    _validate_summary(manifest["browser"], "browser")

    observations = manifest["observations"]
    if not isinstance(observations, dict):
        raise ValidationError(f"{path} observations must be an object")
    _expect_keys(
        observations,
        {"coverage_summary", "point_to_point_summary"},
        f"{path} observations",
    )
    for key, value in observations.items():
        _validate_summary(value, key)

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ValidationError(f"{path} must list exactly two Site Planner artifacts")
    expected_names = {"coverage.geojson", "point-to-point.png"}
    found_names: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValidationError(f"{path} contains a non-object artifact")
        _expect_keys(artifact, {"path", "sha256"}, f"{path} artifact")
        name = artifact["path"]
        if name not in expected_names or name in found_names:
            raise ValidationError(f"{path} has missing, duplicate, or unknown artifacts")
        if not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(
            artifact["sha256"]
        ):
            raise ValidationError(f"{path} contains an invalid artifact digest")
        local_path = path.parent / name
        if not local_path.is_file() or _sha256(local_path) != artifact["sha256"]:
            raise ValidationError(f"{path} artifact is missing or changed: {name}")
        found_names.add(name)
    if found_names != expected_names:
        raise ValidationError(f"{path} does not contain the required artifacts")
    _validate_site_artifacts(
        path.parent / "coverage.geojson", path.parent / "point-to-point.png", study
    )
    return manifest


def capture_site_study(args: argparse.Namespace) -> Path:
    study_path = SIMULATION_ROOT / "site-planner" / "study-input.json"
    study = load_json(study_path)
    coverage_source = Path(args.coverage).resolve()
    p2p_source = Path(args.point_to_point).resolve()
    if coverage_source.suffix.casefold() not in {".geojson", ".json"}:
        raise ValidationError("coverage export must be GeoJSON")
    if p2p_source.suffix.casefold() != ".png":
        raise ValidationError("point-to-point evidence must use a .png extension")
    _validate_site_artifacts(coverage_source, p2p_source, study)

    run_at = _parse_utc(args.run_at, "run_at")
    if run_at > datetime.now(timezone.utc):
        raise ValidationError("Site Planner run time cannot be in the future")
    for name, value in {
        "browser": args.browser,
        "coverage_summary": args.coverage_summary,
        "point_to_point_summary": args.point_to_point_summary,
    }.items():
        _validate_summary(value, name)

    output_dir = Path(args.output_dir).resolve()
    allowed_root = (EVIDENCE_ROOT / "generated" / "site-planner").resolve()
    try:
        output_dir.relative_to(allowed_root)
    except ValueError as error:
        raise ValidationError(
            f"Site Planner output must be inside {allowed_root}"
        ) from error
    if output_dir.exists():
        raise ValidationError(
            f"refusing to overwrite Site Planner evidence: {output_dir}"
        )
    output_dir.mkdir(parents=True)
    coverage_output = output_dir / "coverage.geojson"
    p2p_output = output_dir / "point-to-point.png"
    try:
        shutil.copyfile(coverage_source, coverage_output)
        shutil.copyfile(p2p_source, p2p_output)
        manifest = {
            "schema_version": 1,
            "recorder": "phase5_tools.py",
            "study_id": study["study_id"],
            "run_at": run_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "captured_at": datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "planner_url": study["planner"]["official_url"],
            "browser": args.browser,
            "input_sha256": _sha256(study_path),
            "coordinate_classification": study["coordinate_classification"],
            "regulatory_status": study["regulatory_status"],
            "observations": {
                "coverage_summary": args.coverage_summary,
                "point_to_point_summary": args.point_to_point_summary,
            },
            "artifacts": [
                {"path": "coverage.geojson", "sha256": _sha256(coverage_output)},
                {"path": "point-to-point.png", "sha256": _sha256(p2p_output)},
            ],
            "limitations": study["limitations"],
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        validate_site_evidence(manifest_path)
        return manifest_path
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 5 simulation and evidence utilities"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-source")

    topology = subparsers.add_parser("validate-topology")
    topology.add_argument("path", type=Path)

    convert = subparsers.add_parser("write-topology-yaml")
    convert.add_argument("source", type=Path)
    convert.add_argument("output", type=Path)

    fixture = subparsers.add_parser("write-fixture")
    fixture.add_argument("output", type=Path)

    evidence = subparsers.add_parser("validate-evidence")
    evidence.add_argument("paths", nargs="+", type=Path)
    evidence.add_argument("--require-artifacts", action="store_true")

    record = subparsers.add_parser("record")
    record.add_argument("--scenario", required=True)
    record.add_argument("--started-at", required=True)
    record.add_argument("--ended-at", required=True)
    record.add_argument(
        "--delivery", choices=("delivered", "not-delivered"), required=True
    )
    record.add_argument("--route-hops", type=int)
    record.add_argument(
        "--route-source", choices=sorted(SAFE_ROUTE_SOURCES), default="not-available"
    )
    record.add_argument("--duplicate-count", type=int, required=True)
    record.add_argument("--latency-ms", type=float)
    record.add_argument(
        "--reassembly-outcome", choices=sorted(SAFE_REASSEMBLY_OUTCOMES), required=True
    )
    record.add_argument(
        "--backend-outcome", choices=sorted(SAFE_BACKEND_OUTCOMES), required=True
    )
    record.add_argument("--notes", default="")
    record.add_argument("--artifact", action="append", default=[])
    record.add_argument("--output", required=True)

    site = subparsers.add_parser("capture-site-study")
    site.add_argument("--coverage", required=True)
    site.add_argument("--point-to-point", required=True)
    site.add_argument("--run-at", required=True)
    site.add_argument("--browser", required=True)
    site.add_argument("--coverage-summary", required=True)
    site.add_argument("--point-to-point-summary", required=True)
    site.add_argument("--output-dir", required=True)

    validate_site = subparsers.add_parser("validate-site-evidence")
    validate_site.add_argument("paths", nargs="+", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-source":
            validate_source()
            print("Phase 5 simulation source is valid.")
        elif args.command == "validate-topology":
            topology = validate_topology(args.path)
            print(json.dumps(topology["calculated_link_margins_db"], sort_keys=True))
        elif args.command == "write-topology-yaml":
            write_meshtasticator_yaml(args.source, args.output)
            print(f"Wrote validated runtime topology: {args.output}")
        elif args.command == "write-fixture":
            write_fixture(args.output)
            print(f"Wrote local golden fixture: {args.output}")
        elif args.command == "validate-evidence":
            for path in args.paths:
                validate_evidence(path, require_artifacts=args.require_artifacts)
                print(f"Valid evidence: {path}")
        elif args.command == "record":
            print(f"Recorded evidence: {record_evidence(args)}")
        elif args.command == "capture-site-study":
            print(f"Captured Site Planner evidence: {capture_site_study(args)}")
        elif args.command == "validate-site-evidence":
            for path in args.paths:
                validate_site_evidence(path)
                print(f"Valid Site Planner evidence: {path}")
        else:  # pragma: no cover - argparse prevents this
            raise ValidationError(f"unknown command: {args.command}")
    except (ValidationError, KeyError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
