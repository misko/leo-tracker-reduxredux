"""Transfer frozen calibration-fold geometry models from reception to held windows."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.rx_joint_geometry import attach_reference, relative_emissions
from tools.rx_presence_filter import forward_score
from tools.rx_presence_geometry import posterior_summary, prepare_lanes

ARMS = ("D", "E", "S", "T")
ROLES = ("reception", "held_frequency")


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def within_center_from_reception(lanes):
    """Subtract each lane's reception mean from both role blocks."""
    output = []
    for lane in lanes:
        changed = {**lane, "x": lane["x"].copy()}
        reception = lane["roles"] == "reception"
        if not np.any(reception):
            raise ValueError("lane has no reception windows for within centering")
        mean = changed["x"][reception, ..., 3:8].mean(axis=0, keepdims=True)
        changed["x"][..., 3:8] -= mean
        output.append(changed)
    return output


def score_lanes(lanes, fitted):
    """Forward-score both roles in one sequence for each lane."""
    role_totals = {
        role: {"windows": 0, "relative_log_score": 0.0, "reference_log_score": 0.0}
        for role in ROLES
    }
    exports = []
    for lane in lanes:
        emission = relative_emissions(lane, np.asarray(fitted["beta"], dtype=float))
        reception = lane["roles"] == "reception"
        held = lane["roles"] == "held_frequency"
        score = forward_score(
            lane["prior"],
            emission,
            lane["times"],
            reception,
            held,
            fitted["occupancy"],
            fitted["tau_s"],
        )
        window_rows = []
        for local_index, source_index in enumerate(lane["indices"]):
            window = lane["source"]["windows"][source_index]
            role = lane["roles"][local_index]
            total = role_totals[role]
            total["windows"] += 1
            total["relative_log_score"] += float(score.window_log_scores[local_index])
            total["reference_log_score"] += float(lane["reference"][local_index])
            window_rows.append(
                {
                    "source_window_id": window["source_window_id"],
                    "role": str(role),
                    "prediction_utc_ns": window["prediction_utc_ns"],
                    "elapsed_s": float(lane["times"][local_index]),
                    "relative_log_score": float(score.window_log_scores[local_index]),
                    "reference_log_score": float(lane["reference"][local_index]),
                }
            )
        exports.append(
            {
                "lane": lane["source"]["lane"],
                "windows": window_rows,
                "reception_posterior": posterior_summary(score.reception_log_posterior),
                "held_posterior": posterior_summary(score.held_log_posterior),
                "window_presence": score.posterior_presence.tolist(),
            }
        )
    for total in role_totals.values():
        if total["windows"] == 0:
            raise ValueError("empty role population")
        total["full_log_score"] = total["relative_log_score"] + total["reference_log_score"]
        for metric in ("relative_log_score", "reference_log_score", "full_log_score"):
            total[f"{metric}_per_window"] = total[metric] / total["windows"]
    return {"roles": role_totals, "lanes": exports}


def _calibration_record(document, session_id):
    lanes = [
        copy.deepcopy(lane)
        for lane in document.get("lanes", [])
        if lane.get("recording_split") == "calibration"
        and lane.get("lane", {}).get("session_id") == session_id
    ]
    if not lanes:
        raise ValueError(f"missing calibration record {session_id}")
    return {"schema": document.get("schema"), "lanes": lanes}


def _prepare_control(document, background, center, scale, control=None):
    lanes = prepare_lanes(document, center, scale)
    return attach_reference(
        lanes,
        background,
        500.0,
        control=control,
        center=center,
        scale=scale,
    )


def _reception_relative(evaluation):
    return evaluation["roles"]["reception"]["relative_log_score"]


def _summary(values):
    sequence = list(values.values())
    return {
        "records": values,
        "mean": float(np.mean(sequence)),
        "positive_records": sum(value > 0 for value in sequence),
        "negative_records": sum(value < 0 for value in sequence),
        "zero_records": sum(value == 0 for value in sequence),
    }


