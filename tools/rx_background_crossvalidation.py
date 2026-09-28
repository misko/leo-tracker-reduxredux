"""Recording-held-out selection of an empirical observational reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from tools.rx_empirical_background import fit, log_density

MODES = ("poisson", "joint", "joint_frequency", "rate_joint", "rate_joint_frequency")


def calibration_rows(document, expected_records=6):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset")
    rows, seen = [], set()
    for lane in document["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        session_id = lane.get("lane", {}).get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("calibration lane session_id must be a nonempty string")
        period = float(lane["alias_period_hz"])
        if not math.isfinite(period) or period <= 0:
            raise ValueError("invalid alias period")
        for window in lane["windows"]:
            if window["role"] != "reception":
                continue
            window_id = window.get("source_window_id")
            if not isinstance(window_id, str) or not window_id:
                raise ValueError("source_window_id must be a nonempty string")
            if window_id in seen:
                raise ValueError("duplicate paired source window")
            seen.add(window_id)
            frequencies = [
                [
                    float(candidate["canonical_rx0_hz"]) % period / period
                    for candidate in window["observed"][rx]
                ]
                for rx in ("rx0", "rx1")
            ]
            if any(not math.isfinite(value) for values in frequencies for value in values):
                raise ValueError("invalid candidate frequency")
            rows.append(
                {
                    "session_id": session_id,
                    "window_id": window_id,
                    "period_hz": period,
                    "rate_hz": window["sample_rate_hz"],
                    "counts": [len(values) for values in frequencies],
                    "frequencies": frequencies,
                }
            )
    sessions = {row["session_id"] for row in rows}
    if len(sessions) != expected_records:
        raise ValueError(f"expected {expected_records} calibration recordings")
    return rows


def crossvalidate(rows):
    sessions = sorted({row["session_id"] for row in rows})
    folds = []
    for held_session in sessions:
        training = [row for row in rows if row["session_id"] != held_session]
        held = [row for row in rows if row["session_id"] == held_session]
        models = {mode: fit(training, mode) for mode in MODES}
        scores = {}
        for mode in MODES:
            count_mode = mode.removesuffix("_frequency")
            count_scores = [log_density(models[count_mode], row) for row in held]
            phase_scores = [log_density(models[mode], row) for row in held]
            jacobians = [-sum(row["counts"]) * math.log(row["period_hz"]) for row in held]
            full_scores = [phase + jac for phase, jac in zip(phase_scores, jacobians, strict=True)]
            count_mean = math.fsum(count_scores) / len(held)
            mean = math.fsum(full_scores) / len(held)
            scores[mode] = {
                "mean_log_density": mean,
                "count_set_mean": count_mean,
                "frequency_hz_mean": mean - count_mean,
                "window_log_density": full_scores,
            }
        folds.append(
            {
                "held_session": held_session,
                "training_sessions": sorted(set(sessions) - {held_session}),
                "training_windows": len(training),
                "held_windows": len(held),
                "held_window_ids": [row["window_id"] for row in held],
                "scores": scores,
            }
        )
    means = {
        mode: math.fsum(fold["scores"][mode]["mean_log_density"] for fold in folds) / len(folds)
        for mode in MODES
    }
    selected = max(MODES, key=lambda mode: means[mode])
    comparisons = {}
    for mode in MODES:
        differences = {
            fold["held_session"]: fold["scores"][mode]["mean_log_density"]
            - fold["scores"]["poisson"]["mean_log_density"]
            for fold in folds
        }
        comparisons[mode] = {
            "by_record": differences,
            "equal_record_mean": math.fsum(differences.values()) / len(folds),
            "positive_records": sum(value > 0 for value in differences.values()),
        }
    return {
        "schema": "rx-empirical-background-selection/v1",
        "status": "complete",
        "calibration_recordings": sessions,
        "calibration_windows": len(rows),
        "folds": folds,
        "equal_record_scores": means,
        "versus_poisson": comparisons,
        "selected_mode": selected,
        "selected_model": fit(rows, selected),
        "interpretation": (
            "Calibration-only unconditional observational reference; not physical clutter truth."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = crossvalidate(calibration_rows(json.loads(payload)))
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(
        json.dumps(
            {"selected_mode": result["selected_mode"], "versus_poisson": result["versus_poisson"]}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
