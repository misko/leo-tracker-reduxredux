"""Audit forecast-only candidate variation in nominal receiver contrast."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

SIN10 = math.sin(math.radians(10.0))
ROLES = ("reception", "held_frequency")


def _logsumexp(values):
    values = np.asarray(values, dtype=float)
    return float(np.logaddexp.reduce(values))


def _role_support(times_ns, q, log_prior, visible):
    times_ns = np.asarray(times_ns)
    q = np.asarray(q, dtype=float)
    log_prior = np.asarray(log_prior, dtype=float)
    visible = np.asarray(visible)
    if (
        times_ns.ndim != 1
        or not np.issubdtype(times_ns.dtype, np.integer)
        or len(times_ns) == 0
        or np.any(np.diff(times_ns) <= 0)
    ):
        raise ValueError("role times must be nonempty, integer, and strictly increasing")
    if (
        q.ndim != 2
        or q.shape[0] != len(times_ns)
        or q.shape[1] != len(log_prior)
        or visible.shape != q.shape
        or visible.dtype != bool
    ):
        raise ValueError("q trajectory dimensions do not align")
    if np.any(~np.isfinite(q)) or not np.isfinite(_logsumexp(log_prior)):
        raise ValueError("q and retained priors must contain finite support")
    normalized = log_prior - _logsumexp(log_prior)
    probabilities = np.exp(normalized)
    centered = q - q.mean(axis=0, keepdims=True)
    prior_mean = centered @ probabilities
    disagreement = math.sqrt(
        float(np.sum(probabilities * np.mean((centered - prior_mean[:, None]) ** 2, axis=0)))
    )
    excursions = np.ptp(q, axis=0)
    entropy = -float(np.sum(probabilities[probabilities > 0] * normalized[probabilities > 0]))
    duration_s = (int(times_ns[-1]) - int(times_ns[0])) / 1e9
    nominees = []
    for index in range(q.shape[1]):
        nominees.append(
            {
                "normalized_log_prior": (
                    float(normalized[index]) if np.isfinite(normalized[index]) else None
                ),
                "conditional_retained_probability": float(probabilities[index]),
                "q_first": float(q[0, index]),
                "q_last": float(q[-1, index]),
                "q_range": float(excursions[index]),
                "q_secant_per_s": (
                    None if duration_s == 0 else float((q[-1, index] - q[0, index]) / duration_s)
                ),
                "visible_windows": int(visible[:, index].sum()),
                "visible_fraction": float(visible[:, index].mean()),
            }
        )
    return {
        "windows": len(times_ns),
        "start_utc_ns": int(times_ns[0]),
        "end_utc_ns": int(times_ns[-1]),
        "duration_s": duration_s,
        "prior_weighted_centered_trajectory_rms_disagreement": disagreement,
        "mean_within_trajectory_excursion": float(np.mean(excursions)),
        "prior_weighted_mean_within_trajectory_excursion": float(
            np.sum(probabilities * excursions)
        ),
        "prior_entropy_nats": entropy,
        "prior_effective_nominee_count": math.exp(entropy),
        "prior_weighted_visible_fraction": float(
            np.sum(probabilities * visible.mean(axis=0))
        ),
        "visibility_gated": False,
        "nominees": nominees,
    }


def analyze(document, *, expected_records=None):
    """Analyze calibration forecasts without reading observed candidate fields."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported geometry dataset")
    calibration = [
        lane for lane in document.get("lanes", []) if lane.get("recording_split") == "calibration"
    ]
    session_set = {lane.get("lane", {}).get("session_id") for lane in calibration}
    if any(not isinstance(value, str) or not value for value in session_set):
        raise ValueError("calibration session IDs must be nonempty strings")
    sessions = sorted(session_set)
    if expected_records is not None and len(sessions) != expected_records:
        raise ValueError(f"expected exactly {expected_records} calibration recordings")
    output = []
    seen_windows = set()
    for lane in calibration:
        components = lane.get("components", [])
        if (
            len(components) < 2
            or components[-1].get("kind") != "other"
            or any(component.get("kind") != "track_candidate" for component in components[:-1])
        ):
            raise ValueError("components must be track candidates followed by other")
        nominees = components[:-1]
        keys = [(row.get("track_id"), row.get("catalog_number")) for row in nominees]
        if any(None in key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("track/catalog nominee keys must be complete and unique")
        retained_logs = np.asarray(
            [
                -np.inf if nominee.get("log_prior") is None else float(nominee["log_prior"])
                for nominee in nominees
            ]
        )
        if (
            np.any(np.isnan(retained_logs))
            or np.any(retained_logs == np.inf)
            or not np.isfinite(_logsumexp(retained_logs))
        ):
            raise ValueError("retained priors must contain finite mass")
        other_log = components[-1].get("log_prior")
        omitted_mass = 0.0 if other_log is None else math.exp(float(other_log))
        retained_mass = float(np.sum(np.exp(retained_logs[np.isfinite(retained_logs)])))
        if not math.isfinite(omitted_mass) or omitted_mass < 0:
            raise ValueError("invalid omitted prior mass")
        if not math.isclose(retained_mass + omitted_mass, 1.0, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("retained and omitted prior masses must sum to one")
        windows = lane.get("windows", [])
        if any(window.get("role") not in ROLES for window in windows):
            raise ValueError("window has an unsupported role")
        times = [window.get("prediction_utc_ns") for window in windows]
        if any(not isinstance(value, int) for value in times) or any(
            right <= left for left, right in zip(times, times[1:], strict=False)
        ):
            raise ValueError("lane windows must have strictly increasing integer times")
        role_rows = {}
        for role in ROLES:
            selected = [window for window in windows if window.get("role") == role]
            if not selected:
                role_rows[role] = None
                continue
            role_times, q_rows, visible_rows = [], [], []
            for window in selected:
                window_id = window.get("source_window_id")
                if not isinstance(window_id, str) or not window_id:
                    raise ValueError("source window ID must be nonempty")
                if window_id in seen_windows:
                    raise ValueError("source window IDs must be globally unique")
                seen_windows.add(window_id)
                predictions = window.get("predictions", [])
                prediction_keys = [
                    (prediction.get("track_id"), prediction.get("catalog_number"))
                    for prediction in predictions
                ]
                if prediction_keys != keys:
                    raise ValueError("prediction keys/order do not match nominees")
                east = np.asarray(
                    [prediction.get("los_enu_unit", {}).get("east") for prediction in predictions],
                    dtype=float,
                )
                if np.any(~np.isfinite(east)):
                    raise ValueError("forecast east LOS must be finite")
                visibility = [prediction.get("visible") for prediction in predictions]
                if any(not isinstance(value, bool) for value in visibility):
                    raise ValueError("forecast visibility must be boolean")
                role_times.append(window["prediction_utc_ns"])
                q_rows.append(2.0 * SIN10 * east)
                visible_rows.append(visibility)
            role_result = _role_support(role_times, q_rows, retained_logs, visible_rows)
            for nominee, component, key in zip(
                role_result["nominees"], nominees, keys, strict=True
            ):
                nominee.update(
                    {
                        "track_id": key[0],
                        "catalog_number": key[1],
                        "rank": component.get("rank"),
                        "log_prior": (
                            float(component["log_prior"])
                            if component.get("log_prior") is not None
                            and math.isfinite(float(component["log_prior"]))
                            else None
                        ),
                    }
                )
            role_rows[role] = role_result
        output.append(
            {
                "lane": lane["lane"],
                "session_id": lane["lane"]["session_id"],
                "retained_nominee_count": len(nominees),
                "retained_prior_mass_before_conditional_normalization": retained_mass,
                "omitted_prior_mass": omitted_mass,
                "roles": role_rows,
            }
        )
    return {
        "schema": "rx-partial-arc-support/v1",
        "status": "complete",
        "calibration_sessions": sessions,
        "lanes": output,
        "interpretation": (
            "Forecast-only conditional-retained partial-arc support; not a score, identity claim, "
            "or calibrated receiver response. Visibility is reported but does not gate "
            "trajectories."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = analyze(json.loads(payload), expected_records=6)
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