def analyze(document, cv_result):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    if (
        cv_result.get("schema") != "rx-within-geometry-cv/v1"
        or cv_result.get("status") != "complete"
    ):
        raise ValueError("cross-validation result must be complete")
    if float(cv_result.get("sigma_hz", np.nan)) != 500.0:
        raise ValueError("cross-validation sigma must equal the frozen 500 Hz value")
    calibration_ids = sorted(
        {
            lane["lane"]["session_id"]
            for lane in document["lanes"]
            if lane["recording_split"] == "calibration"
        }
    )
    if len(calibration_ids) != 6:
        raise ValueError("expected six calibration recordings")
    if len(cv_result.get("folds", [])) != 6:
        raise ValueError("cross-validation result must contain exactly six folds")
    folds_by_id = {fold["held_session"]: fold for fold in cv_result["folds"]}
    if len(folds_by_id) != 6 or sorted(folds_by_id) != calibration_ids:
        raise ValueError("cross-validation folds do not match calibration recordings")
    for held_session, fold in folds_by_id.items():
        if fold.get("training_sessions") != sorted(set(calibration_ids) - {held_session}):
            raise ValueError("cross-validation fold training membership mismatch")

    folds = []
    for session_id in calibration_ids:
        frozen = folds_by_id[session_id]
        background = frozen.get("background_model", {})
        if (
            background.get("schema") != "rx-empirical-background/v1"
            or background.get("mode") != "joint"
            or background.get("rows") != frozen.get("training_window_count")
            or _json_hash(background) != frozen.get("background_model_sha256")
        ):
            raise ValueError(f"{session_id} frozen background metadata mismatch")
        center = np.asarray(frozen["feature_center"], dtype=float)
        scale = np.asarray(frozen["feature_scale"], dtype=float)
        record_document = _calibration_record(document, session_id)
        families = {}
        for family in ("absolute", "within"):
            base = _prepare_control(record_document, background, center, scale)
            if family == "within":
                base = within_center_from_reception(base)
            evaluations = {
                arm: score_lanes(base, frozen["families"][family]["fits"][arm]["selected"])
                for arm in ARMS
            }
            for control in ("swap", "reverse"):
                controlled = _prepare_control(
                    record_document,
                    background,
                    center,
                    scale,
                    control,
                )
                if family == "within":
                    controlled = within_center_from_reception(controlled)
                evaluations[f"T_{control}"] = score_lanes(
                    controlled, frozen["families"][family]["fits"]["T"]["selected"]
                )
            shifted = _prepare_control(
                record_document,
                background,
                center,
                scale,
                "shift",
            )
            if family == "within":
                shifted = within_center_from_reception(shifted)
            for arm in ARMS:
                evaluations[f"{arm}_shift"] = score_lanes(
                    shifted, frozen["families"][family]["fits"][arm]["selected"]
                )
            expected = frozen["families"][family]["scores"]
            for arm in ARMS:
                actual_reception = evaluations[arm]["roles"]["reception"]
                if actual_reception["windows"] != frozen["families"][family]["held_windows"]:
                    raise ValueError(f"{session_id} {family} {arm} reception denominator mismatch")
                difference = (
                    _reception_relative(evaluations[arm]) - expected[arm]["relative_log_score"]
                )
                if abs(difference) > 1e-8:
                    raise ValueError(f"{session_id} {family} {arm} reception replay mismatch")
                reference_difference = (
                    evaluations[arm]["roles"]["reception"]["reference_log_score"]
                    - frozen["families"][family]["reference_log_score"]
                )
                if abs(reference_difference) > 1e-8:
                    raise ValueError(f"{session_id} {family} {arm} reference replay mismatch")
                full_difference = (
                    actual_reception["full_log_score"] - expected[arm]["full_log_score"]
                )
                if abs(full_difference) > 1e-8:
                    raise ValueError(f"{session_id} {family} {arm} full-score replay mismatch")
            families[family] = {"evaluations": evaluations}
        if families["absolute"]["evaluations"]["D"] != families["within"]["evaluations"]["D"]:
            raise ValueError("absolute and within D transfer scores differ")
        if (
            families["absolute"]["evaluations"]["D_shift"]
            != families["within"]["evaluations"]["D_shift"]
        ):
            raise ValueError("absolute and within shifted-D transfer scores differ")
        folds.append({"held_session": session_id, "families": families})

    aggregate = {}
    comparisons = (
        ("E", "D"),
        ("S", "D"),
        ("S", "E"),
        ("T", "D"),
        ("T", "S"),
        ("T", "T_swap"),
        ("T", "T_reverse"),
        *((arm, f"{arm}_shift") for arm in ARMS),
    )
    for family in ("absolute", "within"):
        for role in ROLES:
            for arm in ARMS:
                values = {
                    fold["held_session"]: fold["families"][family]["evaluations"][arm]["roles"][
                        role
                    ]["relative_log_score_per_window"]
                    for fold in folds
                }
                aggregate[f"{family}_{role}_{arm}-reference"] = _summary(values)
            for left, right in comparisons:
                values = {
                    fold["held_session"]: fold["families"][family]["evaluations"][left]["roles"][
                        role
                    ]["relative_log_score_per_window"]
                    - fold["families"][family]["evaluations"][right]["roles"][role][
                        "relative_log_score_per_window"
                    ]
                    for fold in folds
                }
                aggregate[f"{family}_{role}_{left}-{right}"] = _summary(values)
        for arm in ARMS:
            values = {
                fold["held_session"]: fold["families"][family]["evaluations"][arm]["roles"][
                    "held_frequency"
                ]["relative_log_score_per_window"]
                - fold["families"][family]["evaluations"][arm]["roles"]["reception"][
                    "relative_log_score_per_window"
                ]
                for fold in folds
            }
            aggregate[f"{family}_{arm}_held-minus-reception"] = _summary(values)
        for left, right in comparisons:
            values = {}
            for fold in folds:
                evaluations = fold["families"][family]["evaluations"]
                held_contrast = (
                    evaluations[left]["roles"]["held_frequency"]["relative_log_score_per_window"]
                    - evaluations[right]["roles"]["held_frequency"]["relative_log_score_per_window"]
                )
                reception_contrast = (
                    evaluations[left]["roles"]["reception"]["relative_log_score_per_window"]
                    - evaluations[right]["roles"]["reception"]["relative_log_score_per_window"]
                )
                values[fold["held_session"]] = held_contrast - reception_contrast
            aggregate[f"{family}_{left}-{right}_held-minus-reception"] = _summary(values)
    return {
        "schema": "rx-geometry-temporal-transfer/v1",
        "status": "complete",
        "folds": folds,
        "aggregate_equal_record": aggregate,
        "interpretation": "Frozen calibration-fold temporal transfer; no fitting or "
        "evaluation-record use.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cv-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_bytes = args.dataset.read_bytes()
    result_bytes = args.cv_results.read_bytes()
    document, cv_result = json.loads(dataset_bytes), json.loads(result_bytes)
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    if cv_result.get("dataset_sha256") != dataset_hash:
        raise ValueError("cross-validation result is not bound to this dataset")
    result = analyze(document, cv_result)
    result["source_sha256"] = {
        "dataset": dataset_hash,
        "cv_results": hashlib.sha256(result_bytes).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
