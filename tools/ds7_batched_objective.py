#!/usr/bin/env python3
"""Read-only prototype for exact cross-track batched DS7 offset profiling."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import gammaln, logsumexp

try:
    from tools import ds7_baseline_adapter as baseline

    # The existing fast kernel is also a directly executable adapter and uses
    # its script-local import name. Alias the same loaded baseline module.
    sys.modules.setdefault("ds7_baseline_adapter", baseline)
    from tools import ds7_fast_baseline_adapter as fast
except ImportError:  # Direct execution from tools/.
    import ds7_baseline_adapter as baseline
    import ds7_fast_baseline_adapter as fast


def batched_track_offsets(
    training_residuals: list[np.ndarray], max_group_rows: int = 1024
) -> tuple[list[np.ndarray], list[list[dict]]]:
    """Profile candidate rows by training width and restore exact input order."""
    if max_group_rows < 1:
        raise ValueError("max_group_rows must be positive")
    offsets: list[np.ndarray | None] = [None] * len(training_residuals)
    audits: list[list[dict] | None] = [None] * len(training_residuals)
    groups: dict[int, list[int]] = defaultdict(list)
    arrays = []
    for index, values in enumerate(training_residuals):
        array = np.asarray(values, dtype=float)
        if array.ndim != 2 or not array.shape[0] or not array.shape[1]:
            raise ValueError("each residual block must be a nonempty candidate-by-training array")
        arrays.append(array)
        groups[array.shape[1]].append(index)

    for width in sorted(groups):
        row_refs = [
            (track_index, row_index)
            for track_index in groups[width]
            for row_index in range(arrays[track_index].shape[0])
        ]
        track_offsets = {
            index: np.empty(arrays[index].shape[0], dtype=float) for index in groups[width]
        }
        track_audits = {
            index: [None] * arrays[index].shape[0] for index in groups[width]
        }
        for begin in range(0, len(row_refs), max_group_rows):
            refs = row_refs[begin : begin + max_group_rows]
            block = np.stack([arrays[track][row] for track, row in refs])
            block_offsets, block_audits = fast.fit_stationary_offsets(block)
            for (track, row), offset, audit in zip(
                refs, block_offsets, block_audits, strict=True
            ):
                track_offsets[track][row] = offset
                track_audits[track][row] = audit
        for index in groups[width]:
            offsets[index] = track_offsets[index]
            audits[index] = track_audits[index]
    return offsets, audits  # type: ignore[return-value]


class BatchedJointObjective:
    """Frozen objective with only offset-kernel scheduling changed."""

    def __init__(self, documents: list[dict], config: dict, max_group_rows: int = 1024):
        self.models = [baseline.Stationary(document, config) for document in documents]
        self.max_group_rows = max_group_rows

    def coordinates(self, x):
        return self.models[0].coordinates(x)

    def value_gradient(self, x: np.ndarray) -> tuple[float, np.ndarray]:
        items = []
        training = []
        for document_index, model in enumerate(self.models):
            local = np.asarray([x[0], x[1], x[document_index + 2]], dtype=float)
            for track in model.document["tracks"]:
                prediction, visible = model.prediction(track, local)
                residual = track["y"][None, :] - prediction
                items.append((document_index, model, local, track, prediction, visible, residual))
                training.append(residual[:, track["mask"]])

        offset_blocks, audit_blocks = batched_track_offsets(training, self.max_group_rows)
        totals = np.zeros(len(self.models), dtype=float)
        local_derivatives = [np.zeros(3, dtype=float) for _model in self.models]
        constant = gammaln(2.5) - gammaln(2.0) - 0.5 * np.log(4.0 * np.pi) - np.log(100.0)
        for item, offsets, audits in zip(items, offset_blocks, audit_blocks, strict=True):
            document_index, model, local, track, _prediction, visible, residual = item
            if not all(audit["converged"] for audit in audits):
                raise RuntimeError("offset stationarity check failed")
            z = (residual - offsets[:, None]) / 100.0
            density = constant - 2.5 * np.log1p(z * z / 4.0)
            score = density[:, track["mask"]].sum(axis=1) - 0.5 * offsets**2 / 1e12
            score = np.where(visible, score, -np.inf)
            normal = logsumexp(score)
            totals[document_index] += float(normal - math.log(track["catalogue_size"]))
            centered = residual[:, track["mask"]] - offsets[:, None]
            slope = 5.0 * centered / (40_000.0 + centered**2)
            responsibility = np.exp(score - normal)
            for axis in range(3):
                step = 1e-4 if axis < 2 else 1e-5
                plus, minus = local.copy(), local.copy()
                plus[axis] += step
                minus[axis] -= step
                if axis == 2:
                    plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                delta = (model.prediction(track, plus)[0] - model.prediction(track, minus)[0]) / (
                    plus[axis] - minus[axis]
                )
                value = float(
                    responsibility @ np.sum(slope * delta[:, track["mask"]], axis=1)
                )
                local_derivatives[document_index][axis] += value
        total = 0.0
        derivative = np.zeros_like(x, dtype=float)
        for document_index, (score, local_derivative) in enumerate(
            zip(totals, local_derivatives, strict=True)
        ):
            total += score
            derivative[:2] += local_derivative[:2]
            derivative[document_index + 2] += local_derivative[2]
        return -total, -derivative


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _points(count: int, fitted: list[float], config: dict) -> dict[str, np.ndarray]:
    position_low, position_high = config["position_bounds_km"]
    timing_low, timing_high = config["timing_bounds_s"]
    return {
        "donor": np.zeros(count + 2),
        "interior": np.r_[1.25, -0.75, np.linspace(-1.0, 1.0, count)],
        "fitted": np.asarray(fitted, dtype=float),
        "near_boundary": np.r_[
            position_high - 0.1,
            position_low + 0.1,
            np.full(count, timing_high - min(0.1, (timing_high - timing_low) / 10.0)),
        ],
    }


def benchmark(
    cases: list[dict], max_group_rows: int, deadline: float, selected_points: set[str]
) -> dict:
    rows = []
    for case in cases:
        if time.monotonic() >= deadline:
            raise TimeoutError("benchmark deadline exceeded")
        request_path = Path(case["request"])
        response_path = Path(case["response"])
        request = json.loads(request_path.read_text())
        response = json.loads(response_path.read_text())
        documents = fast.load_documents(request)
        original = baseline.JointObjective(documents, request["config"])
        batched = BatchedJointObjective(documents, request["config"], max_group_rows)
        fitted = [
            *response["diagnostics"]["east_north_km"],
            *response["diagnostics"]["timing_offsets_s"],
        ]
        for point_name, point in _points(len(documents), fitted, request["config"]).items():
            if point_name not in selected_points:
                continue
            started = time.monotonic()
            saved_profile = baseline.profile
            baseline.profile = fast.profile
            try:
                old_value, old_gradient = original.value_gradient(point)
            finally:
                baseline.profile = saved_profile
            old_seconds = time.monotonic() - started
            started = time.monotonic()
            new_value, new_gradient = batched.value_gradient(point)
            new_seconds = time.monotonic() - started
            rows.append(
                {
                    "case": case["label"],
                    "point": point_name,
                    "objective_current_fast": old_value,
                    "objective_batched": new_value,
                    "objective_absolute_difference": abs(old_value - new_value),
                    "gradient_max_absolute_difference": float(
                        np.max(np.abs(old_gradient - new_gradient))
                    ),
                    "current_fast_seconds": old_seconds,
                    "batched_seconds": new_seconds,
                }
            )
    return {"rows": rows, "maximum_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-group-rows", type=int, default=1024)
    parser.add_argument("--maximum-seconds", type=float, default=180.0)
    parser.add_argument(
        "--points", default="donor,interior,fitted,near_boundary", help="comma-separated points"
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    started = time.monotonic()
    selected_points = set(args.points.split(","))
    known_points = {"donor", "interior", "fitted", "near_boundary"}
    if not selected_points or not selected_points <= known_points:
        raise ValueError("unknown or empty benchmark point selection")
    result = benchmark(
        cases, args.max_group_rows, started + args.maximum_seconds, selected_points
    )
    rows = result["rows"]
    result.update(
        {
            "schema": "ds7-batched-objective-benchmark/v1",
            "reference_audit": "reference_pose_scores_iq_excluded",
            "max_group_rows": args.max_group_rows,
            "elapsed_seconds": time.monotonic() - started,
            "maximum_seconds": args.maximum_seconds,
            "selected_points": sorted(selected_points),
            "resource_policy": {
                "cpu_threads": 1,
                "blas_threads": 1,
                "nice": 19,
                "raw_iq": False,
            },
            "maximum_objective_absolute_difference": max(
                row["objective_absolute_difference"] for row in rows
            ),
            "maximum_gradient_absolute_difference": max(
                row["gradient_max_absolute_difference"] for row in rows
            ),
            "inputs": [
                {
                    **case,
                    "request_sha256": _sha256(Path(case["request"])),
                    "response_sha256": _sha256(Path(case["response"])),
                }
                for case in cases
            ],
            "tool_sha256": _sha256(Path(__file__)),
            "current_fast_comparator": {
                "path": str(Path(fast.__file__)),
                "sha256": _sha256(Path(fast.__file__)),
            },
        }
    )
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
