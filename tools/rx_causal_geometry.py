"""Score frozen within-geometry models against a causal frequency reference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.rx_causal_frequency import CausalFrequencyPredictor
from tools.rx_geometry_likelihood import periodic_signal_ratio
from tools.rx_geometry_temporal_transfer import (
    _calibration_record,
    _prepare_control,
    score_lanes,
    within_center_from_reception,
)

ARMS = ("D", "S", "T")
EVALUATIONS = (*ARMS, "T_swap", "T_reverse", "T_shift")
ROLES = ("reception", "held_frequency")


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def attach_causal_frequency(lanes, sigma_hz=500.0, frequency_shift_fraction=0.0):
    """Replace uniform phase terms while preserving frozen count probabilities."""
    output, diagnostics = [], []
    for lane in lanes:
        changed = {
            **lane,
            "reference": lane["reference"].copy(),
            "signal": lane["signal"].copy(),
        }
        period = float(lane["source"]["alias_period_hz"])
        receiver_rows = []
        for receiver_index, receiver in enumerate(("rx0", "rx1")):
            predictor = CausalFrequencyPredictor(period)
            window_rows = []
            for local_index, source_index in enumerate(lane["indices"]):
                window = lane["source"]["windows"][source_index]
                observed = np.asarray(
                    [item["canonical_rx0_hz"] for item in window["observed"][receiver]],
                    dtype=float,
                )
                density, receipt = predictor.score_then_update(
                    float(lane["times"][local_index]), observed
                )
                if (
                    len(density) != len(observed)
                    or np.any(~np.isfinite(density))
                    or np.any(density <= 0)
                ):
                    raise ValueError("causal phase density must be positive at every candidate")
                if len(observed):
                    changed["reference"][local_index] += float(np.log(density).sum())
                    predictions = window["predictions"]
                    if len(predictions) != changed["signal"].shape[1]:
                        raise ValueError("prediction and nominee dimensions differ")
                    mu = np.asarray(
                        [item["mu_canonical_rx0_hz"] for item in predictions], dtype=float
                    ) + float(frequency_shift_fraction) * period
                    ratio = np.zeros(len(mu))
                    for value, phase_density in zip(observed, density, strict=True):
                        ratio += periodic_signal_ratio(
                            [value], mu, period, sigma_hz
                        ) / phase_density
                    changed["signal"][local_index, :, receiver_index] = ratio
                else:
                    changed["signal"][local_index, :, receiver_index] = 0.0
                window_rows.append(
                    {
                        "source_window_id": window["source_window_id"],
                        "role": window["role"],
                        "candidate_count": len(observed),
                        "phase_density": density.tolist(),
                        "predictor": receipt,
                    }
                )
            receiver_rows.append({"receiver": receiver, "windows": window_rows})
        output.append(changed)
        diagnostics.append({"lane": lane["source"]["lane"], "receivers": receiver_rows})
    return output, diagnostics


def _summary(values):
    return {
        "records": values,
        "mean": float(np.mean(list(values.values()))),
        "positive_records": sum(value > 0 for value in values.values()),
    }


def analyze(document, cv_results, transfer_results):
    """Apply frozen omitted-record models with no fitting or selection."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset")
    if cv_results.get("schema") != "rx-within-geometry-cv/v1" or cv_results.get(
        "status"
    ) != "complete":
        raise ValueError("cross-validation result must be complete")
    if float(cv_results.get("sigma_hz", np.nan)) != 500.0:
        raise ValueError("cross-validation sigma must be 500 Hz")
    if transfer_results.get("schema") != "rx-geometry-temporal-transfer/v1" or transfer_results.get(
        "status"
    ) != "complete":
        raise ValueError("temporal-transfer result must be complete")
    frozen_by_id = {fold["held_session"]: fold for fold in cv_results["folds"]}
    replay_by_id = {fold["held_session"]: fold for fold in transfer_results["folds"]}
    if len(cv_results["folds"]) != 6 or len(transfer_results["folds"]) != 6:
        raise ValueError("results must contain exactly six folds")
    if set(frozen_by_id) != set(replay_by_id) or len(frozen_by_id) != 6:
        raise ValueError("frozen fold populations differ")
    all_sessions = set(frozen_by_id)
    folds = []
    for session_id in sorted(frozen_by_id):
        frozen = frozen_by_id[session_id]
        if frozen.get("training_sessions") != sorted(all_sessions - {session_id}):
            raise ValueError("frozen training membership mismatch")
        background = frozen.get("background_model", {})
        if (
            background.get("schema") != "rx-empirical-background/v1"
            or background.get("mode") != "joint"
            or background.get("rows") != frozen.get("training_window_count")
            or _json_hash(background) != frozen.get("background_model_sha256")
        ):
            raise ValueError("frozen background metadata mismatch")
        record = _calibration_record(document, session_id)
        center = np.asarray(frozen["feature_center"])
        scale = np.asarray(frozen["feature_scale"])

        def prepared(
            control=None,
            record=record,
            background=frozen["background_model"],
            center=center,
            scale=scale,
        ):
            lanes = _prepare_control(record, background, center, scale, control)
            return within_center_from_reception(lanes)

        uniform = {}
        causal = {}
        diagnostics = None
        causal_reference = None
        specifications = {
            "D": (None, "D"),
            "S": (None, "S"),
            "T": (None, "T"),
            "T_swap": ("swap", "T"),
            "T_reverse": ("reverse", "T"),
            "T_shift": ("shift", "T"),
        }
        for name, (control, arm) in specifications.items():
            base = prepared(control)
            fitted = frozen["families"]["within"]["fits"][arm]["selected"]
            uniform[name] = score_lanes(base, fitted)
            causal_lanes, current_diagnostics = attach_causal_frequency(
                base, frequency_shift_fraction=0.25 if control == "shift" else 0.0
            )
            causal[name] = score_lanes(causal_lanes, fitted)
            if diagnostics is None:
                diagnostics = current_diagnostics
                causal_reference = [lane["reference"].tolist() for lane in causal_lanes]
            elif current_diagnostics != diagnostics or [
                lane["reference"].tolist() for lane in causal_lanes
            ] != causal_reference:
                raise ValueError("causal reference differs across arms or controls")
            replay = replay_by_id[session_id]["families"]["within"]["evaluations"][name]
            if uniform[name] != replay:
                raise ValueError(f"uniform replay mismatch: {session_id} {name}")
        folds.append(
            {
                "held_session": session_id,
                "uniform": uniform,
                "causal": causal,
                "causal_frequency_diagnostics": diagnostics,
            }
        )

    aggregates = {}
    for role in ROLES:
        reference_gain = {
            fold["held_session"]: (
                fold["causal"]["D"]["roles"][role]["reference_log_score_per_window"]
                - fold["uniform"]["D"]["roles"][role]["reference_log_score_per_window"]
            )
            for fold in folds
        }
        aggregates[f"{role}:causal_reference-uniform_reference"] = _summary(reference_gain)
        for name in EVALUATIONS:
            versus_reference = {
                fold["held_session"]: fold["causal"][name]["roles"][role][
                    "relative_log_score_per_window"
                ]
                for fold in folds
            }
            aggregates[f"{role}:causal_{name}-causal_reference"] = _summary(versus_reference)
            full_gain = {
                fold["held_session"]: (
                    fold["causal"][name]["roles"][role]["full_log_score_per_window"]
                    - fold["uniform"][name]["roles"][role]["full_log_score_per_window"]
                )
                for fold in folds
            }
            aggregates[f"{role}:causal_{name}-uniform_{name}_full"] = _summary(full_gain)
        for left, right in (
            ("T", "D"),
            ("T", "S"),
            ("T", "T_swap"),
            ("T", "T_reverse"),
            ("T", "T_shift"),
        ):
            values = {
                fold["held_session"]: (
                    fold["causal"][left]["roles"][role]["relative_log_score_per_window"]
                    - fold["causal"][right]["roles"][role]["relative_log_score_per_window"]
                )
                for fold in folds
            }
            aggregates[f"{role}:causal_{left}-{right}"] = _summary(values)
    return {
        "schema": "rx-causal-geometry/v1",
        "status": "complete",
        "folds": folds,
        "aggregate_equal_record": aggregates,
        "interpretation": "Frozen geometry under a causal frequency reference; no fitting.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cv-results", type=Path, required=True)
    parser.add_argument("--transfer-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    paths = (args.dataset, args.cv_results, args.transfer_results)
    payloads = [path.read_bytes() for path in paths]
    document, cv_results, transfer_results = [json.loads(payload) for payload in payloads]
    dataset_hash = hashlib.sha256(payloads[0]).hexdigest()
    cv_hash = hashlib.sha256(payloads[1]).hexdigest()
    if cv_results.get("dataset_sha256") != dataset_hash:
        raise ValueError("CV result dataset hash mismatch")
    if transfer_results.get("source_sha256", {}).get("dataset") != dataset_hash:
        raise ValueError("transfer result dataset hash mismatch")
    if transfer_results.get("source_sha256", {}).get("cv_results") != cv_hash:
        raise ValueError("transfer result CV hash mismatch")
    result = analyze(document, cv_results, transfer_results)
    result["source_sha256"] = {
        "dataset": dataset_hash,
        "cv_results": cv_hash,
        "transfer_results": hashlib.sha256(payloads[2]).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
