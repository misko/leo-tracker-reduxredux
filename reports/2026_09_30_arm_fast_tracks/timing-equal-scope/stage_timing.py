#!/usr/bin/env python3
"""Time maintained Python lane reconstruction without changing its result."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

import leo.analysis.persistent_hop_trajectory as trajectory
from leo.storage.adaptive_hop import AdaptiveHopIqStore


SESSION = "scan-fw-f363c7f29141d0b1"
MANIFEST = "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
FROZEN_RESULT_SHA256 = "08449328b987c2151bff11ee5bd6ae9ab844b720f912264d5fc77a5f6db9f1ef"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(payload)
    os.replace(temporary, path)


def load_baseline_module(path: Path):
    spec = importlib.util.spec_from_file_location("leo_fast_track_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load baseline exporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--baseline-exporter", type=Path, required=True)
    parser.add_argument("--frozen-result", type=Path, required=True)
    parser.add_argument("--arm-tracklet-timing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions != 3:
        raise ValueError("this receipt requires exactly three repetitions")
    if sha256_file(args.frozen_result) != FROZEN_RESULT_SHA256:
        raise ValueError("frozen trajectory result differs")

    baseline = load_baseline_module(args.baseline_exporter)
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        published = store.inspect(SESSION)
        if published.manifest_sha256 != MANIFEST:
            raise ValueError("recording manifest differs")
        candidates, analysis_digest = baseline.server_projection(args.server, published)
    finally:
        store.close()
    if len(candidates) != 10_066:
        raise ValueError("projected candidate count differs")

    original = trajectory._lane_tracklets
    active_calls: list[dict[str, object]] | None = None

    def measured_lane(rows, config):
        nonlocal active_calls
        if active_calls is None or not rows:
            raise RuntimeError("lane timing wrapper used outside a measured call")
        started = time.perf_counter()
        result = original(rows, config)
        elapsed = time.perf_counter() - started
        channel, edge, receiver, actual_rf_hz = rows[0].lane_key
        active_calls.append(
            {
                "channel": channel,
                "edge": edge.value,
                "receiver_id": receiver,
                "actual_rf_hz": actual_rf_hz,
                "input_candidate_count": len(rows),
                "output_tracklet_count": len(result),
                "elapsed_s": elapsed,
            }
        )
        return result

    trajectory._lane_tracklets = measured_lane
    repetitions = []
    try:
        for index in range(args.repetitions):
            active_calls = []
            started = time.perf_counter()
            result = trajectory.reconstruct_persistent_hop_trajectories(
                candidates,
                config=trajectory.PersistentHopTrajectoryConfig(),
            )
            total = time.perf_counter() - started
            calls = active_calls
            active_calls = None
            if len(calls) != 8:
                raise ValueError("lane call count differs")
            payload = (
                json.dumps(
                    baseline.json_value(result), indent=2, sort_keys=True, allow_nan=False
                )
                + "\n"
            ).encode()
            result_sha256 = sha256_bytes(payload)
            if result_sha256 != FROZEN_RESULT_SHA256:
                raise ValueError("timed trajectory result differs")
            lane_sum = sum(float(item["elapsed_s"]) for item in calls)
            repetitions.append(
                {
                    "repetition": index + 1,
                    "total_reconstruction_s": total,
                    "lane_reconstruction_sum_s": lane_sum,
                    "non_lane_reconstruction_s": total - lane_sum,
                    "lane_fraction": lane_sum / total,
                    "lane_calls": calls,
                    "result_sha256": result_sha256,
                    "tracklet_count": len(result.tracklets),
                    "physical_group_count": len(result.physical_groups),
                    "hypothesis_count": len(result.hypotheses),
                }
            )
    finally:
        trajectory._lane_tracklets = original

    lane_values = [float(item["lane_reconstruction_sum_s"]) for item in repetitions]
    total_values = [float(item["total_reconstruction_s"]) for item in repetitions]
    non_lane_values = [float(item["non_lane_reconstruction_s"]) for item in repetitions]
    arm_lines = [json.loads(line) for line in args.arm_tracklet_timing.read_text().splitlines()]
    if len(arm_lines) < 1 or not isinstance(arm_lines[0].get("reconstruct_s"), (int, float)):
        raise ValueError("ARM tracklet timing is invalid")
    arm_tracklet_s = float(arm_lines[0]["reconstruct_s"])
    if not arm_tracklet_s > 0.0:
        raise ValueError("ARM tracklet timing is invalid")
    report = {
        "schema": "leo-arm-fast-track-equal-scope-timing/v1",
        "scope": (
            "Three unprofiled perf_counter measurements of the eight maintained Python "
            "_lane_tracklets calls. Projection/store access occurs before timing. Total "
            "reconstruction also includes hypothesis, physical-group, and episode-graph output."
        ),
        "warning": (
            "Lane time is comparable in product scope to a native tracklet-only result. "
            "The complete Python total is not, because it additionally returns 16 bounded "
            "hypotheses and their graphs. Host and ARM hardware timings remain different-platform "
            "measurements."
        ),
        "inputs": {
            "session_id": SESSION,
            "recording_manifest_sha256": MANIFEST,
            "analysis_digest": analysis_digest,
            "candidate_count": len(candidates),
            "baseline_exporter_sha256": sha256_file(args.baseline_exporter),
            "stage_timing_py_sha256": sha256_file(Path(__file__)),
            "frozen_result_sha256": sha256_file(args.frozen_result),
            "persistent_hop_trajectory_py_sha256": sha256_file(Path(trajectory.__file__)),
            "server_summary_sha256": sha256_file(args.server / "summary.json"),
            "arm_tracklet_timing_sha256": sha256_file(args.arm_tracklet_timing),
        },
        "measurement": {
            "clock": "time.perf_counter",
            "repetitions": args.repetitions,
            "process_environment": {
                "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
                "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS"),
            },
            "lane_reconstruction_s": {
                "minimum": min(lane_values),
                "median": sorted(lane_values)[1],
                "maximum": max(lane_values),
            },
            "total_reconstruction_s": {
                "minimum": min(total_values),
                "median": sorted(total_values)[1],
                "maximum": max(total_values),
            },
            "non_lane_reconstruction_s": {
                "minimum": min(non_lane_values),
                "median": sorted(non_lane_values)[1],
                "maximum": max(non_lane_values),
            },
        },
        "repetitions": repetitions,
        "equal_scope_cross_platform_comparison": {
            "python_host_lane_tracklet_median_s": sorted(lane_values)[1],
            "arm_native_tracklet_s": arm_tracklet_s,
            "python_host_over_arm_native_ratio": sorted(lane_values)[1] / arm_tracklet_s,
            "warning": (
                "This is equal product scope (tracklets) but different hardware and language "
                "implementations; it is not a same-host microbenchmark."
            ),
        },
        "output_identity": {
            "expected_sha256": FROZEN_RESULT_SHA256,
            "all_repetitions_equal_frozen_result": all(
                item["result_sha256"] == FROZEN_RESULT_SHA256 for item in repetitions
            ),
        },
    }
    atomic_json(args.output, report)
    print(json.dumps(report["measurement"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
