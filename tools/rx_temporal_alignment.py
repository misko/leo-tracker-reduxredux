"""Describe temporal alignment between raw candidates and frozen presence scores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

BIN_EDGES_S = (0.0, 30.0, 60.0, 90.0, 120.0, 180.0, math.inf)
METRICS = (
    "prior_probability_nearest_le_500hz_rx0",
    "prior_probability_nearest_le_500hz_rx1",
    "prior_probability_nearest_le_1500hz_rx0",
    "prior_probability_nearest_le_1500hz_rx1",
    "candidate_count_rx0",
    "candidate_count_rx1",
    "visible_prior_mass",
    "D_presence_probability",
    "T_presence_probability",
    "D_relative_log_score",
    "T_relative_log_score",
)


def _lane_key(lane):
    return json.dumps(lane, sort_keys=True, separators=(",", ":"))


def _transfer_windows(transfer):
    if (
        transfer.get("schema") != "rx-geometry-temporal-transfer/v1"
        or transfer.get("status") != "complete"
    ):
        raise ValueError("temporal transfer result must be complete")
    output = {}
    fold_ids = []
    for fold in transfer.get("folds", []):
        session_id = fold["held_session"]
        fold_ids.append(session_id)
        evaluations = fold["families"]["within"]["evaluations"]
        arm_maps = {}
        for arm in ("D", "T"):
            arm_map = {}
            for lane in evaluations[arm]["lanes"]:
                presence = lane["window_presence"]
                if len(presence) != len(lane["windows"]):
                    raise ValueError("transfer presence/window length mismatch")
                for window, probability in zip(lane["windows"], presence, strict=True):
                    window_id = window["source_window_id"]
                    if window["role"] not in ("reception", "held_frequency"):
                        raise ValueError("unknown transfer window role")
                    if (
                        not math.isfinite(float(probability))
                        or not 0.0 <= float(probability) <= 1.0
                        or not math.isfinite(float(window["relative_log_score"]))
                    ):
                        raise ValueError("nonfinite transfer probability or score")
                    if window_id in arm_map:
                        raise ValueError("duplicate transfer source window")
                    arm_map[window_id] = {
                        "lane": lane["lane"],
                        "role": window["role"],
                        "prediction_utc_ns": window["prediction_utc_ns"],
                        "presence_probability": probability,
                        "relative_log_score": window["relative_log_score"],
                    }
            arm_maps[arm] = arm_map
        if set(arm_maps["D"]) != set(arm_maps["T"]):
            raise ValueError("D/T transfer window populations differ")
        for window_id in arm_maps["D"]:
            left, right = arm_maps["D"][window_id], arm_maps["T"][window_id]
            if (
                _lane_key(left["lane"]) != _lane_key(right["lane"])
                or left["role"] != right["role"]
                or left["prediction_utc_ns"] != right["prediction_utc_ns"]
            ):
                raise ValueError("D/T transfer metadata differ")
            if window_id in output:
                raise ValueError("duplicate transfer source window across folds")
            output[window_id] = {
                **left,
                "session_id": session_id,
                "D_presence_probability": left["presence_probability"],
                "T_presence_probability": right["presence_probability"],
                "D_relative_log_score": left["relative_log_score"],
                "T_relative_log_score": right["relative_log_score"],
            }
    if len(fold_ids) != len(set(fold_ids)):
        raise ValueError("duplicate temporal-transfer fold")
    return output, set(fold_ids)


def _periodic_nearest(frequencies, prediction, period):
    if not frequencies:
        return math.inf
    delta = np.asarray(frequencies, dtype=float) - prediction
    wrapped = np.remainder(delta + period / 2.0, period) - period / 2.0
    return float(np.min(np.abs(wrapped)))


def _bin_label(elapsed):
    for left, right in zip(BIN_EDGES_S[:-1], BIN_EDGES_S[1:], strict=True):
        if left <= elapsed < right:
            right_label = "infinity" if math.isinf(right) else str(int(right))
            return f"{int(left)}-{right_label}"
    raise ValueError("elapsed time precedes first reception")


def lane_reception_origins(document):
    """Return the first reception timestamp for every calibration lane."""
    origins = {}
    for lane in document.get("lanes", []):
        if lane.get("recording_split") != "calibration":
            continue
        key = (lane["lane"]["session_id"], _lane_key(lane["lane"]))
        times = [
            window["prediction_utc_ns"]
            for window in lane["windows"]
            if window["role"] == "reception"
        ]
        if not times:
            raise ValueError("calibration lane lacks reception windows")
        if key in origins:
            raise ValueError("duplicate calibration lane identity")
        origins[key] = min(times)
    return origins


def aggregate_rows(rows, calibration_ids):
    """Aggregate windows with equal recording weight for each role and bin."""
    aggregates = {}
    bin_labels = [
        f"{int(left)}-{'infinity' if math.isinf(right) else int(right)}"
        for left, right in zip(BIN_EDGES_S[:-1], BIN_EDGES_S[1:], strict=True)
    ]
    for role in ("reception", "held_frequency"):
        for label in ("all", *bin_labels):
            record_means = {}
            window_count = 0
            for sid in sorted(calibration_ids):
                selected = [
                    row
                    for row in rows
                    if row["session_id"] == sid
                    and row["role"] == role
                    and (label == "all" or row["elapsed_bin_s"] == label)
                ]
                if selected:
                    window_count += len(selected)
                    record_means[sid] = {
                        metric: float(np.mean([row[metric] for row in selected]))
                        for metric in METRICS
                    }
            aggregates[f"{role}:{label}"] = {
                "recordings_with_windows": len(record_means),
                "windows": window_count,
                "record_means": record_means,
                "equal_record_mean": {
                    metric: (
                        float(np.mean([value[metric] for value in record_means.values()]))
                        if record_means
                        else None
                    )
                    for metric in METRICS
                },
            }
    return aggregates


def analyze(document, transfer):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    joined, fold_ids = _transfer_windows(transfer)
    calibration_ids = {
        lane["lane"]["session_id"]
        for lane in document.get("lanes", [])
        if lane.get("recording_split") == "calibration"
    }
    if calibration_ids != fold_ids:
        raise ValueError("dataset and transfer calibration populations differ")
    first_reception = lane_reception_origins(document)

    rows = []
    seen = set()
    for lane in document["lanes"]:
        if lane.get("recording_split") != "calibration":
            continue
        sid = lane["lane"]["session_id"]
        period = float(lane["alias_period_hz"])
        if not math.isfinite(period) or period <= 0:
            raise ValueError("alias period must be positive and finite")
        if not lane.get("components") or lane["components"][-1].get("kind") != "other":
            raise ValueError("components must end with other")
        nominees = lane["components"][:-1]
        log_prior = np.asarray(
            [item["log_prior"] if item["log_prior"] is not None else -np.inf for item in nominees]
        )
        if not np.isfinite(logsumexp(log_prior)):
            raise ValueError("lane has no retained nomination mass")
        weights = np.exp(log_prior - logsumexp(log_prior))
        for window in lane["windows"]:
            if window["role"] not in ("reception", "held_frequency"):
                raise ValueError("unknown dataset window role")
            window_id = window["source_window_id"]
            if window_id in seen:
                raise ValueError("duplicate dataset source window")
            seen.add(window_id)
            frozen = joined.get(window_id)
            if frozen is None:
                raise ValueError("dataset window missing from temporal transfer")
            if (
                frozen["session_id"] != sid
                or frozen["role"] != window["role"]
                or frozen["prediction_utc_ns"] != window["prediction_utc_ns"]
                or _lane_key(frozen["lane"]) != _lane_key(lane["lane"])
            ):
                raise ValueError("dataset/transfer window metadata mismatch")
            if len(window["predictions"]) != len(nominees):
                raise ValueError("prediction/nominee population mismatch")
            component_keys = [
                (component.get("track_id"), component.get("catalog_number"))
                for component in nominees
            ]
            if any(None in key for key in component_keys) or len(set(component_keys)) != len(
                component_keys
            ):
                raise ValueError("nominee keys must be complete and unique")
            prediction_keys = [
                (prediction.get("track_id"), prediction.get("catalog_number"))
                for prediction in window["predictions"]
            ]
            if component_keys != prediction_keys:
                raise ValueError("prediction/nominee key alignment mismatch")
            frequencies = [
                [candidate["canonical_rx0_hz"] for candidate in window["observed"][receiver]]
                for receiver in ("rx0", "rx1")
            ]
            if any(not math.isfinite(float(value)) for values in frequencies for value in values):
                raise ValueError("candidate frequencies must be finite")
            probabilities = np.zeros((2, 2))
            visible_mass = 0.0
            for weight, prediction in zip(weights, window["predictions"], strict=True):
                if not math.isfinite(float(prediction["mu_canonical_rx0_hz"])):
                    raise ValueError("prediction frequency must be finite")
                if not prediction["visible"]:
                    continue
                visible_mass += weight
                for receiver in range(2):
                    nearest = _periodic_nearest(
                        frequencies[receiver], prediction["mu_canonical_rx0_hz"], period
                    )
                    probabilities[0, receiver] += weight * (nearest <= 500.0)
                    probabilities[1, receiver] += weight * (nearest <= 1500.0)
            origin_key = (sid, _lane_key(lane["lane"]))
            elapsed = (window["prediction_utc_ns"] - first_reception[origin_key]) / 1e9
            rows.append(
                {
                    "source_window_id": window_id,
                    "session_id": sid,
                    "lane": lane["lane"],
                    "role": window["role"],
                    "prediction_utc_ns": window["prediction_utc_ns"],
                    "elapsed_s": elapsed,
                    "elapsed_bin_s": _bin_label(elapsed),
                    "candidate_count_rx0": len(frequencies[0]),
                    "candidate_count_rx1": len(frequencies[1]),
                    "visible_prior_mass": visible_mass,
                    "prior_probability_nearest_le_500hz_rx0": probabilities[0, 0],
                    "prior_probability_nearest_le_500hz_rx1": probabilities[0, 1],
                    "prior_probability_nearest_le_1500hz_rx0": probabilities[1, 0],
                    "prior_probability_nearest_le_1500hz_rx1": probabilities[1, 1],
                    **{
                        key: frozen[key]
                        for key in (
                            "D_presence_probability",
                            "T_presence_probability",
                            "D_relative_log_score",
                            "T_relative_log_score",
                        )
                    },
                }
            )
    if seen != set(joined):
        raise ValueError("temporal transfer contains windows outside calibration dataset")

    aggregates = aggregate_rows(rows, calibration_ids)
    return {
        "schema": "rx-temporal-alignment/v1",
        "status": "complete",
        "elapsed_bin_edges_s": [0, 30, 60, 90, 120, 180, "infinity"],
        "windows": rows,
        "aggregate_equal_record": aggregates,
        "interpretation": (
            "Descriptive periodic candidate alignment; duplicate saved candidates remain in "
            "receiver counts while nearest residuals are duplicate-invariant. No optimization "
            "or causal claim."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--transfer-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_bytes = args.dataset.read_bytes()
    transfer_bytes = args.transfer_results.read_bytes()
    document, transfer = json.loads(dataset_bytes), json.loads(transfer_bytes)
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    if transfer.get("source_sha256", {}).get("dataset") != dataset_hash:
        raise ValueError("temporal transfer is not bound to this dataset")
    if len(transfer.get("folds", [])) != 6:
        raise ValueError("production temporal transfer must contain six folds")
    result = analyze(document, transfer)
    result["source_sha256"] = {
        "dataset": dataset_hash,
        "transfer_results": hashlib.sha256(transfer_bytes).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
