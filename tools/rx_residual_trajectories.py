"""Export wrapped nearest-candidate residual trajectories for all frozen nominees."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

ROLES = ("reception", "held_frequency")


def _wrapped(value, period):
    return float((value + period / 2.0) % period - period / 2.0)


def _nearest(candidates, prediction, period):
    if not candidates:
        return None
    residuals = [
        _wrapped(float(candidate["canonical_rx0_hz"]) - prediction, period)
        for candidate in candidates
    ]
    index = min(range(len(residuals)), key=lambda item: (abs(residuals[item]), item))
    candidate = candidates[index]
    return {
        "signed_residual_hz": residuals[index],
        "absolute_residual_hz": abs(residuals[index]),
        "candidate_index": index,
        "candidate_id": candidate["candidate_id"],
        "candidate_frequency_hz": float(candidate["canonical_rx0_hz"]),
        "candidate_rank": candidate.get("candidate_rank"),
        "fractional_margin": candidate.get("fractional_margin"),
    }


def _role_stats(windows, role):
    selected = [window for window in windows if window["role"] == role]
    if not selected:
        return None
    observed = [window for window in selected if window["nearest"] is not None]
    residuals = [window["nearest"]["signed_residual_hz"] for window in observed]
    return {
        "windows": len(selected),
        "observed_windows": len(observed),
        "observed_fraction": len(observed) / len(selected),
        "within_500hz_fraction": sum(
            window["visible"]
            and window["nearest"] is not None
            and window["nearest"]["absolute_residual_hz"] <= 500.0
            for window in selected
        )
        / len(selected),
        "within_1500hz_fraction": sum(
            window["visible"]
            and window["nearest"] is not None
            and window["nearest"]["absolute_residual_hz"] <= 1500.0
            for window in selected
        )
        / len(selected),
        "median_signed_residual_hz_given_observed": (
            float(np.median(residuals)) if residuals else None
        ),
        "median_absolute_residual_hz_given_observed": (
            float(np.median(np.abs(residuals))) if residuals else None
        ),
    }


def _steps(windows, period):
    output = []
    for previous, current in zip(windows[:-1], windows[1:], strict=True):
        previous_nearest, current_nearest = previous["nearest"], current["nearest"]
        candidate_step = None
        residual_step = None
        if previous_nearest is not None and current_nearest is not None:
            candidate_step = _wrapped(
                current_nearest["candidate_frequency_hz"]
                - previous_nearest["candidate_frequency_hz"],
                period,
            )
            residual_step = _wrapped(
                current_nearest["signed_residual_hz"] - previous_nearest["signed_residual_hz"],
                period,
            )
        output.append(
            {
                "from_source_window_id": previous["source_window_id"],
                "to_source_window_id": current["source_window_id"],
                "elapsed_step_s": current["elapsed_s"] - previous["elapsed_s"],
                "candidate_step_hz": candidate_step,
                "forecast_step_hz": _wrapped(
                    current["forecast_frequency_hz"] - previous["forecast_frequency_hz"], period
                ),
                "residual_step_hz": residual_step,
            }
        )
    return output


def _boundary(windows, period):
    reception = [window for window in windows if window["role"] == "reception"]
    held = [window for window in windows if window["role"] == "held_frequency"]
    if not reception or not held:
        return None
    previous, current = reception[-1], held[0]
    previous_nearest, current_nearest = previous["nearest"], current["nearest"]
    return {
        "last_reception_source_window_id": previous["source_window_id"],
        "first_held_source_window_id": current["source_window_id"],
        "last_reception_utc_ns": previous["prediction_utc_ns"],
        "first_held_utc_ns": current["prediction_utc_ns"],
        "gap_s": (current["prediction_utc_ns"] - previous["prediction_utc_ns"]) / 1e9,
        "last_reception_signed_residual_hz": (
            None if previous_nearest is None else previous_nearest["signed_residual_hz"]
        ),
        "first_held_signed_residual_hz": (
            None if current_nearest is None else current_nearest["signed_residual_hz"]
        ),
        "last_reception_candidate_frequency_hz": (
            None if previous_nearest is None else previous_nearest["candidate_frequency_hz"]
        ),
        "first_held_candidate_frequency_hz": (
            None if current_nearest is None else current_nearest["candidate_frequency_hz"]
        ),
        "last_reception_forecast_frequency_hz": previous["forecast_frequency_hz"],
        "first_held_forecast_frequency_hz": current["forecast_frequency_hz"],
        "candidate_step_hz": (
            None
            if previous_nearest is None or current_nearest is None
            else _wrapped(
                current_nearest["candidate_frequency_hz"]
                - previous_nearest["candidate_frequency_hz"],
                period,
            )
        ),
        "forecast_step_hz": _wrapped(
            current["forecast_frequency_hz"] - previous["forecast_frequency_hz"], period
        ),
        "residual_step_hz": (
            None
            if previous_nearest is None or current_nearest is None
            else _wrapped(
                current_nearest["signed_residual_hz"] - previous_nearest["signed_residual_hz"],
                period,
            )
        ),
    }


def analyze(document, expected_records=None, expected_lanes=None):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    calibration = [
        lane for lane in document.get("lanes", []) if lane.get("recording_split") == "calibration"
    ]
    if expected_lanes is not None and len(calibration) != expected_lanes:
        raise ValueError(f"expected {expected_lanes} calibration lanes")
    session_ids = {lane["lane"]["session_id"] for lane in calibration}
    if expected_records is not None and len(session_ids) != expected_records:
        raise ValueError(f"expected {expected_records} calibration records")
    exports = []
    seen_windows = set()
    for lane in calibration:
        period = float(lane["alias_period_hz"])
        if not math.isfinite(period) or period <= 0:
            raise ValueError("alias period must be positive and finite")
        components = lane.get("components", [])
        if len(components) < 2 or components[-1].get("kind") != "other":
            raise ValueError("components must contain nominees followed by other")
        nominees = components[:-1]
        if any(component.get("kind") != "track_candidate" for component in nominees):
            raise ValueError("all components preceding other must be track candidates")
        keys = [(item.get("track_id"), item.get("catalog_number")) for item in nominees]
        if any(None in key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("nominee keys must be complete and unique")
        log_prior = np.asarray(
            [item["log_prior"] if item["log_prior"] is not None else -np.inf for item in nominees],
            dtype=float,
        )
        if not np.isfinite(logsumexp(log_prior)):
            raise ValueError("lane has no retained nominee mass")
        normalized_logs = log_prior - logsumexp(log_prior)
        probabilities = np.exp(normalized_logs)
        times = [window["prediction_utc_ns"] for window in lane["windows"]]
        if any(not isinstance(value, int) for value in times) or any(
            later <= earlier for earlier, later in zip(times[:-1], times[1:], strict=True)
        ):
            raise ValueError("window timestamps must be integer and strictly increasing")
        roles = [window["role"] for window in lane["windows"]]
        if set(roles) != set(ROLES) or any(role not in ROLES for role in roles):
            raise ValueError("lane must contain both declared roles")
        first_held = roles.index("held_frequency")
        if any(role != "reception" for role in roles[:first_held]) or any(
            role != "held_frequency" for role in roles[first_held:]
        ):
            raise ValueError("all reception windows must precede held windows")
        reception_times = [
            time
            for time, window in zip(times, lane["windows"], strict=True)
            if window["role"] == "reception"
        ]
        if not reception_times:
            raise ValueError("lane has no reception origin")
        origin = min(reception_times)
        nominee_exports = []
        for nominee_index, (component, key) in enumerate(zip(nominees, keys, strict=True)):
            receivers = []
            for receiver_name in ("rx0", "rx1"):
                window_exports = []
                for window in lane["windows"]:
                    if window["role"] not in ROLES:
                        raise ValueError("unknown window role")
                    window_id = window["source_window_id"]
                    if window_id in seen_windows and nominee_index == 0 and receiver_name == "rx0":
                        raise ValueError("duplicate source window")
                    predictions = window["predictions"]
                    if len(predictions) != len(nominees):
                        raise ValueError("prediction/nominee population mismatch")
                    prediction = predictions[nominee_index]
                    if (prediction.get("track_id"), prediction.get("catalog_number")) != key:
                        raise ValueError("prediction/nominee key mismatch")
                    forecast = float(prediction["mu_canonical_rx0_hz"])
                    if not math.isfinite(forecast):
                        raise ValueError("nonfinite forecast")
                    candidates = window["observed"][receiver_name]
                    for candidate in candidates:
                        if not isinstance(candidate.get("candidate_id"), str) or not math.isfinite(
                            float(candidate["canonical_rx0_hz"])
                        ):
                            raise ValueError("invalid observed candidate")
                    nearest = _nearest(candidates, forecast, period)
                    window_exports.append(
                        {
                            "source_window_id": window_id,
                            "role": window["role"],
                            "prediction_utc_ns": window["prediction_utc_ns"],
                            "elapsed_s": (window["prediction_utc_ns"] - origin) / 1e9,
                            "visible": bool(prediction["visible"]),
                            "forecast_frequency_hz": forecast,
                            "observed_count": len(candidates),
                            "nearest": nearest,
                        }
                    )
                    if nominee_index == 0 and receiver_name == "rx0":
                        seen_windows.add(window_id)
                receivers.append(
                    {
                        "receiver": receiver_name,
                        "windows": window_exports,
                        "adjacent_steps": _steps(window_exports, period),
                        "role_boundary": _boundary(window_exports, period),
                        "role_stats": {role: _role_stats(window_exports, role) for role in ROLES},
                    }
                )
            nominee_exports.append(
                {
                    "track_id": component["track_id"],
                    "catalog_number": component["catalog_number"],
                    "rank": component.get("rank"),
                    "normalized_log_prior": (
                        float(normalized_logs[nominee_index])
                        if np.isfinite(normalized_logs[nominee_index])
                        else None
                    ),
                    "prior_probability": float(probabilities[nominee_index]),
                    "receivers": receivers,
                }
            )
        exports.append(
            {
                "lane": lane["lane"],
                "session_id": lane["lane"]["session_id"],
                "alias_period_hz": period,
                "nomination_summary": {
                    "nominees": len(nominees),
                    "finite_log_prior_count": int(np.isfinite(log_prior).sum()),
                    "positive_probability_count": int(np.sum(probabilities > 0)),
                    "weight_ge_1e_6_count": int(np.sum(probabilities >= 1e-6)),
                    "finite_below_1e_6_count": int(
                        np.sum(np.isfinite(log_prior) & (probabilities < 1e-6))
                    ),
                },
                "nominees": nominee_exports,
            }
        )
    return {
        "schema": "rx-residual-trajectories/v1",
        "status": "complete",
        "calibration_records": sorted(session_ids),
        "lanes": exports,
        "interpretation": "Wrapped nearest-candidate descriptions for every retained nominee; "
        "candidate switching is not a physical track and no time unwrapping, midpoint "
        "repropagation, role-specific transform, or fit is performed.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = analyze(json.loads(payload), expected_records=6, expected_lanes=12)
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
