#!/usr/bin/env python3
"""Summarize Kalman versus causal trailing-20ms errors from replay NPZ files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--tracker", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def robust_line(time_s: np.ndarray, cfo_hz: np.ndarray) -> tuple[float, np.ndarray]:
    reference = float(np.median(time_s))
    design = np.column_stack((np.ones(len(time_s)), time_s - reference))
    coefficients = np.linalg.lstsq(design, cfo_hz, rcond=None)[0]
    for _ in range(8):
        residual = cfo_hz - design @ coefficients
        scale = max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            15.0,
        )
        standardized = np.abs(residual) / scale
        weights = np.ones(len(residual))
        mask = standardized > 1.5
        weights[mask] = 1.5 / standardized[mask]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(
            design * root[:, None],
            cfo_hz * root,
            rcond=None,
        )[0]
        if np.max(np.abs(updated - coefficients)) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    return reference, coefficients


def evaluate_npz(path: Path) -> dict[str, Any]:
    """Evaluate fixed even-lane windows without pooling recording seconds."""

    with np.load(path) as source:
        required = {
            "window_index",
            "window_raw_disjoint",
            "absolute_time_s",
            "absolute_cfo_measurement_hz",
            "measurement_supported",
            "frequency_innovation_hz",
        }
        missing = required - set(source.files)
        if missing:
            raise ValueError(f"{path}: missing NPZ arrays {sorted(missing)}")
        windows = []
        for index in sorted(int(value) for value in np.unique(source["window_index"])):
            mask = source["window_index"] == index
            if not bool(source["window_raw_disjoint"][mask][0]):
                continue
            windows.append(
                (
                    np.asarray(source["absolute_time_s"][mask], dtype=float),
                    np.asarray(source["absolute_cfo_measurement_hz"][mask], dtype=float),
                    np.asarray(source["measurement_supported"][mask], dtype=bool),
                    np.asarray(source["frequency_innovation_hz"][mask], dtype=float),
                )
            )
    pairs: list[tuple[float, float, float]] = []
    supported_count = 0
    for time_s, cfo_hz, supported, innovation_hz in windows:
        if not (
            np.all(np.isfinite(time_s))
            and np.all(np.isfinite(cfo_hz))
            and np.all(np.isfinite(innovation_hz))
        ):
            raise ValueError(f"{path}: non-finite frame data")
        supported_offsets = np.flatnonzero(supported)
        supported_count += len(supported_offsets)
        line_error: dict[int, float] = {}
        for position, offset in enumerate(supported_offsets):
            prior = supported_offsets[:position]
            prior = prior[time_s[prior] >= time_s[offset] - 0.020]
            if len(prior) < 6:
                continue
            reference, coefficients = robust_line(time_s[prior], cfo_hz[prior])
            predicted = float(coefficients[0] + coefficients[1] * (time_s[offset] - reference))
            line_error[int(offset)] = float(cfo_hz[offset] - predicted)
        for offset in supported_offsets[12:]:
            offset = int(offset)
            if offset in line_error:
                pairs.append(
                    (float(time_s[offset]), float(innovation_hz[offset]), line_error[offset])
                )
    blocks: dict[int, list[tuple[float, float]]] = {}
    for time_s, kalman_error, line_error in pairs:
        blocks.setdefault(math.floor(time_s), []).append((kalman_error, line_error))
    if not blocks:
        return {
            "status": "not_estimable",
            "raw_disjoint_window_count": len(windows),
            "supported_frame_count": supported_count,
            "common_frame_count": 0,
            "reason": "no post-bootstrap frames share a causal trailing-20ms prediction",
        }
    kalman_rms = math.sqrt(
        float(np.mean([np.mean([row[0] ** 2 for row in blocks[key]]) for key in sorted(blocks)]))
    )
    line_rms = math.sqrt(
        float(np.mean([np.mean([row[1] ** 2 for row in blocks[key]]) for key in sorted(blocks)]))
    )
    return {
        "status": "estimable",
        "raw_disjoint_window_count": len(windows),
        "supported_frame_count": supported_count,
        "common_frame_count": len(pairs),
        "recording_anchored_one_second_block_count": len(blocks),
        "kalman_block_equal_rms_hz": kalman_rms,
        "trailing_20ms_block_equal_rms_hz": line_rms,
        "kalman_to_trailing_20ms_rms_ratio": kalman_rms / line_rms,
        "kalman_fractional_improvement": 1.0 - kalman_rms / line_rms,
        "line_weighting": "equal weight with Huber residual reweighting",
    }


def common_required_value(documents: list[dict[str, Any]], key: str) -> Any:
    values = [document.get(key) for document in documents]
    if any(value is None for value in values):
        raise ValueError(f"source summaries do not all declare {key}")
    if any(value != values[0] for value in values[1:]):
        raise ValueError(f"source summaries disagree on {key}")
    return values[0]


def common_optional_value(documents: list[dict[str, Any]], key: str) -> Any | None:
    values = [document.get(key) for document in documents]
    if all(value is None for value in values):
        return None
    return common_required_value(documents, key)


def phase_window_counts(summary: dict[str, Any]) -> dict[str, int]:
    """Return explicit phase-test denominators after validating source coverage."""

    selected = int(summary["selected_window_count"])
    exact = len(summary["exact_windows"])
    rolled = len(summary["rolled_windows"])
    if exact != selected or rolled != selected:
        raise ValueError(
            f"{summary['label']}: phase replay coverage does not match selected windows"
        )
    return {
        "scheduled_window_count": int(summary["window_count"]),
        "selected_window_count": selected,
        "scheduled_raw_disjoint_window_count": int(summary["raw_disjoint_window_count"]),
        "exact_phase_qualification_window_count": exact,
        "rolled_phase_qualification_window_count": rolled,
    }


def main() -> None:
    arguments = _arguments()
    summaries = sorted(arguments.source_root.glob("*filter-benchmark-summary.json"))
    if not summaries:
        raise ValueError("source root contains no filter benchmark summaries")
    rows = []
    summary_documents = []
    for summary_path in summaries:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_documents.append(summary)
        npz_path = summary_path.with_name(summary_path.name.replace("-summary.json", ".npz"))
        metric = evaluate_npz(npz_path)
        metric.update(
            {
                "label": summary["label"],
                "session_id": summary["session_id"],
                "run_id": summary["run_id"],
                "edge": summary["edge"],
                "npz_path": str(npz_path),
                "npz_sha256": _sha256(npz_path),
                "source_summary_path": str(summary_path),
                "source_summary_sha256": _sha256(summary_path),
                "seed_sha256": summary["seed_sha256"],
                "replay_runtime_s": summary["runtime_s"],
                "exact_qualified_window_count": summary["exact"]["qualified_count"],
                "rolled_qualified_window_count": summary["rolled"]["qualified_count"],
                "rolled_supported_frame_count": summary["rolled"]["supported_frames"],
                **phase_window_counts(summary),
            }
        )
        rows.append(metric)
    estimable = [row for row in rows if row["status"] == "estimable"]
    ratios = [float(row["kalman_to_trailing_20ms_rms_ratio"]) for row in estimable]
    evidence = {
        "schema": "org.leo.research.pnt-kalman-npz-same-mask/v1",
        "tracker": arguments.tracker,
        "source_root": str(arguments.source_root),
        "replay_source_inventory_sha256": common_optional_value(
            summary_documents,
            "replay_source_inventory_sha256",
        ),
        "pnt_source_sha256": common_required_value(
            summary_documents,
            "pnt_source_sha256",
        ),
        "dwells": rows,
        "aggregate": {
            "dwell_count": len(rows),
            "estimable_dwell_count": len(estimable),
            "not_estimable_dwell_count": len(rows) - len(estimable),
            "equal_dwell_geometric_mean_kalman_to_20ms_ratio": (
                math.exp(float(np.mean(np.log(ratios)))) if ratios else None
            ),
            "kalman_better_dwell_count": sum(value < 1.0 for value in ratios),
            "selected_window_count": sum(row["selected_window_count"] for row in rows),
            "exact_phase_qualification_window_count": sum(
                row["exact_phase_qualification_window_count"] for row in rows
            ),
            "rolled_phase_qualification_window_count": sum(
                row["rolled_phase_qualification_window_count"] for row in rows
            ),
            "exact_qualified_window_count": sum(
                row["exact_qualified_window_count"] for row in rows
            ),
            "rolled_qualified_window_count": sum(
                row["rolled_qualified_window_count"] for row in rows
            ),
            "inference_unit": "dwell",
            "frame_pooling_across_dwells": False,
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence["aggregate"], indent=2))


if __name__ == "__main__":
    main()
