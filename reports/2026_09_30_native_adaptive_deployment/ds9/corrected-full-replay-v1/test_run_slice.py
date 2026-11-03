#!/usr/bin/env python3
"""Component tests for the corrected full-replay harness."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("corrected_replay", HERE / "run_slice.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def stall_task(task) -> dict:
    ready = Path(task.output_dir) / "child.ready"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,signal,time;"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                f"open({str(ready)!r},'w').write(str(os.getpid()));"
                "time.sleep(5)"
            ),
        ]
    )
    while not ready.exists():
        time.sleep(0.001)
    child.wait()
    return {"visit": task.visit}


def fail_task(task) -> dict:
    raise ValueError(f"synthetic failure {task.visit}")


class GeometryTests(unittest.TestCase):
    def test_source_bound_lower_edge_geometry(self) -> None:
        for pilot, tuned in (
            (959_687_500, 960_000_000),
            (1_209_687_500, 1_210_000_000),
            (1_459_687_500, 1_460_000_000),
            (1_709_687_500, 1_710_000_000),
        ):
            self.assertEqual(
                MODULE.derive_geometry(
                    pilot_if_hz=pilot,
                    tuned_if_hz=tuned,
                    sample_rate_hz=7_500_000,
                    bandwidth_hz=7_500_000,
                    template_min_hz=-2_500_000,
                    template_max_hz=2_500_000,
                ),
                (-312_500.0, -800_000.0, 800_000.0),
            )

    def test_observable_band_clips_policy_without_candidate_data(self) -> None:
        self.assertEqual(
            MODULE.derive_geometry(
                pilot_if_hz=0,
                tuned_if_hz=0,
                sample_rate_hz=2_000_000,
                bandwidth_hz=2_000_000,
                template_min_hz=-750_000,
                template_max_hz=750_000,
            ),
            (0.0, -250_000.0, 250_000.0),
        )

    def test_unobservable_and_nonfinite_geometry_fail(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.derive_geometry(
                pilot_if_hz=2_000_000,
                tuned_if_hz=0,
                sample_rate_hz=2_000_000,
                bandwidth_hz=2_000_000,
                template_min_hz=-750_000,
                template_max_hz=750_000,
            )
        with self.assertRaises(ValueError):
            MODULE.derive_geometry(
                pilot_if_hz=float("nan"),
                tuned_if_hz=0,
                sample_rate_hz=2_000_000,
                bandwidth_hz=2_000_000,
                template_min_hz=-750_000,
                template_max_hz=750_000,
            )


class SelectionTests(unittest.TestCase):
    def test_all_receiver_outcomes(self) -> None:
        self.assertEqual(MODULE.classify_outcome({0: True, 1: True}), "both_active")
        self.assertEqual(MODULE.classify_outcome({0: False, 1: False}), "both_quiet")
        self.assertEqual(MODULE.classify_outcome({0: True, 1: False}), "rx0_only")
        self.assertEqual(MODULE.classify_outcome({0: False, 1: True}), "rx1_only")

    def test_frozen_selection_has_two_per_channel_outcome(self) -> None:
        selection = json.loads((HERE / "selection.json").read_text())
        counts = {}
        for item in selection["visits"]:
            key = item["channel"], item["persisted_outcome"]
            counts[key] = counts.get(key, 0) + 1
            self.assertEqual(item["edge"], "lower")
        self.assertEqual(len(selection["visits"]), 32)
        self.assertEqual(len({item["visit"] for item in selection["visits"]}), 32)
        self.assertEqual(
            counts,
            {
                (channel, outcome): 2
                for channel in range(1, 5)
                for outcome in ("both_active", "both_quiet", "rx0_only", "rx1_only")
            },
        )

    def test_full_selection_covers_recording_without_corrected_results(self) -> None:
        root = HERE.parents[3]
        selection = MODULE.build_full_selection(
            root / "reports/2026_09_30_native_adaptive_deployment/ds9/"
            "location-source-inventory/capture-manifest.json",
            root / "reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl",
        )
        self.assertEqual(len(selection), 2215)
        self.assertEqual([selection[0]["visit"], selection[-1]["visit"]], [0, 2214])
        self.assertEqual({item["channel"] for item in selection}, {1, 2, 3, 4})
        self.assertEqual({item["edge"] for item in selection}, {"lower"})
        self.assertEqual(
            {item["persisted_outcome"] for item in selection},
            {"both_active", "both_quiet", "rx0_only", "rx1_only"},
        )


class ComparatorTests(unittest.TestCase):
    @staticmethod
    def candidate(*, rank: int, status: str, perturb: float = 0.0) -> dict:
        complete = status == "complete"
        return {
            "rank": rank,
            "integer_epoch": 100 + rank,
            "acquired_cfo_hz": 20.0 + perturb,
            "integer_tracking_cfo_hz": 21.0 + perturb,
            "integer_exact_score": 0.5 + perturb,
            "integer_control_score": 0.1 + perturb,
            "integer_margin": 0.4 + perturb,
            "fractional_status": status,
            "fractional_offset": 0.25 + perturb if complete else None,
            "tracking_cfo_hz": 22.0 + perturb if complete else None,
            "exact_score": 0.6 + perturb if complete else None,
            "control_score": 0.1 + perturb if complete else None,
            "margin": 0.5 + perturb if complete else None,
        }

    def test_complete_and_unavailable_rows_compare(self) -> None:
        server = {
            0: [
                self.candidate(rank=0, status="complete"),
                self.candidate(rank=1, status="unbracketed"),
            ]
        }
        native = {
            0: [
                self.candidate(rank=0, status="complete", perturb=1e-12),
                self.candidate(rank=1, status="unbracketed", perturb=1e-12),
            ]
        }
        result = MODULE.compare_native_server(native, server)
        self.assertTrue(result["structure_equal"])
        self.assertTrue(result["within_frozen_tolerance"])

    def test_rank_status_and_tolerance_fail_closed(self) -> None:
        server = {0: [self.candidate(rank=0, status="complete")]}
        wrong_rank = {0: [self.candidate(rank=1, status="complete")]}
        wrong_status = {0: [self.candidate(rank=0, status="unbracketed")]}
        wrong_value = {0: [self.candidate(rank=0, status="complete", perturb=1e-4)]}
        self.assertFalse(MODULE.compare_native_server(wrong_rank, server)["structure_equal"])
        self.assertFalse(MODULE.compare_native_server(wrong_status, server)["structure_equal"])
        self.assertFalse(
            MODULE.compare_native_server(wrong_value, server)["within_frozen_tolerance"]
        )

    def test_nonfinite_and_gate_swap_fail_closed(self) -> None:
        server = {
            0: [
                self.candidate(rank=0, status="complete", perturb=0.0),
                self.candidate(rank=1, status="complete", perturb=-0.5),
            ]
        }
        nonfinite = {0: [dict(server[0][0], exact_score=math.nan), server[0][1]]}
        result = MODULE.compare_native_server(nonfinite, server)
        self.assertFalse(result["numeric_values_finite"])
        self.assertFalse(result["within_frozen_tolerance"])

        swapped = {
            0: [
                dict(server[0][0], margin=0.0),
                dict(server[0][1], margin=0.5),
            ]
        }
        result = MODULE.compare_native_server(swapped, server)
        self.assertEqual(result["native_passing_candidates"], 1)
        self.assertEqual(result["server_passing_candidates"], 1)
        self.assertFalse(result["all_gate_decisions_equal"])


class ResumeAndDeadlineTests(unittest.TestCase):
    @staticmethod
    def task(output_dir: str = ".") -> MODULE.Task:
        return MODULE.Task(
            visit=7,
            channel=2,
            edge="lower",
            persisted_outcome="both_quiet",
            output_dir=output_dir,
            bulk_root="/unused",
            analysis_root="/unused",
            detector="/unused",
            exact_template="/unused",
            control_template="/unused",
            task_digest="task-v1",
        )

    def test_resume_rejects_changed_raw_or_analysis_authority(self) -> None:
        task = self.task()
        authority = {
            "actual_lo_frequency_hz": 1_210_000_000,
            "channel": 2,
            "edge": "lower",
            "recording_event_sha256": "event-v1",
            "raw_sha256": "raw-v1",
            "recording_manifest_sha256": "recording-v1",
            "analysis_visit_compressed_sha256": "analysis-v1",
            "source_store": {
                "adapter": "leo.storage.adaptive_hop.AdaptiveHopIqStore",
                "root": "/unused",
                "read_only": True,
            },
        }
        previous = {
            "status": "pass",
            "task_digest": "task-v1",
            "source_authority": {
                key: value for key, value in authority.items() if key not in ("channel", "edge")
            },
        }
        self.assertTrue(MODULE.resume_receipt_matches(task, previous, authority))
        for key in (
            "recording_event_sha256",
            "raw_sha256",
            "analysis_visit_compressed_sha256",
        ):
            changed = dict(authority)
            changed[key] += "-changed"
            self.assertFalse(MODULE.resume_receipt_matches(task, previous, changed))

    def test_stalled_worker_deadline_is_hard_and_durable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                MODULE.run_tasks_bounded(
                    [self.task(directory)],
                    workers=1,
                    deadline_seconds=0.2,
                    output_dir=Path(directory),
                    runner=stall_task,
                )
            self.assertLess(time.monotonic() - started, 2.0)
            partial = json.loads((Path(directory) / "partial.json").read_text())
            self.assertEqual(partial["kind"], "deadline")
            self.assertEqual(partial["unfinished_visits"], [7])
            self.assertEqual(partial["task_digests"], ["task-v1"])
            child_pid = int((Path(directory) / "child.ready").read_text())
            for _ in range(20):
                if not Path(f"/proc/{child_pid}").exists():
                    break
                time.sleep(0.01)
            self.assertFalse(Path(f"/proc/{child_pid}").exists())

    def test_worker_failure_writes_visit_and_partial_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "synthetic failure 7"):
                MODULE.run_tasks_bounded(
                    [self.task(directory)],
                    workers=1,
                    deadline_seconds=2,
                    output_dir=Path(directory),
                    runner=fail_task,
                )
            failure = json.loads((Path(directory) / "failures" / "visit-000007.json").read_text())
            partial = json.loads((Path(directory) / "partial.json").read_text())
            self.assertEqual(failure["kind"], "worker_exception")
            self.assertEqual(partial["failed_visits"], [7])


if __name__ == "__main__":
    unittest.main()
