"""Describe geometry-feature support without fitting an outcome model."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from tools.rx_geometry_fit import raw_features
from tools.rx_geometry_frozen_score import validate_frozen_model

FEATURE_NAMES = ("up", "north", "east", "tilt", "tilt_up")
FEATURE_COLUMNS = np.arange(3, 8)


def _finite(value):
    return float(value) if np.isfinite(value) else None


def _correlation(covariance):
    scale = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(scale, scale)
    numeric = np.divide(
        covariance, denominator, out=np.zeros_like(covariance), where=denominator > 0
    )
    exported = [
        [
            _finite(numeric[row, column]) if denominator[row, column] > 0 else None
            for column in range(5)
        ]
        for row in range(5)
    ]
    return numeric, exported


def analyze(document, old_model):
    """Return a weighted identifiability audit of calibration reception geometry."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    center, scale, _ = validate_frozen_model(old_model)
    selected = [
        lane
        for lane in document.get("lanes", [])
        if lane.get("recording_split") == "calibration"
        and any(window.get("role") == "reception" for window in lane.get("windows", []))
    ]
    if not selected:
        raise ValueError("no calibration reception geometry")
    by_record = defaultdict(list)
    for lane in selected:
        by_record[lane["lane"]["session_id"]].append(lane)
    record_count = len(by_record)

    feature_rows = []
    weights = []
    group_ids = []
    lane_exports = []
    for session_id in sorted(by_record):
        lanes = by_record[session_id]
        for source in lanes:
            reception_windows = [
                window for window in source["windows"] if window["role"] == "reception"
            ]
            reception_source = {**source, "windows": reception_windows}
            raw, _, _ = raw_features(reception_source)
            reception_indices = list(range(len(reception_windows)))
            nominees = len(source["components"]) - 1
            if nominees < 1 or raw.shape[1] < nominees:
                raise ValueError("lane has no retained nominee geometry")
            log_prior = np.asarray(
                [
                    component["log_prior"] if component["log_prior"] is not None else -np.inf
                    for component in source["components"][:nominees]
                ],
                dtype=float,
            )
            if not np.isfinite(logsumexp(log_prior)):
                raise ValueError("lane has no finite conditional nominee mass")
            nominee_weights = np.exp(log_prior - logsumexp(log_prior))
            positive_nominees = nominee_weights > 0
            entropy = -float(
                np.sum(
                    nominee_weights[positive_nominees] * np.log(nominee_weights[positive_nominees])
                )
            )
            standardized = (raw - center) / scale
            window_weight = 1.0 / (record_count * len(lanes) * len(reception_indices))
            for index in reception_indices:
                for nominee in range(nominees):
                    if nominee_weights[nominee] == 0:
                        continue
                    for receiver in range(2):
                        feature_rows.append(standardized[index, nominee, receiver, FEATURE_COLUMNS])
                        weights.append(window_weight * nominee_weights[nominee] * 0.5)
                        group_ids.append((session_id, id(source), nominee, receiver))

            first, last = reception_indices[0], reception_indices[-1]
            excursions = []
            nominee_directions = []
            for nominee in range(nominees):
                first_los = raw[first, nominee, 0, [5, 4, 3]]
                last_los = raw[last, nominee, 0, [5, 4, 3]]
                delta_los = last_los - first_los
                cosine = np.dot(first_los, last_los) / (
                    np.linalg.norm(first_los) * np.linalg.norm(last_los)
                )
                excursions.append(math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))))
                nominee_directions.append(
                    {
                        "weight": float(nominee_weights[nominee]),
                        "start_los_enu": first_los.tolist(),
                        "end_los_enu": last_los.tolist(),
                        "endpoint_delta_los_enu": delta_los.tolist(),
                        "endpoint_delta_norm": float(np.linalg.norm(delta_los)),
                        "first_last_angular_excursion_deg": excursions[-1],
                    }
                )
            reception_raw = raw[:, :nominees, :, :]
            times = [window["prediction_utc_ns"] for window in reception_windows]
            if not all(isinstance(value, int) for value in times):
                raise ValueError("prediction times must be integer nanoseconds")
            lane_exports.append(
                {
                    "lane": source["lane"],
                    "reception_windows": len(reception_indices),
                    "time_span_s": (max(times) - min(times)) / 1e9,
                    "conditional_nominee_weights": nominee_weights.tolist(),
                    "nomination_prior_summary": {
                        "entropy_nats": entropy,
                        "maximum_weight": float(nominee_weights.max()),
                        "effective_count": math.exp(entropy),
                        "finite_log_prior_count": int(np.isfinite(log_prior).sum()),
                        "weight_ge_1e_6_count": int(np.sum(nominee_weights >= 1e-6)),
                    },
                    "weighted_nominee_los_first_last_excursion_deg": float(
                        np.dot(nominee_weights, excursions)
                    ),
                    "nominee_forecast_directions": nominee_directions,
                    "raw_feature_temporal_std": {
                        name: float(
                            np.sum(
                                np.std(reception_raw[..., column], axis=0)
                                * nominee_weights[:, None]
                                * 0.5
                            )
                        )
                        for name, column in zip(FEATURE_NAMES, FEATURE_COLUMNS, strict=True)
                    },
                }
            )

    values = np.asarray(feature_rows, dtype=float)
    weight = np.asarray(weights, dtype=float)
    weight /= weight.sum()
    mean = np.sum(weight[:, None] * values, axis=0)
    centered = values - mean
    covariance = (centered * weight[:, None]).T @ centered
    numeric_correlation, exported_correlation = _correlation(covariance)

    groups = defaultdict(list)
    for index, group in enumerate(group_ids):
        groups[group].append(index)
    within = np.zeros((5, 5))
    between = np.zeros((5, 5))
    within_residuals = np.zeros_like(values)
    for indices in groups.values():
        indices = np.asarray(indices)
        group_weight = weight[indices].sum()
        if group_weight <= 0:
            continue
        conditional = weight[indices] / group_weight
        group_mean = np.sum(conditional[:, None] * values[indices], axis=0)
        residual = values[indices] - group_mean
        within += group_weight * (residual * conditional[:, None]).T @ residual
        difference = group_mean - mean
        between += group_weight * np.outer(difference, difference)
        within_residuals[indices] = residual
    total_variance = np.diag(covariance)
    within_variance = np.diag(within)
    between_variance = np.diag(between)
    ratios = np.divide(
        within_variance,
        total_variance,
        out=np.full(5, np.nan),
        where=total_variance > 0,
    )
    within_design = within_residuals * np.sqrt(weight[:, None])
    eigenvalues = np.linalg.eigvalsh(within_design.T @ within_design)[::-1]

    # Receiver sign is reconstructed from the raw feature convention and has
    # equal receiver weight by construction.
    receiver_sign = np.asarray([group[-1] * 2.0 - 1.0 for group in group_ids])
    sign_mean = np.sum(weight * receiver_sign)
    sign_centered = receiver_sign - sign_mean
    sign_variance = np.sum(weight * sign_centered**2)
    sign_correlations = []
    for feature in (3, 4):
        variance = total_variance[feature]
        if variance <= 0 or sign_variance <= 0:
            sign_correlations.append(None)
        else:
            correlation = np.sum(weight * centered[:, feature] * sign_centered) / math.sqrt(
                variance * sign_variance
            )
            sign_correlations.append(float(correlation))

    return {
        "schema": "rx-geometry-support/v1",
        "recordings": record_count,
        "lanes": lane_exports,
        "weight_sum": float(weight.sum()),
        "features": list(FEATURE_NAMES),
        "weighted_mean": mean.tolist(),
        "weighted_covariance": covariance.tolist(),
        "weighted_correlation": exported_correlation,
        "covariance_eigenvalues": np.linalg.eigvalsh(covariance)[::-1].tolist(),
        "correlation_singular_values": np.linalg.svd(
            numeric_correlation, compute_uv=False
        ).tolist(),
        "variance_decomposition": {
            "total": total_variance.tolist(),
            "within_temporal": within_variance.tolist(),
            "between_group_means": between_variance.tolist(),
            "within_fraction": [_finite(value) for value in ratios],
        },
        "tilt_receiver_sign_correlation": {
            "tilt": sign_correlations[0],
            "tilt_up": sign_correlations[1],
        },
        "within_motion_design_eigenvalues": eigenvalues.tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    dataset_bytes = args.dataset.read_bytes()
    model_bytes = args.model.read_bytes()
    document, model = json.loads(dataset_bytes), json.loads(model_bytes)
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    if model.get("dataset_sha256") != dataset_hash:
        raise ValueError("model/dataset digest mismatch")
    result = analyze(document, model)
    result["source_sha256"] = {
        "dataset": dataset_hash,
        "model": hashlib.sha256(model_bytes).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
