#!/usr/bin/env python3
"""Audit recording-held-out empirical-background selection results."""

import argparse
import hashlib
import json
import math
from pathlib import Path

MODES = ("poisson", "joint", "joint_frequency", "rate_joint", "rate_joint_frequency")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(result: dict, dataset_sha256: str) -> dict:
    if (
        result.get("schema") != "rx-empirical-background-selection/v1"
        or result.get("status") != "complete"
    ):
        raise ValueError("result is not complete empirical-background evidence")
    if result.get("dataset_sha256") != dataset_sha256:
        raise ValueError("dataset hash mismatch")
    sessions = result["calibration_recordings"]
    folds = result["folds"]
    if len(sessions) != 6 or len(folds) != 6 or len(set(sessions)) != 6:
        raise ValueError("expected six recording-held-out folds")
    seen_windows = set()
    mode_fold_means = {mode: [] for mode in MODES}
    folds_audited = []
    for fold in folds:
        held = fold["held_session"]
        training = fold["training_sessions"]
        if held not in sessions or set(training) != set(sessions) - {held} or held in training:
            raise ValueError("fold train/test recording partition is invalid")
        window_ids = fold["held_window_ids"]
        if len(window_ids) != fold["held_windows"] or len(set(window_ids)) != len(window_ids):
            raise ValueError("fold held-window identities are invalid")
        if seen_windows.intersection(window_ids):
            raise ValueError("held window appears in more than one fold")
        seen_windows.update(window_ids)
        audited_scores = {}
        if set(fold["scores"]) != set(MODES):
            raise ValueError("fold modes differ from frozen design")
        for mode in MODES:
            score = fold["scores"][mode]
            values = score["window_log_density"]
            if len(values) != fold["held_windows"]:
                raise ValueError("window score count differs from fold denominator")
            mean = math.fsum(values) / len(values)
            if not math.isclose(mean, score["mean_log_density"], abs_tol=1e-12):
                raise ValueError("fold window scores do not reproduce mean")
            if not math.isclose(
                score["count_set_mean"] + score["frequency_hz_mean"], mean, abs_tol=1e-12
            ):
                raise ValueError("count/frequency decomposition is not additive")
            mode_fold_means[mode].append(mean)
            audited_scores[mode] = {
                "mean_log_density": mean,
                "count_set_mean": score["count_set_mean"],
                "frequency_hz_mean": score["frequency_hz_mean"],
            }
        folds_audited.append(
            {
                "held_session": held,
                "training_sessions": training,
                "training_windows": fold["training_windows"],
                "held_windows": fold["held_windows"],
                "scores": audited_scores,
            }
        )
    if len(seen_windows) != result["calibration_windows"] or len(seen_windows) != 1356:
        raise ValueError("fold windows do not exactly cover 1,356 calibration rows")
    means = {mode: math.fsum(values) / 6 for mode, values in mode_fold_means.items()}
    for mode in MODES:
        if not math.isclose(means[mode], result["equal_record_scores"][mode], abs_tol=1e-12):
            raise ValueError("equal-record mode mean does not recompute")
    selected = max(MODES, key=lambda mode: means[mode])
    if selected != result["selected_mode"]:
        raise ValueError("selected mode is not the ordered-tie maximum")
    comparisons = {}
    for mode in MODES:
        values = {
            fold["held_session"]: fold["scores"][mode]["mean_log_density"]
            - fold["scores"]["poisson"]["mean_log_density"]
            for fold in folds
        }
        stored = result["versus_poisson"][mode]
        mean = math.fsum(values.values()) / 6
        positive = sum(value > 0 for value in values.values())
        if (
            values != stored["by_record"]
            or not math.isclose(mean, stored["equal_record_mean"], abs_tol=1e-12)
            or positive != stored["positive_records"]
        ):
            raise ValueError("versus-Poisson comparison does not recompute")
        comparisons[mode] = {
            "by_record": values,
            "equal_record_mean": mean,
            "positive_records": positive,
        }
    model = result["selected_model"]
    if model.get("schema") != "rx-empirical-background/v1" or model.get("mode") != selected:
        raise ValueError("selected model identity is invalid")
    if model.get("rows") != 1356:
        raise ValueError("selected model was not fit on all 1,356 rows")
    return {
        "schema": "rx-empirical-background-result-audit/v1",
        "status": "pass",
        "dataset_sha256": dataset_sha256,
        "calibration_recordings": sessions,
        "calibration_windows": len(seen_windows),
        "folds": folds_audited,
        "equal_record_scores": means,
        "selected_mode": selected,
        "selected_model_rows": model["rows"],
        "versus_poisson": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audited = audit(json.loads(args.results.read_text()), sha256(args.dataset))
    audited["results_sha256"] = sha256(args.results)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(audited, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
