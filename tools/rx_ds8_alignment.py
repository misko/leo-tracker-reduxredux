"""Describe prior-weighted nominee alignment in the four-record DS8 panel."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from tools.rx_residual_trajectories import _nearest

ROLES = ("reception", "held_frequency")
RECEIVERS = ("rx0", "rx1")
THRESHOLDS = (500, 1500)
ELAPSED_BINS = (
    (0.0, 30.0, "0-30"),
    (30.0, 60.0, "30-60"),
    (60.0, 90.0, "60-90"),
    (90.0, math.inf, "90+"),
)


def _bin_label(elapsed_s):
    for lower, upper, label in ELAPSED_BINS:
        if lower <= elapsed_s < upper:
            return label
    raise ValueError("elapsed time precedes lane reception origin")


def _mean_metrics(windows):
    if not windows:
        return None
    names = windows[0]["metrics"]
    return {
        "windows": len(windows),
        "metrics": {
            name: math.fsum(window["metrics"][name] for window in windows) / len(windows)
            for name in names
        },
    }


def _validate_lane(lane):
    period = float(lane.get("alias_period_hz", np.nan))
    if not math.isfinite(period) or period <= 0:
        raise ValueError("alias period must be positive and finite")
    components = lane.get("components", [])
    if len(components) < 2 or components[-1].get("kind") != "other":
        raise ValueError("components must end in one other component")
    nominees = components[:-1]
    if any(component.get("kind") != "track_candidate" for component in nominees):
        raise ValueError("all retained components must be track candidates")
    keys = [(item.get("track_id"), item.get("catalog_number")) for item in nominees]
    if any(None in key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("nominee keys must be complete and unique")
    logs = np.asarray(
        [
            item.get("log_prior") if item.get("log_prior") is not None else -np.inf
            for item in nominees
        ],
        dtype=float,
    )
    normalizer = float(logsumexp(logs))
    if not math.isfinite(normalizer):
        raise ValueError("lane has no retained prior mass")
    probabilities = np.exp(logs - normalizer)
    probabilities /= probabilities.sum()
    windows = lane.get("windows", [])
    times = [window.get("prediction_utc_ns") for window in windows]
    if not windows or any(not isinstance(value, int) for value in times) or any(
        right <= left for left, right in zip(times, times[1:], strict=False)
    ):
        raise ValueError("lane windows need strictly increasing integer timestamps")
    roles = [window.get("role") for window in windows]
    if set(roles) != set(ROLES) or any(role not in ROLES for role in roles):
        raise ValueError("each lane must contain both declared roles")
    first_held = roles.index("held_frequency")
    if any(role != "reception" for role in roles[:first_held]) or any(
        role != "held_frequency" for role in roles[first_held:]
    ):
        raise ValueError("reception windows must precede held-frequency windows")
    return period, nominees, keys, logs - normalizer, probabilities


def analyze(document, *, expected_records=4):
    """Export per-window residual support and equal-record descriptive means."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    source_lanes = document.get("lanes", [])
    if any(lane.get("recording_split") != "evaluation" for lane in source_lanes):
        raise ValueError("DS8 alignment input must contain evaluation lanes only")
    session_id_set = {lane.get("lane", {}).get("session_id") for lane in source_lanes}
    if any(not isinstance(value, str) or not value for value in session_id_set) or len(
        session_id_set
    ) != expected_records:
        raise ValueError(f"expected exactly {expected_records} evaluation recordings")
    session_ids = sorted(session_id_set)

    lane_exports = []
    record_windows = {session_id: [] for session_id in session_ids}
    seen_window_ids = set()
    for lane in source_lanes:
        session_id = lane["lane"]["session_id"]
        period, nominees, keys, normalized_logs, probabilities = _validate_lane(lane)
        reception_origin = min(
            window["prediction_utc_ns"]
            for window in lane["windows"]
            if window["role"] == "reception"
        )
        window_exports = []
        for window in lane["windows"]:
            window_id = window.get("source_window_id")
            if not isinstance(window_id, str) or not window_id or window_id in seen_window_ids:
                raise ValueError("source window IDs must be nonempty and globally unique")
            seen_window_ids.add(window_id)
            predictions = window.get("predictions", [])
            if len(predictions) != len(nominees):
                raise ValueError("prediction/nominee population mismatch")
            observations = window.get("observed", {})
            for receiver in RECEIVERS:
                if not isinstance(observations.get(receiver), list):
                    raise ValueError("missing receiver candidate list")
                for candidate in observations[receiver]:
                    if not isinstance(candidate.get("candidate_id"), str) or not math.isfinite(
                        float(candidate.get("canonical_rx0_hz", np.nan))
                    ):
                        raise ValueError("invalid observed candidate")
            nominee_rows = []
            aligned = {threshold: [] for threshold in THRESHOLDS}
            for index, (component, key) in enumerate(zip(nominees, keys, strict=True)):
                prediction = predictions[index]
                if (prediction.get("track_id"), prediction.get("catalog_number")) != key:
                    raise ValueError("prediction/nominee key mismatch")
                mu = float(prediction.get("mu_canonical_rx0_hz", np.nan))
                if not math.isfinite(mu):
                    raise ValueError("forecast frequency must be finite")
                visible = bool(prediction.get("visible"))
                receivers = {}
                for receiver in RECEIVERS:
                    nearest = _nearest(observations[receiver], mu, period)
                    receivers[receiver] = {
                        "visible": visible,
                        "observed_count": len(observations[receiver]),
                        "nearest": nearest,
                    }
                for threshold in THRESHOLDS:
                    aligned[threshold].append(
                        tuple(
                            visible
                            and receivers[receiver]["nearest"] is not None
                            and receivers[receiver]["nearest"]["absolute_residual_hz"] <= threshold
                            for receiver in RECEIVERS
                        )
                    )
                nominee_rows.append(
                    {
                        "track_id": component["track_id"],
                        "catalog_number": component["catalog_number"],
                        "normalized_log_prior": (
                            float(normalized_logs[index])
                            if np.isfinite(normalized_logs[index])
                            else None
                        ),
                        "prior_probability": float(probabilities[index]),
                        "visible": visible,
                        "forecast_frequency_hz": mu,
                        "receivers": receivers,
                    }
                )
            metrics = {
                "rx0_observed": float(bool(observations["rx0"])),
                "rx1_observed": float(bool(observations["rx1"])),
                "prior_weighted_visible": math.fsum(
                    probability * row["visible"]
                    for probability, row in zip(probabilities, nominee_rows, strict=True)
                ),
            }
            for threshold in THRESHOLDS:
                states = aligned[threshold]
                metrics[f"rx0_within_{threshold}hz"] = math.fsum(
                    probability * state[0]
                    for probability, state in zip(probabilities, states, strict=True)
                )
                metrics[f"rx1_within_{threshold}hz"] = math.fsum(
                    probability * state[1]
                    for probability, state in zip(probabilities, states, strict=True)
                )
                for label, target in (
                    ("both", (True, True)),
                    ("rx0_only", (True, False)),
                    ("rx1_only", (False, True)),
                    ("neither", (False, False)),
                ):
                    metrics[f"paired_{threshold}hz_{label}"] = math.fsum(
                        probability
                        for probability, state in zip(probabilities, states, strict=True)
                        if state == target
                    )
            elapsed_s = (window["prediction_utc_ns"] - reception_origin) / 1e9
            exported = {
                "source_window_id": window_id,
                "role": window["role"],
                "prediction_utc_ns": window["prediction_utc_ns"],
                "elapsed_s": elapsed_s,
                "elapsed_bin": _bin_label(elapsed_s),
                "metrics": metrics,
                "nominees": nominee_rows,
            }
            window_exports.append(exported)
            record_windows[session_id].append(exported)
        lane_exports.append(
            {
                "lane": lane["lane"],
                "session_id": session_id,
                "alias_period_hz": period,
                "windows": window_exports,
            }
        )

    records = {}
    for session_id, windows in record_windows.items():
        roles = {
            role: _mean_metrics([row for row in windows if row["role"] == role])
            for role in ROLES
        }
        bins = {}
        for role in ROLES:
            for _, _, label in ELAPSED_BINS:
                selected = [
                    row for row in windows if row["role"] == role and row["elapsed_bin"] == label
                ]
                if selected:
                    bins[f"{role}:{label}"] = _mean_metrics(selected)
        records[session_id] = {"windows": len(windows), "roles": roles, "elapsed_bins": bins}

    aggregate_roles = {}
    for role in ROLES:
        supported = {sid: row["roles"][role] for sid, row in records.items() if row["roles"][role]}
        metric_names = next(iter(supported.values()))["metrics"]
        aggregate_roles[role] = {
            "records": len(supported),
            "windows": sum(row["windows"] for row in supported.values()),
            "metrics": {
                name: math.fsum(row["metrics"][name] for row in supported.values()) / len(supported)
                for name in metric_names
            },
        }
    aggregate_bins = {}
    for role in ROLES:
        for _, _, label in ELAPSED_BINS:
            key = f"{role}:{label}"
            supported = {
                sid: row["elapsed_bins"][key]
                for sid, row in records.items()
                if key in row["elapsed_bins"]
            }
            if not supported:
                continue
            metric_names = next(iter(supported.values()))["metrics"]
            aggregate_bins[key] = {
                "records": len(supported),
                "windows": sum(row["windows"] for row in supported.values()),
                "metrics": {
                    name: math.fsum(row["metrics"][name] for row in supported.values())
                    / len(supported)
                    for name in metric_names
                },
            }
    return {
        "schema": "rx-ds8-alignment/v1",
        "status": "complete",
        "evaluation_sessions": session_ids,
        "records": records,
        "lanes": lane_exports,
        "aggregate_equal_record": {"roles": aggregate_roles, "elapsed_bins": aggregate_bins},
        "interpretation": (
            "Prior-weighted nearest-candidate alignment diagnostic; no fit, nominee selection, "
            "or identity claim."
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
    result = analyze(json.loads(payload), expected_records=4)
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
