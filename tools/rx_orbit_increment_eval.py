"""Fit and score frozen geometry models using a causal orbit-increment kernel."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_causal_full_calibration import prepare_families
from tools.rx_causal_geometry import attach_causal_frequency
from tools.rx_ds8_geometry_score import _validate_model
from tools.rx_geometry_temporal_transfer import score_lanes, within_center_from_reception
from tools.rx_joint_geometry import attach_reference
from tools.rx_joint_geometry_fit import fit_arms
from tools.rx_orbit_increment import attach_orbit_increment
from tools.rx_presence_geometry import prepare_lanes

ARMS = ("D", "E", "S", "T")
ROLES = ("reception", "held_frequency")
ORBIT_SPECS = {
    "D": (None, None, 0.0, "D"),
    "E": (None, None, 0.0, "E"),
    "S": (None, None, 0.0, "S"),
    "T": (None, None, 0.0, "T"),
    "T_swap": ("swap", None, 0.0, "T"),
    "T_geometry_reverse": ("reverse", None, 0.0, "T"),
    "T_zero_motion": (None, "zero", 0.0, "T"),
    "T_reverse_motion": (None, "reverse", 0.0, "T"),
    "T_shift": (None, None, 0.25, "T"),
    "T_geometry_permute": (None, None, 0.0, "T"),
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def fit(document: dict) -> dict:
    """Fit D/E/S/T once on calibration-reception orbit-increment lanes."""
    prepared = prepare_families(document)
    sessions = sorted({row["session_id"] for row in prepared["rows"]})
    if len(sessions) != 6 or len(prepared["uniform"]) != 12:
        raise ValueError("expected six calibration recordings and twelve lanes")
    orbit, diagnostics = attach_orbit_increment(prepared["uniform"])
    fitted = fit_arms(orbit, {"D": {"parameters": [-2.0, 0.0, 0.0]}})
    window_ids = sorted(row["window_id"] for row in prepared["rows"])
    scaler = {
        "feature_center": prepared["center"].tolist(),
        "feature_scale": prepared["scale"].tolist(),
    }
    return {
        "schema": "rx-orbit-increment-fit/v1",
        "status": "complete",
        "sigma_hz": 500.0,
        "calibration_sessions": sessions,
        "training_source_window_ids": window_ids,
        "training_source_window_count": len(window_ids),
        "training_source_window_ids_sha256": _json_hash(window_ids),
        "background_model": prepared["background"],
        "background_model_sha256": _json_hash(prepared["background"]),
        **scaler,
        "feature_scaler_sha256": _json_hash(scaler),
        "fits": fitted["fits"],
        "orbit_increment_diagnostics": diagnostics,
    }


def _validate_orbit_model(model, training, training_sha256=None):
    if model.get("schema") != "rx-orbit-increment-fit/v1":
        raise ValueError("unsupported orbit model schema")
    wrapper = {**model, "schema": "rx-causal-full-calibration/v1"}
    wrapper["dataset_sha256"] = model.get("training_dataset_sha256")
    wrapper["families"] = {
        "uniform": {"fits": model.get("fits")},
        "causal": {"fits": copy.deepcopy(model.get("fits"))},
    }
    scaler = {
        "feature_center": model.get("feature_center"),
        "feature_scale": model.get("feature_scale"),
    }
    if model.get("feature_scaler_sha256") != _json_hash(scaler):
        raise ValueError("orbit model feature-scaler receipt mismatch")
    return _validate_model(wrapper, training, training_sha256)


def _evaluation_document(document):
    lanes = [
        lane for lane in document.get("lanes", []) if lane.get("recording_split") == "evaluation"
    ]
    if not lanes:
        raise ValueError("dataset has no evaluation lanes")
    return {**document, "lanes": lanes}


def _prepared(document, background, center, scale, geometry_control=None):
    lanes = prepare_lanes(document, center, scale)
    lanes = attach_reference(
        lanes, background, 500.0, control=geometry_control, center=center, scale=scale
    )
    return within_center_from_reception(lanes)


def _permute_geometry(lanes):
    output = copy.deepcopy(lanes)
    for lane in output:
        if lane["x"].shape[1] > 1:
            lane["x"][..., 3:8] = np.roll(lane["x"][..., 3:8], 1, axis=1)
    return output


def _summary(values):
    return {
        "records": values,
        "eligible_recordings": len(values),
        "equal_record_mean": math.fsum(values.values()) / len(values),
        "positive_records": sum(value > 0 for value in values.values()),
    }


def score(training, model, document, static_model, *, training_sha256=None):
    """Score evaluation recordings under orbit and static causal frozen models."""
    training_ids, background, center, scale = _validate_orbit_model(
        model, training, training_sha256
    )
    static_ids, static_background, static_center, static_scale = _validate_model(
        static_model, training, training_sha256
    )
    if training_ids != static_ids or background != static_background:
        raise ValueError("orbit and static models do not share training membership/background")
    if not np.array_equal(center, static_center) or not np.array_equal(scale, static_scale):
        raise ValueError("orbit and static models do not share the frozen scaler")
    evaluation = _evaluation_document(document)
    observed_ids = sorted({lane["lane"]["session_id"] for lane in evaluation["lanes"]})
    if len(observed_ids) != 4:
        raise ValueError("evaluation dataset must contain exactly four recordings")
    if set(observed_ids) & set(training_ids):
        raise ValueError("evaluation overlaps calibration training membership")
    records = {}
    diagnostics = {}
    for session_id in observed_ids:
        one = {
            **evaluation,
            "lanes": [
                lane for lane in evaluation["lanes"] if lane["lane"]["session_id"] == session_id
            ],
        }
        evaluations = {}
        reference_receipt = None
        base_signal = None
        base_orbit_receipt = None
        for name, (geometry, motion, shift, arm) in ORBIT_SPECS.items():
            lanes = _prepared(one, background, center, scale, geometry)
            if name == "T_geometry_permute":
                lanes = _permute_geometry(lanes)
            attached, receipt = attach_orbit_increment(
                lanes, motion_control=motion, frequency_shift_fraction=shift
            )
            reference = [lane["reference"].tolist() for lane in attached]
            if reference_receipt is None:
                reference_receipt = reference
            elif reference != reference_receipt:
                raise ValueError("orbit controls changed the causal reference")
            if name == "D":
                base_signal = [lane["signal"].tolist() for lane in attached]
                base_orbit_receipt = receipt
            elif name in ("T_swap", "T_geometry_reverse", "T_geometry_permute"):
                if [lane["signal"].tolist() for lane in attached] != base_signal:
                    raise ValueError("geometry-only control changed orbit signal ratios")
                if receipt != base_orbit_receipt:
                    raise ValueError("geometry-only control changed orbit diagnostics")
            evaluations[name] = score_lanes(attached, model["fits"][arm]["selected"])
            diagnostics[f"{session_id}:{name}"] = receipt
        static_base = _prepared(one, background, center, scale)
        static_causal, static_receipt = attach_causal_frequency(static_base)
        static_evaluations = {
            arm: score_lanes(
                static_causal, static_model["families"]["causal"]["fits"][arm]["selected"]
            )
            for arm in ARMS
        }
        if [lane["reference"].tolist() for lane in static_causal] != reference_receipt:
            raise ValueError("static and orbit evaluations do not share causal reference")
        records[session_id] = {
            "eligible_lanes": len(one["lanes"]),
            "orbit_increment": evaluations,
            "static_causal": static_evaluations,
            "static_causal_reference_diagnostics": static_receipt,
        }
    aggregates = {}
    comparisons = (
        ("T", "D"),
        ("T", "S"),
        ("T", "T_swap"),
        ("T", "T_geometry_reverse"),
        ("T", "T_zero_motion"),
        ("T", "T_reverse_motion"),
        ("T", "T_shift"),
        ("T", "T_geometry_permute"),
    )
    for role in ROLES:
        for label, names in (("orbit_increment", ORBIT_SPECS), ("static_causal", ARMS)):
            for name in names:
                values = {
                    sid: row[label][name]["roles"][role]["relative_log_score_per_window"]
                    for sid, row in records.items()
                }
                aggregates[f"{role}:{label}_{name}-causal_reference"] = _summary(values)
        for left, right in comparisons:
            values = {
                sid: row["orbit_increment"][left]["roles"][role]["relative_log_score_per_window"]
                - row["orbit_increment"][right]["roles"][role]["relative_log_score_per_window"]
                for sid, row in records.items()
            }
            aggregates[f"{role}:orbit_increment_{left}-{right}"] = _summary(values)
        for arm in ARMS:
            values = {
                sid: row["orbit_increment"][arm]["roles"][role]["relative_log_score_per_window"]
                - row["static_causal"][arm]["roles"][role]["relative_log_score_per_window"]
                for sid, row in records.items()
            }
            aggregates[f"{role}:orbit_increment_{arm}-static_causal_{arm}"] = _summary(values)
    return {
        "schema": "rx-orbit-increment-score/v1",
        "status": "complete",
        "training_sessions": training_ids,
        "evaluation_sessions": observed_ids,
        "coverage": {
            "recordings": len(observed_ids),
            "lanes": len(evaluation["lanes"]),
            "recording_split": "evaluation",
        },
        "records": records,
        "aggregate_equal_record": aggregates,
        "orbit_increment_diagnostics": diagnostics,
        "model_labels": {
            "orbit_increment": "new frozen orbit-increment family",
            "static_causal": "previously frozen static-geometry causal family",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    fit_parser = subparsers.add_parser("fit")
    fit_parser.add_argument("--training-dataset", type=Path, required=True)
    fit_parser.add_argument("--output", type=Path, required=True)
    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--training-dataset", type=Path, required=True)
    score_parser.add_argument("--model", type=Path, required=True)
    score_parser.add_argument("--static-model", type=Path, required=True)
    score_parser.add_argument("--dataset", type=Path, required=True)
    score_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    training_payload = args.training_dataset.read_bytes()
    training = json.loads(training_payload)
    if args.stage == "fit":
        result = fit(training)
        result["training_dataset_sha256"] = _digest(training_payload)
    else:
        dataset_payload = args.dataset.read_bytes()
        model_payload = args.model.read_bytes()
        static_payload = args.static_model.read_bytes()
        result = score(
            training,
            json.loads(model_payload),
            json.loads(dataset_payload),
            json.loads(static_payload),
            training_sha256=_digest(training_payload),
        )
        result["source_sha256"] = {
            "training_dataset": _digest(training_payload),
            "model": _digest(model_payload),
            "static_model": _digest(static_payload),
            "dataset": _digest(dataset_payload),
        }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
