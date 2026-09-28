"""Score frozen full-calibration geometry models on the prospective DS8 panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_causal_geometry import attach_causal_frequency
from tools.rx_geometry_temporal_transfer import score_lanes, within_center_from_reception
from tools.rx_joint_geometry import attach_reference
from tools.rx_presence_geometry import prepare_lanes

ARMS = ("D", "E", "S", "T")
DIMENSIONS = {"D": 3, "E": 4, "S": 6, "T": 8}
ROLES = ("reception", "held_frequency")
SPECIFICATIONS = {
    **{arm: (None, arm) for arm in ARMS},
    "T_swap": ("swap", "T"),
    "T_reverse": ("reverse", "T"),
    **{f"{arm}_shift": ("shift", arm) for arm in ARMS},
}


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_model(model, training_document, training_sha256=None):
    if model.get("schema") != "rx-causal-full-calibration/v1" or model.get("status") != "complete":
        raise ValueError("model must be a complete full-calibration result")
    if float(model.get("sigma_hz", np.nan)) != 500.0:
        raise ValueError("model sigma must equal 500 Hz")
    if training_sha256 is not None and model.get("dataset_sha256") != training_sha256:
        raise ValueError("model training-dataset hash mismatch")
    rows = calibration_rows(training_document)
    calibration_lanes = [
        lane
        for lane in training_document.get("lanes", [])
        if lane.get("recording_split") == "calibration"
    ]
    if len(calibration_lanes) != 12:
        raise ValueError("model training dataset must contain twelve calibration lanes")
    sessions = sorted({row["session_id"] for row in rows})
    window_ids = sorted(row["window_id"] for row in rows)
    if model.get("calibration_sessions") != sessions or len(sessions) != 6:
        raise ValueError("model calibration membership mismatch")
    if (
        model.get("training_source_window_ids") != window_ids
        or model.get("training_source_window_count") != len(window_ids)
        or model.get("training_source_window_ids_sha256") != _json_hash(window_ids)
    ):
        raise ValueError("model training-window binding mismatch")
    background = model.get("background_model", {})
    if (
        background.get("schema") != "rx-empirical-background/v1"
        or background.get("mode") != "joint"
        or background.get("rows") != len(rows)
        or model.get("background_model_sha256") != _json_hash(background)
    ):
        raise ValueError("model background binding mismatch")
    center = np.asarray(model.get("feature_center"), dtype=float)
    scale = np.asarray(model.get("feature_scale"), dtype=float)
    if center.shape != (8,) or scale.shape != (8,) or not np.all(np.isfinite(center)):
        raise ValueError("invalid frozen scaler")
    if not np.all(np.isfinite(scale)) or np.any(scale <= 0):
        raise ValueError("invalid frozen scaler")
    families = model.get("families", {})
    for family in ("uniform", "causal"):
        fits = families.get(family, {}).get("fits", {})
        if set(fits) != set(ARMS):
            raise ValueError("model does not contain all frozen arms")
        for arm, dimension in DIMENSIONS.items():
            selected = fits[arm].get("selected", {})
            beta = np.asarray(selected.get("beta"), dtype=float)
            if beta.shape != (dimension,) or not np.all(np.isfinite(beta)):
                raise ValueError(f"invalid selected {arm} coefficient dimension")
            if not (0 <= float(selected.get("occupancy", np.nan)) <= 1):
                raise ValueError("invalid selected occupancy")
            if not math.isfinite(float(selected.get("tau_s", np.nan))) or float(
                selected["tau_s"]
            ) <= 0:
                raise ValueError("invalid selected persistence time")
            candidates = fits[arm].get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError(f"missing {arm} optimizer candidates")
            converged = []
            for candidate in candidates:
                parameters = np.asarray(candidate.get("parameters"), dtype=float)
                gain = float(candidate.get("map_gain", np.nan))
                if parameters.shape != (dimension + 2,) or not np.all(np.isfinite(parameters)):
                    raise ValueError(f"invalid {arm} optimizer candidate")
                if not math.isfinite(gain):
                    raise ValueError(f"invalid {arm} optimizer MAP gain")
                if candidate.get("success") is True:
                    converged.append(candidate)
            if not converged:
                raise ValueError(f"no {arm} optimizer candidate converged")
            best = max(converged, key=lambda candidate: float(candidate["map_gain"]))
            if float(best["map_gain"]) <= 0:
                expected = {
                    "beta": [0.0] * dimension,
                    "occupancy": 0.0,
                    "tau_s": 1.0,
                    "calibration_relative_log_evidence": 0.0,
                    "map_penalty": 0.0,
                    "map_gain": 0.0,
                    "null_selected": True,
                }
                if selected != expected:
                    raise ValueError(f"selected {arm} fit is not the exact null")
            else:
                parameters = np.asarray(best["parameters"], dtype=float)
                expected_scalars = {
                    "occupancy": float(expit(parameters[-2])),
                    "tau_s": math.exp(parameters[-1]),
                    "calibration_relative_log_evidence": float(
                        best["calibration_relative_log_evidence"]
                    ),
                    "map_penalty": float(best["map_penalty"]),
                    "map_gain": float(best["map_gain"]),
                }
                if selected.get("null_selected") is not False or not np.allclose(
                    beta, parameters[:dimension], rtol=0, atol=1e-12
                ):
                    raise ValueError(f"selected {arm} fit does not match best converged candidate")
                if any(
                    not math.isclose(
                        float(selected.get(key, np.nan)), value, rel_tol=0, abs_tol=1e-12
                    )
                    for key, value in expected_scalars.items()
                ):
                    raise ValueError(f"selected {arm} fit receipt is inconsistent")
    return sessions, background, center, scale


def _readiness_ids(readiness):
    if readiness.get("schema") != "rx-ds8-confirmation-readiness/v1":
        raise ValueError("unsupported readiness schema")
    selected = readiness.get("selected", [])
    ids = [row.get("session_id") for row in selected]
    if len(ids) != 4 or len(set(ids)) != 4 or any(not isinstance(value, str) for value in ids):
        raise ValueError("readiness must select four unique recordings")
    return ids


def _prepare(document, background, center, scale, control=None):
    lanes = prepare_lanes(document, center, scale)
    uniform = attach_reference(
        lanes, background, 500.0, control=control, center=center, scale=scale
    )
    uniform = within_center_from_reception(uniform)
    causal, diagnostics = attach_causal_frequency(
        uniform, frequency_shift_fraction=0.25 if control == "shift" else 0.0
    )
    return uniform, causal, diagnostics


def _role_reference(lanes):
    totals = {role: {"windows": 0, "log_score": 0.0} for role in ROLES}
    for lane in lanes:
        for role in ROLES:
            mask = lane["roles"] == role
            totals[role]["windows"] += int(mask.sum())
            totals[role]["log_score"] += float(np.sum(lane["reference"][mask]))
    for role, row in totals.items():
        if row["windows"] == 0:
            raise ValueError(f"empty {role} population")
        row["log_score_per_window"] = row["log_score"] / row["windows"]
    return totals


def _summary(values):
    if not values:
        raise ValueError("cannot summarize an empty eligible population")
    return {
        "records": values,
        "eligible_recordings": len(values),
        "equal_record_mean": math.fsum(values.values()) / len(values),
        "positive_records": sum(value > 0 for value in values.values()),
        "negative_records": sum(value < 0 for value in values.values()),
        "zero_records": sum(value == 0 for value in values.values()),
    }


def analyze(document, model, training_document, readiness, *, training_sha256=None):
    """Evaluate frozen models without fitting or reading any calibration-held rows."""
    training_ids, background, center, scale = _validate_model(
        model, training_document, training_sha256
    )
    expected_ids = _readiness_ids(readiness)
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported DS8 dataset schema")
    source_lanes = document.get("lanes", [])
    if any(lane.get("recording_split") != "evaluation" for lane in source_lanes):
        raise ValueError("DS8 dataset must contain evaluation lanes only")
    observed_ids = {lane.get("lane", {}).get("session_id") for lane in source_lanes}
    if None in observed_ids or not observed_ids <= set(expected_ids):
        raise ValueError("DS8 dataset includes a recording outside frozen readiness")
    if observed_ids & set(training_ids):
        raise ValueError("DS8 recordings overlap model calibration recordings")

    prepared = {}
    reference_receipt = None
    for name, (control, _) in SPECIFICATIONS.items():
        uniform, causal, diagnostics = _prepare(document, background, center, scale, control)
        receipt = {
            "diagnostics": diagnostics,
            "reference": [lane["reference"].tolist() for lane in causal],
        }
        if reference_receipt is None:
            reference_receipt = receipt
        elif receipt != reference_receipt:
            raise ValueError("causal reference differs across controls")
        prepared[name] = (uniform, causal)
    if not prepared["D"][1]:
        raise ValueError("DS8 dataset has no eligible lanes")

    records = {}
    for session_id in expected_ids:
        session_lanes = {
            name: (
                [lane for lane in pair[0] if lane["source"]["lane"]["session_id"] == session_id],
                [lane for lane in pair[1] if lane["source"]["lane"]["session_id"] == session_id],
            )
            for name, pair in prepared.items()
        }
        lane_count = len(session_lanes["D"][1])
        if lane_count == 0:
            records[session_id] = {
                "eligible": False,
                "eligible_lanes": 0,
                "eligible_windows": 0,
                "reason": "no eligible lane in the frozen DS8 dataset",
            }
            continue
        uniform_base, causal_base = session_lanes["D"]
        uniform_reference = _role_reference(uniform_base)
        causal_reference = _role_reference(causal_base)
        references = {}
        for role in ROLES:
            if uniform_reference[role]["windows"] != causal_reference[role]["windows"]:
                raise ValueError("reference denominator mismatch")
            references[role] = {
                "windows": causal_reference[role]["windows"],
                "background_full_log_score": uniform_reference[role]["log_score"],
                "background_full_log_score_per_window": uniform_reference[role][
                    "log_score_per_window"
                ],
                "causal_reference_log_score": causal_reference[role]["log_score"],
                "causal_reference_log_score_per_window": causal_reference[role][
                    "log_score_per_window"
                ],
                "causal_minus_uniform_reference_per_window": causal_reference[role][
                    "log_score_per_window"
                ]
                - uniform_reference[role]["log_score_per_window"],
            }
        families = {}
        for family in ("uniform", "causal"):
            evaluations = {}
            for name, (_, arm) in SPECIFICATIONS.items():
                fitted = model["families"][family]["fits"][arm]["selected"]
                evaluation = score_lanes(session_lanes[name][1], fitted)
                for role in ROLES:
                    ref = evaluation["roles"][role]
                    if (
                        ref["windows"] != references[role]["windows"]
                        or abs(
                            ref["reference_log_score"]
                            - references[role]["causal_reference_log_score"]
                        )
                        > 1e-10
                    ):
                        raise ValueError("model evaluations do not share the causal reference")
                evaluations[name] = evaluation
            families[family] = {"evaluations": evaluations}
        records[session_id] = {
            "eligible": True,
            "eligible_lanes": lane_count,
            "eligible_windows": sum(row["windows"] for row in references.values()),
            "references": references,
            "families": families,
        }

    eligible_ids = [session_id for session_id in expected_ids if records[session_id]["eligible"]]
    if not eligible_ids:
        raise ValueError("no readiness recording has eligible geometry lanes")
    aggregate = {}
    for role in ROLES:
        aggregate[f"{role}:causal_reference-uniform_reference"] = _summary(
            {
                sid: records[sid]["references"][role][
                    "causal_minus_uniform_reference_per_window"
                ]
                for sid in eligible_ids
            }
        )
        for family in ("uniform", "causal"):
            for name in SPECIFICATIONS:
                aggregate[f"{role}:{family}_{name}-causal_reference"] = _summary(
                    {
                        sid: records[sid]["families"][family]["evaluations"][name]["roles"][
                            role
                        ]["relative_log_score_per_window"]
                        for sid in eligible_ids
                    }
                )
            for left, right in (
                ("E", "D"),
                ("S", "D"),
                ("T", "D"),
                ("T", "S"),
                ("T", "T_swap"),
                ("T", "T_reverse"),
                *((arm, f"{arm}_shift") for arm in ARMS),
            ):
                aggregate[f"{role}:{family}_{left}-{right}"] = _summary(
                    {
                        sid: records[sid]["families"][family]["evaluations"][left]["roles"][
                            role
                        ]["relative_log_score_per_window"]
                        - records[sid]["families"][family]["evaluations"][right]["roles"][role][
                            "relative_log_score_per_window"
                        ]
                        for sid in eligible_ids
                    }
                )
        for name in SPECIFICATIONS:
            aggregate[f"{role}:causal_family-{name}-uniform_family-{name}"] = _summary(
                {
                    sid: records[sid]["families"]["causal"]["evaluations"][name]["roles"][
                        role
                    ]["relative_log_score_per_window"]
                    - records[sid]["families"]["uniform"]["evaluations"][name]["roles"][role][
                        "relative_log_score_per_window"
                    ]
                    for sid in eligible_ids
                }
            )
    return {
        "schema": "rx-ds8-geometry-score/v1",
        "status": "complete",
        "sigma_hz": 500.0,
        "readiness_sessions": expected_ids,
        "eligible_sessions": eligible_ids,
        "eligible_session_count": len(eligible_ids),
        "records": records,
        "aggregate_equal_record": aggregate,
        "causal_frequency_diagnostics": reference_receipt["diagnostics"],
        "interpretation": (
            "Frozen full-calibration models scored under one causal reference; no fitting."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    paths = (args.model, args.training_dataset, args.dataset, args.readiness)
    payloads = [path.read_bytes() for path in paths]
    model, training, document, readiness = [json.loads(payload) for payload in payloads]
    result = analyze(
        document,
        model,
        training,
        readiness,
        training_sha256=hashlib.sha256(payloads[1]).hexdigest(),
    )
    result["source_sha256"] = {
        "model": hashlib.sha256(payloads[0]).hexdigest(),
        "training_dataset": hashlib.sha256(payloads[1]).hexdigest(),
        "dataset": hashlib.sha256(payloads[2]).hexdigest(),
        "readiness": hashlib.sha256(payloads[3]).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
