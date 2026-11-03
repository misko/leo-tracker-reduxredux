#!/usr/bin/env python3
"""Tests for the corrected native public C3/C4 exporter."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "corrected_public_export", HERE / "export_public_contract.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ExportTests(unittest.TestCase):
    @staticmethod
    def source(receiver: int) -> dict:
        return {
            "rate": 7_500_000,
            "anchor_counter": 100,
            "anchor_utc_ns": 1_000_000,
            "generation": 2,
            "visit": 0,
            "window_counter": 200,
            "probe_index": 0,
            "receiver": receiver,
            "channel": 1,
            "upper_edge": False,
            "actual_rf_hz": 10_710_000_000,
            "utc_bracket_width_ns": 100,
            "input_digest": "sha256:" + "b" * 64,
            "continuity_qualified": True,
        }

    @staticmethod
    def candidate(rank: int) -> dict:
        return {
            "rank": rank,
            "integer_epoch": 12,
            "fractional_status": "complete",
            "fractional_offset": 0.25,
            "tracking_cfo_hz": 123.0,
            "exact_score": 0.5,
            "control_score": 0.1,
            "margin": 0.4,
        }

    @staticmethod
    def public_event() -> dict:
        return {
            "recording_event_sha256": "event-v1",
            "valid_start_counter": 200,
            "channel": 1,
            "edge": "lower",
            "actual_rf_hz": 10_710_000_000,
            "actual_lo_frequency_hz": 960_000_000,
            "receiver_center_hz": [-312_500.0, -312_500.0],
            "residual_cfo_min_hz": -800_000.0,
            "residual_cfo_max_hz": 800_000.0,
        }

    @classmethod
    def source_globals(cls) -> dict:
        source = cls.source(0)
        return {
            key: source[key]
            for key in (
                "rate",
                "anchor_counter",
                "anchor_utc_ns",
                "generation",
                "utc_bracket_width_ns",
                "input_digest",
                "continuity_qualified",
            )
        }

    def test_projection_record_uses_only_source_and_native_candidate(self) -> None:
        source, candidate = self.source(0), self.candidate(3)
        before = MODULE.projection_record(source, "sha256:analysis", candidate)
        contaminated_receipt_fields = {
            "current_server": [{"margin": -999}],
            "persisted_vs_current_server": {"rows": ["oracle"]},
        }
        self.assertTrue(contaminated_receipt_fields)
        self.assertEqual(
            before,
            MODULE.projection_record(source, "sha256:analysis", candidate),
        )
        fields = before.split("\t")
        self.assertEqual(fields[13], "sha256:analysis")
        self.assertEqual(fields[15:17], ["3", "12"])
        self.assertEqual(fields[-1], "1")

    def test_load_sources_discards_candidate_values_and_rejects_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.jsonl"
            first = {"source": self.source(0), "candidate": {"margin": 0.5}}
            second = {"source": self.source(0), "candidate": {"margin": -10.0}}
            path.write_text("\n".join(map(json.dumps, (first, second))) + "\n")
            self.assertEqual(MODULE.load_sources(path), {(0, 0, 0): self.source(0)})
            second["source"] = dict(self.source(0), actual_rf_hz=1)
            path.write_text("\n".join(map(json.dumps, (first, second))) + "\n")
            with self.assertRaisesRegex(ValueError, "conflicting source authority"):
                MODULE.load_sources(path)

    def test_native_identity_excludes_oracle_comparison_bytes(self) -> None:
        sources = {(0, receiver, 0): self.source(receiver) for receiver in (0, 1)}
        receipt = {
            "status": "pass",
            "visit": 0,
            "task_digest": "task",
            "channel": 1,
            "edge": "lower",
            "source_authority": {
                "source_store": {"read_only": True},
                "recording_manifest_sha256": "sha256:" + "b" * 64,
                "recording_event_sha256": "event-v1",
                "actual_lo_frequency_hz": 960_000_000,
                "receiver_center_hz": [-312_500.0, -312_500.0],
                "residual_cfo_min_hz": -800_000.0,
                "residual_cfo_max_hz": 800_000.0,
            },
            "native": {
                str(receiver): [self.candidate(rank) for rank in range(8)] for receiver in (0, 1)
            },
            "current_server": {"oracle": 1},
            "persisted_vs_current_server": {"oracle": 2},
        }
        with tempfile.TemporaryDirectory() as directory:
            visits = Path(directory) / "visits"
            visits.mkdir()
            path = visits / "visit-000000.json"
            path.write_text(json.dumps(receipt))
            first_records, first = MODULE.load_native_inventory(
                Path(directory), 1, sources, {0: self.public_event()}
            )
            receipt["current_server"] = {"oracle": -999}
            receipt["persisted_vs_current_server"] = {"oracle": "changed"}
            path.write_text(json.dumps(receipt))
            second_records, second = MODULE.load_native_inventory(
                Path(directory), 1, sources, {0: self.public_event()}
            )
            self.assertEqual(first_records, second_records)
            self.assertEqual(first["native_identity_sha256"], second["native_identity_sha256"])
            self.assertNotEqual(first["receipt_bindings"], second["receipt_bindings"])

    def test_source_identity_time_and_counter_corruption_fail_closed(self) -> None:
        sources = {(0, receiver, 0): self.source(receiver) for receiver in (0, 1)}
        MODULE.validate_source_inventory(sources, 1, self.source_globals())
        swapped = dict(sources)
        swapped[0, 0, 0] = dict(swapped[0, 0, 0], receiver=1)
        with self.assertRaisesRegex(ValueError, "source identity differs"):
            MODULE.validate_source_inventory(swapped, 1)
        for field in ("anchor_utc_ns", "window_counter"):
            corrupted = dict(sources)
            corrupted[0, 1, 0] = dict(corrupted[0, 1, 0])
            corrupted[0, 1, 0][field] += 1
            with self.assertRaisesRegex(ValueError, "authority"):
                MODULE.validate_source_inventory(corrupted, 1)

        consistently_shifted = {
            key: dict(
                source,
                anchor_counter=source["anchor_counter"] + 1,
                anchor_utc_ns=source["anchor_utc_ns"] + 1,
            )
            for key, source in sources.items()
        }
        with self.assertRaisesRegex(ValueError, "differs from recording manifest"):
            MODULE.validate_source_inventory(consistently_shifted, 1, self.source_globals())

    def test_prior_success_products_are_removed_before_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in (
                "algorithm.json",
                "candidates.tsv",
                "graph-candidates.tsv",
                "tracks.tsv",
                "report.json",
            ):
                (output / name).write_text("stale pass\n")
            MODULE.prepare_output_dir(output)
            self.assertFalse(
                any(
                    (output / name).exists()
                    for name in (
                        "algorithm.json",
                        "candidates.tsv",
                        "graph-candidates.tsv",
                        "tracks.tsv",
                        "report.json",
                    )
                )
            )
            status = json.loads((output / "status.json").read_text())
            self.assertFalse(status["success_products_valid"])

    def test_graph_row_preserves_projector_17_digit_moment_lexemes(self) -> None:
        fields = [
            "candidate",
            "group",
            "1",
            "2",
            "3",
            "4",
            "5",
            "0.12345678901234567",
            "1.2345678901234567",
        ]
        row = MODULE.graph_row(fields).split("\t")
        self.assertEqual(row[-2:], fields[-2:])

    def test_real_projector_rank_identity_gate_boundary_and_incomplete(self) -> None:
        projector = HERE / "public-export-artifacts/host/leo-project"
        source = self.source(0)
        first, second = self.candidate(0), self.candidate(1)
        first["margin"] = GATE = 0.025
        second["margin"] = GATE
        first["exact_score"] = first["control_score"] + GATE
        second["exact_score"] = second["control_score"] + GATE
        incomplete = dict(self.candidate(2), fractional_status="unbracketed")
        records = [
            MODULE.projection_record(source, "sha256:" + "a" * 64, candidate)
            for candidate in (first, second, incomplete)
        ]
        result = subprocess.run(
            [str(projector)],
            input="\n".join(records) + "\n",
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        self.assertNotEqual(result[0].split("\t")[0], result[1].split("\t")[0])
        self.assertNotEqual(result[0], "unavailable")
        self.assertNotEqual(result[1], "unavailable")
        self.assertEqual(result[2], "unavailable")


if __name__ == "__main__":
    unittest.main()
