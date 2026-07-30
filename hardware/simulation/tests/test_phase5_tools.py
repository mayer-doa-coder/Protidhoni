from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import phase5_tools as tools


class Phase5SourceTests(unittest.TestCase):
    def test_all_source_files_validate(self) -> None:
        tools.validate_source()

    def test_relay_topology_requires_node_one(self) -> None:
        topology = tools.validate_topology(
            tools.SIMULATION_ROOT / "topologies" / "relay-required.json"
        )
        margins = topology["calculated_link_margins_db"]
        self.assertGreater(margins["0-1"], 0)
        self.assertGreater(margins["1-2"], 0)
        self.assertLess(margins["0-2"], 0)

    def test_two_relay_topology_requires_both_relays(self) -> None:
        topology = tools.validate_topology(
            tools.SIMULATION_ROOT / "topologies" / "two-relay-required.json"
        )
        margins = topology["calculated_link_margins_db"]
        self.assertGreater(margins["0-1"], 0)
        self.assertGreater(margins["1-2"], 0)
        self.assertGreater(margins["2-3"], 0)
        self.assertLess(margins["0-2"], 0)
        self.assertLess(margins["1-3"], 0)

    def test_scenario_matrix_is_complete(self) -> None:
        manifest = tools.load_scenarios()
        self.assertEqual(len(manifest["scenarios"]), 7)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"value": 1, "value": 2}', encoding="utf-8")
            with self.assertRaises(tools.ValidationError):
                tools.load_json(path)


class EvidenceTests(unittest.TestCase):
    def _args(self, output: Path) -> argparse.Namespace:
        now = datetime.now(timezone.utc)
        return argparse.Namespace(
            scenario="required-multi-hop",
            started_at=(now - timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
            ended_at=(now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
            delivery="delivered",
            route_hops=2,
            route_source="meshtasticator-console",
            duplicate_count=0,
            latency_ms=1000.0,
            reassembly_outcome="accepted",
            backend_outcome="accepted",
            notes="Synthetic signed fixture completed the required relay path.",
            artifact=[],
            output=str(output),
        )

    def test_recorded_evidence_round_trip(self) -> None:
        generated = tools.EVIDENCE_ROOT / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        output = generated / "unittest-evidence.json"
        output.unlink(missing_ok=True)
        try:
            tools.record_evidence(self._args(output))
            evidence = tools.validate_evidence(output)
            self.assertEqual(evidence["scenario_id"], "required-multi-hop")
        finally:
            output.unlink(missing_ok=True)

    def test_site_study_capture_hashes_unedited_artifacts(self) -> None:
        output = tools.EVIDENCE_ROOT / "generated" / "site-planner" / "unittest-site"
        shutil.rmtree(output, ignore_errors=True)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            coverage = source / "coverage.geojson"
            coverage.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [90.4125, 23.8103],
                                },
                                "properties": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            screenshot = source / "point-to-point.png"
            screenshot.write_bytes(
                b"\x89PNG\r\n\x1a\n"
                + struct.pack(">I", 13)
                + b"IHDR"
                + struct.pack(">II", 1, 1)
            )
            args = argparse.Namespace(
                coverage=str(coverage),
                point_to_point=str(screenshot),
                run_at=(datetime.now(timezone.utc) - timedelta(seconds=1))
                .isoformat()
                .replace("+00:00", "Z"),
                browser="Test browser 1",
                coverage_summary="Synthetic coverage output captured.",
                point_to_point_summary="Synthetic point to point output captured.",
                output_dir=str(output),
            )
            try:
                manifest_path = tools.capture_site_study(args)
                manifest = tools.validate_site_evidence(manifest_path)
                self.assertEqual(len(manifest["artifacts"]), 2)
                self.assertTrue((output / "coverage.geojson").is_file())
                self.assertTrue((output / "point-to-point.png").is_file())

                (output / "coverage.geojson").write_text("{}", encoding="utf-8")
                with self.assertRaises(tools.ValidationError):
                    tools.validate_site_evidence(manifest_path)
            finally:
                shutil.rmtree(output, ignore_errors=True)

    def test_sensitive_evidence_key_is_rejected(self) -> None:
        generated = tools.EVIDENCE_ROOT / "generated"
        generated.mkdir(parents=True, exist_ok=True)
        output = generated / "unittest-sensitive.json"
        output.unlink(missing_ok=True)
        try:
            tools.record_evidence(self._args(output))
            data = json.loads(output.read_text(encoding="utf-8"))
            data["observations"]["token"] = "not-allowed"
            output.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(tools.ValidationError):
                tools.validate_evidence(output)
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
