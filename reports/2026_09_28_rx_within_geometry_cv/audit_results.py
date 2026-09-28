#!/usr/bin/env python3
"""Independently audit calibration recording-held-out geometry results."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_empirical_background import fit
from tools.rx_geometry_fit import raw_features

ARMS = ("D", "E", "S", "T")
FAMILIES = ("absolute", "within")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def independent_scaler(document, held_session):
    blocks = []
    for lane in document["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        if lane["lane"]["session_id"] == held_session:
            continue
        windows = [window for window in lane["windows"] if window["role"] == "reception"]
        if not windows:
            continue
        source = {**lane, "windows": windows}
        values = raw_features(source)[0][:, :-1].reshape(-1, 8)
        blocks.append(values)
    values = np.concatenate(blocks)
    center = values.mean(axis=0)
    scale = values.std(axis=0)
    center[0], scale[0] = 0.0, 1.0
    scale[scale < 1e-12] = 1.0
    return center, scale


def audit(results, document, dataset_hash):
    if results.get("schema") != "rx-within-geometry-cv/v1":
        raise ValueError("unsupported results schema")
    if results.get("status") != "complete" or results.get("dataset_sha256") != dataset_hash:
        raise ValueError("results are incomplete or bound to another dataset")
    rows = calibration_rows(document)
    sessions = sorted({row["session_id"] for row in rows})
    if len(rows) != 1356 or len(sessions) != 6:
        raise ValueError("unexpected calibration population")
    expected_ids = {row["window_id"] for row in rows}
    if len(expected_ids) != len(rows):
        raise ValueError("source window ids are not unique")
    folds = results["folds"]
    if sorted(fold["held_session"] for fold in folds) != sessions:
        raise ValueError("fold held sessions do not partition recordings")

    values = {family: {arm: {} for arm in ARMS} for family in FAMILIES}
    fold_receipts = []
    seen_held_ids = set()
    for fold in folds:
        held = fold["held_session"]
        training_sessions = sorted(set(sessions) - {held})
        if fold["training_sessions"] != training_sessions:
            raise ValueError("training and held sessions overlap or omit a recording")
        held_rows = [row for row in rows if row["session_id"] == held]
        training_rows = [row for row in rows if row["session_id"] != held]
        held_ids = {row["window_id"] for row in held_rows}
        expected_held_order = [row["window_id"] for row in held_rows]
        expected_training_ids = sorted(row["window_id"] for row in training_rows)
        if fold["held_window_ids"] != expected_held_order:
            raise ValueError("exported held source-window membership differs from dataset")
        if fold["training_window_count"] != len(expected_training_ids):
            raise ValueError("exported training window count differs from dataset")
        if fold["training_window_ids_sha256"] != json_hash(expected_training_ids):
            raise ValueError("exported training source-window membership differs from dataset")
        if seen_held_ids & held_ids:
            raise ValueError("held source windows overlap folds")
        seen_held_ids |= held_ids
        expected_background = fit(training_rows, "joint")
        if fold["background_model"] != expected_background:
            raise ValueError("background model does not independently refit")
        if fold["background_model_sha256"] != json_hash(expected_background):
            raise ValueError("background model hash mismatch")
        if expected_background["rows"] != len(training_rows):
            raise ValueError("background training count mismatch")
        center, scale = independent_scaler(document, held)
        if not np.allclose(center, fold["feature_center"], rtol=0, atol=2e-12):
            raise ValueError("fold feature center does not independently refit")
        if not np.allclose(scale, fold["feature_scale"], rtol=0, atol=2e-12):
            raise ValueError("fold feature scale does not independently refit")

        held_windows = None
        for family in FAMILIES:
            exported = fold["families"][family]
            if exported["held_windows"] != len(held_rows):
                raise ValueError("held denominator differs from source membership")
            held_windows = exported["held_windows"]
            for arm in ARMS:
                fit_result = exported["fits"][arm]
                candidates = fit_result["candidates"]
                if not candidates or not any(candidate["success"] for candidate in candidates):
                    raise ValueError("arm has no converged optimizer start")
                for candidate in candidates:
                    expected_gain = (
                        candidate["calibration_relative_log_evidence"]
                        - candidate["map_penalty"]
                    )
                    if not math.isclose(candidate["map_gain"], expected_gain, abs_tol=1e-9):
                        raise ValueError("candidate MAP arithmetic mismatch")
                selected = fit_result["selected"]
                converged = [candidate for candidate in candidates if candidate["success"]]
                best = max(converged, key=lambda candidate: candidate["map_gain"])
                if best["map_gain"] <= 0:
                    if not selected["null_selected"] or selected["map_gain"] != 0:
                        raise ValueError("nonpositive fit did not select exact null")
                elif selected["null_selected"] or not math.isclose(
                    selected["map_gain"], best["map_gain"], abs_tol=1e-9
                ):
                    raise ValueError("fit did not select best converged MAP start")
                score = exported["scores"][arm]
                if not math.isclose(
                    score["full_log_score"],
                    exported["reference_log_score"] + score["relative_log_score"],
                    abs_tol=1e-9,
                ):
                    raise ValueError("full score additivity failed")
                if not math.isclose(
                    score["versus_reference_per_window"],
                    score["relative_log_score"] / held_windows,
                    abs_tol=1e-12,
                ):
                    raise ValueError("relative score denominator mismatch")
                if not math.isclose(
                    score["full_log_score_per_window"],
                    score["full_log_score"] / held_windows,
                    abs_tol=1e-12,
                ):
                    raise ValueError("full score denominator mismatch")
                values[family][arm][held] = score["versus_reference_per_window"]
        absolute_d = fold["families"]["absolute"]
        within_d = fold["families"]["within"]
        if absolute_d["fits"]["D"] != within_d["fits"]["D"]:
            raise ValueError("D fits differ between identical designs")
        if absolute_d["scores"]["D"] != within_d["scores"]["D"]:
            raise ValueError("D held scores differ between identical designs")
        fold_receipts.append(
            {
                "held_session": held,
                "training_windows": len(training_rows),
                "held_windows": len(held_rows),
                "background_model_sha256": fold["background_model_sha256"],
                "scaler_max_abs_error": float(
                    max(
                        np.max(np.abs(center - fold["feature_center"])),
                        np.max(np.abs(scale - fold["feature_scale"])),
                    )
                ),
            }
        )
    if seen_held_ids != expected_ids:
        raise ValueError("folds do not cover every calibration reception window exactly once")

    expected = {}
    for family in FAMILIES:
        for arm in ARMS:
            expected[f"{family}_{arm}-reference"] = values[family][arm]
        for arm in ("E", "S", "T"):
            expected[f"{family}_{arm}-{family}_D"] = {
                sid: values[family][arm][sid] - values[family]["D"][sid] for sid in sessions
            }
    for arm in ("E", "S", "T"):
        expected[f"within_{arm}-absolute_{arm}"] = {
            sid: values["within"][arm][sid] - values["absolute"][arm][sid]
            for sid in sessions
        }
    expected["within_T-within_S"] = {
        sid: values["within"]["T"][sid] - values["within"]["S"][sid] for sid in sessions
    }
    if set(results["aggregates"]) != set(expected):
        raise ValueError("aggregate grid differs from protocol")
    aggregates = {}
    for name, records in expected.items():
        exported = results["aggregates"][name]
        mean = math.fsum(records.values()) / len(records)
        if exported["records"] != records or not math.isclose(
            exported["mean"], mean, abs_tol=1e-12
        ):
            raise ValueError(f"aggregate arithmetic mismatch: {name}")
        positive = sum(value > 0 for value in records.values())
        if exported["positive_records"] != positive:
            raise ValueError(f"aggregate sign count mismatch: {name}")
        aggregates[name] = {"mean": mean, "positive_records": positive}
    for key, aggregate_name in (
        ("within_T-minus_D", "within_T-within_D"),
        ("within_T-minus_S", "within_T-within_S"),
    ):
        if results["primary"][key] != results["aggregates"][aggregate_name]:
            raise ValueError("primary result does not match aggregate")
    return {
        "schema": "rx-within-geometry-cv-audit/v1",
        "status": "pass",
        "calibration_reception_windows": len(rows),
        "folds": fold_receipts,
        "aggregates": aggregates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_hash = sha256(args.dataset)
    receipt = audit(
        json.loads(args.results.read_text()),
        json.loads(args.dataset.read_text()),
        dataset_hash,
    )
    receipt["sha256"] = {"results": sha256(args.results), "dataset": dataset_hash}
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
