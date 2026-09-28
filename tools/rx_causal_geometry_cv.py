"""Refit within-geometry models under a fixed causal frequency reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.rx_causal_geometry import attach_causal_frequency
from tools.rx_geometry_temporal_transfer import _calibration_record, _prepare_control, score_lanes
from tools.rx_joint_geometry_fit import DIMENSIONS, fit_arms
from tools.rx_within_geometry_cv import prepare_reception_lanes, within_center

ARMS = tuple(DIMENSIONS)
CHECKPOINT_SCHEMA = "rx-causal-geometry-cv-fold/v1"


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_hashes():
    directory = Path(__file__).parent
    names = (
        "rx_causal_geometry_cv.py",
        "rx_causal_geometry.py",
        "rx_causal_frequency.py",
        "rx_joint_geometry_fit.py",
        "rx_joint_geometry.py",
        "rx_empirical_signal.py",
        "rx_within_geometry_cv.py",
        "rx_geometry_temporal_transfer.py",
        "rx_geometry_fit.py",
        "rx_geometry_likelihood.py",
        "rx_geometry_frozen_score.py",
        "rx_presence_geometry.py",
        "rx_presence_filter.py",
        "rx_empirical_background.py",
        "rx_background_crossvalidation.py",
    )
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


def training_reception_document(document, held_session):
    """Copy only other-record calibration reception windows before extraction."""
    lanes = []
    for lane in document.get("lanes", []):
        if (
            lane.get("recording_split") != "calibration"
            or lane.get("lane", {}).get("session_id") == held_session
        ):
            continue
        windows = [
            window for window in lane.get("windows", []) if window.get("role") == "reception"
        ]
        if windows:
            lanes.append({**lane, "windows": windows})
    return {"schema": document.get("schema"), "lanes": lanes}


def prepare_training(document, fold):
    center = np.asarray(fold["feature_center"], dtype=float)
    scale = np.asarray(fold["feature_scale"], dtype=float)
    restricted = training_reception_document(document, fold["held_session"])
    lanes = prepare_reception_lanes(restricted, center, scale)
    from tools.rx_joint_geometry import attach_reference

    referenced = attach_reference(lanes, fold["background_model"], 500.0, calibration_only=True)
    centered = within_center(referenced)
    causal, diagnostics = attach_causal_frequency(centered, sigma_hz=500.0)
    return causal, diagnostics


def _prepared_control(record, fold, control=None):
    center = np.asarray(fold["feature_center"], dtype=float)
    scale = np.asarray(fold["feature_scale"], dtype=float)
    lanes = _prepare_control(record, fold["background_model"], center, scale, control)
    from tools.rx_geometry_temporal_transfer import within_center_from_reception

    return within_center_from_reception(lanes)


def score_fold(document, fold, fits):
    """Score one omitted record and all fixed controls without fitting."""
    record = _calibration_record(document, fold["held_session"])
    evaluations = {}
    diagnostics = None
    reference = None
    specifications = {arm: (None, arm) for arm in ARMS}
    specifications.update({"T_swap": ("swap", "T"), "T_reverse": ("reverse", "T")})
    specifications.update({f"{arm}_shift": ("shift", arm) for arm in ARMS})
    for name, (control, arm) in specifications.items():
        base = _prepared_control(record, fold, control)
        causal, current_diagnostics = attach_causal_frequency(
            base,
            sigma_hz=500.0,
            frequency_shift_fraction=0.25 if control == "shift" else 0.0,
        )
        current_reference = [lane["reference"].tolist() for lane in causal]
        if diagnostics is None:
            diagnostics, reference = current_diagnostics, current_reference
        elif current_diagnostics != diagnostics or current_reference != reference:
            raise ValueError("causal reference differs across controls")
        evaluations[name] = score_lanes(causal, fits[arm])
    return evaluations, diagnostics


def _summary(values):
    sequence = list(values.values())
    return {
        "records": values,
        "mean": float(np.mean(sequence)),
        "positive_records": sum(value > 0 for value in sequence),
        "negative_records": sum(value < 0 for value in sequence),
    }


def _validate_inputs(document, cv_results, frozen_results):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset")
    if (
        cv_results.get("schema") != "rx-within-geometry-cv/v1"
        or cv_results.get("status") != "complete"
    ):
        raise ValueError("within CV must be complete")
    if (
        frozen_results.get("schema") != "rx-causal-geometry/v1"
        or frozen_results.get("status") != "complete"
    ):
        raise ValueError("frozen causal result must be complete")
    if float(cv_results.get("sigma_hz", np.nan)) != 500.0:
        raise ValueError("within CV sigma must be 500 Hz")
    sessions = sorted(
        {
            lane["lane"]["session_id"]
            for lane in document["lanes"]
            if lane["recording_split"] == "calibration"
        }
    )
    calibration_lanes = [
        lane for lane in document["lanes"] if lane["recording_split"] == "calibration"
    ]
    if len(calibration_lanes) != 12:
        raise ValueError("expected exactly twelve calibration lanes")
    if len(cv_results.get("folds", [])) != 6 or len(frozen_results.get("folds", [])) != 6:
        raise ValueError("results must each contain exactly six raw folds")
    folds = {fold["held_session"]: fold for fold in cv_results.get("folds", [])}
    frozen = {fold["held_session"]: fold for fold in frozen_results.get("folds", [])}
    if (
        len(sessions) != 6
        or len(folds) != 6
        or len(frozen) != 6
        or sorted(folds) != sessions
        or sorted(frozen) != sessions
    ):
        raise ValueError("fold populations must match six calibration records")
    for session in sessions:
        fold = folds[session]
        if fold.get("training_sessions") != sorted(set(sessions) - {session}):
            raise ValueError("fold training membership mismatch")
        background = fold.get("background_model", {})
        if (
            background.get("schema") != "rx-empirical-background/v1"
            or background.get("mode") != "joint"
            or background.get("rows") != fold.get("training_window_count")
            or _json_hash(background) != fold.get("background_model_sha256")
        ):
            raise ValueError("fold background provenance mismatch")
    return sessions, folds, frozen


def run(
    document,
    cv_results,
    frozen_results,
    *,
    checkpoint_dir,
    experiment_seal,
    input_hashes,
):
    if not experiment_seal:
        raise ValueError("experiment_seal is required")
    sessions, folds_by_id, frozen_by_id = _validate_inputs(document, cv_results, frozen_results)
    fingerprint = {
        "experiment_seal": experiment_seal,
        "input_sha256": input_hashes,
        "source_sha256": _source_hashes(),
        "settings": {"sigma_hz": 500.0, "family": "within", "arms": list(ARMS)},
    }
    completed = []
    old_fits = {"D": {"parameters": [-2.0, 0.0, 0.0]}}
    for index, session in enumerate(sessions):
        checkpoint = checkpoint_dir / f"fold-{index}.json"
        expected_training = sorted(set(sessions) - {session})
        if checkpoint.exists():
            stored = json.loads(checkpoint.read_text())
            if (
                stored.get("schema") != CHECKPOINT_SCHEMA
                or stored.get("held_session") != session
                or stored.get("training_sessions") != expected_training
                or stored.get("fingerprint") != fingerprint
                or stored.get("fold_sha256") != _json_hash(stored.get("fold"))
            ):
                raise ValueError("checkpoint provenance mismatch")
            completed.append(stored["fold"])
            continue
        fold = folds_by_id[session]
        print(json.dumps({"fold": index, "held_session": session, "stage": "prepare"}), flush=True)
        training, training_diagnostics = prepare_training(document, fold)
        training_ids = {lane["source"]["lane"]["session_id"] for lane in training}
        if training_ids != set(expected_training):
            raise ValueError("prepared training membership mismatch")
        fit_result = fit_arms(training, old_fits)
        selected = {arm: fit_result["fits"][arm]["selected"] for arm in ARMS}
        evaluations, held_diagnostics = score_fold(document, fold, selected)
        frozen_evaluations = frozen_by_id[session]["causal"]
        if held_diagnostics != frozen_by_id[session].get("causal_frequency_diagnostics"):
            raise ValueError(f"{session} omitted causal diagnostics replay mismatch")
        current_reference = {
            window["source_window_id"]: window["reference_log_score"]
            for lane in evaluations["D"]["lanes"]
            for window in lane["windows"]
        }
        frozen_reference = {
            window["source_window_id"]: window["reference_log_score"]
            for lane in frozen_evaluations["D"]["lanes"]
            for window in lane["windows"]
        }
        if current_reference != frozen_reference:
            raise ValueError(f"{session} omitted causal per-window reference replay mismatch")
        for role in ("reception", "held_frequency"):
            reference_difference = (
                evaluations["D"]["roles"][role]["reference_log_score_per_window"]
                - frozen_evaluations["D"]["roles"][role]["reference_log_score_per_window"]
            )
            if abs(reference_difference) > 1e-12:
                raise ValueError(f"{session} {role} causal reference replay mismatch")
        frozen_comparison = {}
        for name in sorted(set(evaluations) & set(frozen_evaluations)):
            frozen_comparison[name] = {
                role: evaluations[name]["roles"][role]["full_log_score_per_window"]
                - frozen_evaluations[name]["roles"][role]["full_log_score_per_window"]
                for role in ("reception", "held_frequency")
            }
        training_window_ids = sorted(
            window["source_window_id"] for lane in training for window in lane["source"]["windows"]
        )
        fold_output = {
            "held_session": session,
            "training_sessions": expected_training,
            "training_source_window_ids": training_window_ids,
            "training_source_window_count": len(training_window_ids),
            "fits": fit_result["fits"],
            "evaluations": evaluations,
            "training_causal_diagnostics": training_diagnostics,
            "held_causal_diagnostics": held_diagnostics,
            "refit_minus_frozen_full_per_window": frozen_comparison,
        }
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with checkpoint.open("x") as stream:
            json.dump(
                {
                    "schema": CHECKPOINT_SCHEMA,
                    "held_session": session,
                    "training_sessions": expected_training,
                    "fingerprint": fingerprint,
                    "fold": fold_output,
                    "fold_sha256": _json_hash(fold_output),
                },
                stream,
                indent=2,
                allow_nan=False,
            )
        completed.append(fold_output)
    completed.sort(key=lambda fold: fold["held_session"])
    aggregates = {}
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
    for role in ("reception", "held_frequency"):
        for name in (*ARMS, "T_swap", "T_reverse", *(f"{arm}_shift" for arm in ARMS)):
            values = {
                fold["held_session"]: fold["evaluations"][name]["roles"][role][
                    "relative_log_score_per_window"
                ]
                for fold in completed
            }
            aggregates[f"{role}:{name}-causal_reference"] = _summary(values)
        for left, right in comparisons:
            values = {
                fold["held_session"]: fold["evaluations"][left]["roles"][role][
                    "relative_log_score_per_window"
                ]
                - fold["evaluations"][right]["roles"][role]["relative_log_score_per_window"]
                for fold in completed
            }
            aggregates[f"{role}:{left}-{right}"] = _summary(values)
        for name in ("D", "S", "T", "T_swap", "T_reverse", "T_shift"):
            values = {
                fold["held_session"]: fold["refit_minus_frozen_full_per_window"][name][role]
                for fold in completed
            }
            aggregates[f"{role}:refit-{name}-minus-frozen-{name}-full"] = _summary(values)
    return {
        "schema": "rx-causal-geometry-cv/v1",
        "status": "complete",
        "folds": completed,
        "aggregate_equal_record": aggregates,
        "interpretation": "Calibration-only causal-reference geometry refit; no "
        "evaluation-record use.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cv-results", type=Path, required=True)
    parser.add_argument("--frozen-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--experiment-seal", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    paths = {
        "dataset": args.dataset,
        "cv_results": args.cv_results,
        "frozen_results": args.frozen_results,
    }
    payloads = {name: path.read_bytes() for name, path in paths.items()}
    inputs = {name: json.loads(payload) for name, payload in payloads.items()}
    hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    if inputs["cv_results"].get("dataset_sha256") != hashes["dataset"]:
        raise ValueError("CV dataset hash mismatch")
    frozen_sources = inputs["frozen_results"].get("source_sha256", {})
    if (
        frozen_sources.get("dataset") != hashes["dataset"]
        or frozen_sources.get("cv_results") != hashes["cv_results"]
    ):
        raise ValueError("frozen causal provenance mismatch")
    result = run(
        inputs["dataset"],
        inputs["cv_results"],
        inputs["frozen_results"],
        checkpoint_dir=args.checkpoint_dir,
        experiment_seal=args.experiment_seal,
        input_hashes=hashes,
    )
    result["source_sha256"] = hashes
    result["experiment_seal"] = args.experiment_seal
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
