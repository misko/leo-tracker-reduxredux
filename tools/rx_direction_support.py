"""Audit forecast-only support for candidate-specific receiver crossing order."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

SIN10 = math.sin(math.radians(10.0))
COS10 = math.cos(math.radians(10.0))


def _unique_interior_maximum(values: np.ndarray) -> tuple[int | None, str | None]:
    maximum = float(np.max(values))
    indices = np.flatnonzero(values == maximum)
    if len(indices) != 1:
        return None, "tied_scheduled_peak"
    index = int(indices[0])
    if index in (0, len(values) - 1):
        return None, "boundary_scheduled_peak"
    return index, None


def _zero_crossing(times: np.ndarray, q: np.ndarray):
    zero = np.flatnonzero(q == 0)
    if len(zero) > 1 and np.any(np.diff(zero) == 1):
        return None, None, None, "zero_plateau"
    events = []
    for raw_index in zero:
        index = int(raw_index)
        if index not in (0, len(q) - 1) and q[index - 1] * q[index + 1] < 0:
            slope = (q[index + 1] - q[index - 1]) / (times[index + 1] - times[index - 1])
            events.append((float(times[index]), float(slope), (index - 1, index, index + 1)))
    for raw_index in np.flatnonzero(q[:-1] * q[1:] < 0):
        index = int(raw_index)
        delta_t = times[index + 1] - times[index]
        slope = (q[index + 1] - q[index]) / delta_t
        crossing = times[index] - q[index] / slope
        events.append((float(crossing), float(slope), (index, index + 1)))
    if len(events) != 1:
        return None, None, None, "no_unique_linear_zero_crossing"
    crossing, slope, indices = events[0]
    return crossing, slope, indices, None


def nominee_support(times, east, up, visible=None):
    """Return conventional nominal crossing support on irregular scheduled times."""
    raw_times = np.asarray(times)
    if raw_times.ndim != 1 or not np.issubdtype(raw_times.dtype, np.number):
        raise ValueError("times must be a numeric vector")
    if not np.all(np.equal(raw_times, np.floor(raw_times))):
        raise ValueError("prediction times must be integer nanoseconds")
    integer_times = raw_times.astype(np.int64)
    times = (integer_times - integer_times[0]).astype(float) / 1e9
    east = np.asarray(east, dtype=float)
    up = np.asarray(up, dtype=float)
    if (
        len(times) < 3
        or east.shape != times.shape
        or up.shape != times.shape
        or not np.all(np.isfinite(times))
        or not np.all(np.isfinite(east))
        or not np.all(np.isfinite(up))
        or np.any(np.diff(times) <= 0)
    ):
        raise ValueError("nominee support requires finite, strictly ordered arrays")
    visibility = np.ones(len(times), dtype=bool) if visible is None else np.asarray(visible)
    if visibility.shape != times.shape or visibility.dtype != bool:
        raise ValueError("visibility must be a boolean vector")
    q = 2.0 * SIN10 * east
    rx0 = -SIN10 * east + COS10 * up
    rx1 = SIN10 * east + COS10 * up
    crossing, slope, crossing_indices, crossing_reason = _zero_crossing(times, q)
    peak0, reason0 = _unique_interior_maximum(rx0)
    peak1, reason1 = _unique_interior_maximum(rx1)
    reason = crossing_reason or reason0 or reason1
    crossing_visible = (
        None
        if crossing_indices is None
        else bool(np.all(visibility[list(crossing_indices)]))
    )
    rx0_peak_visible = None if peak0 is None else bool(visibility[peak0])
    rx1_peak_visible = None if peak1 is None else bool(visibility[peak1])
    if reason is None and not crossing_visible:
        reason = "crossing_bracket_not_visible"
    if reason is None and (not rx0_peak_visible or not rx1_peak_visible):
        reason = "scheduled_peak_not_visible"
    order = "unavailable"
    if reason is None:
        delta = float(times[peak1] - times[peak0])
        if delta == 0:
            reason = "simultaneous_scheduled_peaks"
        elif slope == 0 or delta * slope <= 0:
            reason = "peak_order_disagrees_with_crossing_slope"
        else:
            order = "rx0_before_rx1" if delta > 0 else "rx1_before_rx0"
    return {
        "order": order,
        "unavailable_reason": reason,
        "crossing_time_utc_ns": (
            None if crossing is None else float(integer_times[0] + crossing * 1e9)
        ),
        "crossing_slope_per_s": slope,
        "rx0_peak_time_utc_ns": None if peak0 is None else int(integer_times[peak0]),
        "rx1_peak_time_utc_ns": None if peak1 is None else int(integer_times[peak1]),
        "crossing_event_visible": crossing_visible,
        "rx0_peak_visible": rx0_peak_visible,
        "rx1_peak_visible": rx1_peak_visible,
        "q_min": float(np.min(q)),
        "q_max": float(np.max(q)),
        "q_first": float(q[0]),
        "q_last": float(q[-1]),
        "q_overall_secant_per_s": float((q[-1] - q[0]) / (times[-1] - times[0])),
        "scheduled_points": len(times),
        "visible_scheduled_points": int(visibility.sum()),
        "visible_fraction": float(visibility.mean()),
    }


def analyze(document):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported geometry dataset")
    output = []
    for lane in document.get("lanes", []):
        windows = sorted(lane.get("windows", []), key=lambda row: row["prediction_utc_ns"])
        times = np.asarray([row["prediction_utc_ns"] for row in windows], dtype=np.int64)
        if len(times) < 3 or np.any(np.diff(times) <= 0):
            raise ValueError("lane windows must have distinct increasing prediction times")
        raw_components = lane.get("components", [])
        if (
            not raw_components
            or raw_components[-1].get("kind") != "other"
            or sum(row.get("kind") == "other" for row in raw_components) != 1
            or any(row.get("kind") != "track_candidate" for row in raw_components[:-1])
        ):
            raise ValueError("lane must end with exactly one other component")
        components = [
            row
            for row in raw_components
            if row.get("kind") == "track_candidate"
        ]
        if not components:
            raise ValueError("lane has no track candidates")
        keys = [(row["track_id"], int(row["catalog_number"])) for row in components]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate track-catalog component key")
        expected_keys = set(keys)
        for window in windows:
            actual_keys = [
                (row["track_id"], int(row["catalog_number"]))
                for row in window.get("predictions", [])
            ]
            if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != expected_keys:
                raise ValueError("prediction key set does not exactly match components")
        log_priors = np.asarray(
            [
                -np.inf if row.get("log_prior") is None else float(row["log_prior"])
                for row in components
            ]
        )
        if (
            np.any(np.isnan(log_priors))
            or np.any(log_priors == np.inf)
            or not np.any(np.isfinite(log_priors))
        ):
            raise ValueError("candidate priors must contain finite nonnegative mass")
        normalization = float(logsumexp(log_priors))
        normalized = log_priors - normalization
        nominees = []
        for component, normalized_log_prior in zip(components, normalized, strict=True):
            key = (component["track_id"], int(component["catalog_number"]))
            east, up, visible = [], [], []
            for window in windows:
                matches = [
                    row for row in window.get("predictions", [])
                    if (row["track_id"], int(row["catalog_number"])) == key
                ]
                if len(matches) != 1:
                    raise ValueError(f"prediction membership mismatch for {key}")
                east.append(float(matches[0]["los_enu_unit"]["east"]))
                up.append(float(matches[0]["los_enu_unit"]["up"]))
                if not isinstance(matches[0].get("visible"), bool):
                    raise ValueError("prediction visibility must be boolean")
                visible.append(matches[0]["visible"])
            support = nominee_support(times, east, up, visible)
            nominees.append(
                {
                    "track_id": key[0],
                    "catalog_number": key[1],
                    "rank": component.get("rank"),
                    "log_prior": (
                        None if not math.isfinite(log_priors[len(nominees)])
                        else float(log_priors[len(nominees)])
                    ),
                    "normalized_log_prior": (
                        None if not math.isfinite(normalized_log_prior)
                        else float(normalized_log_prior)
                    ),
                    "prior": math.exp(float(normalized_log_prior)),
                    **support,
                }
            )
        masses = {}
        for order in ("rx0_before_rx1", "rx1_before_rx0", "unavailable"):
            selected = [
                row["normalized_log_prior"]
                for row in nominees
                if row["order"] == order and row["normalized_log_prior"] is not None
            ]
            masses[order] = 0.0 if not selected else math.exp(float(logsumexp(selected)))
        probabilities = np.exp(normalized)
        positive = probabilities > 0
        entropy = -float(np.sum(probabilities[positive] * normalized[positive]))
        output.append(
            {
                "lane": lane["lane"],
                "recording_split": lane.get("recording_split"),
                "roles": sorted({row["role"] for row in windows}),
                "windows": len(windows),
                "nominees": nominees,
                "nominee_count": len(nominees),
                "prior_entropy_nats": entropy,
                "prior_effective_count": math.exp(entropy),
                "order_mass": masses,
                "pair_disagreement_mass": 2.0
                * masses["rx0_before_rx1"]
                * masses["rx1_before_rx0"],
            }
        )
    return {
        "schema": "rx-direction-support/v1",
        "status": "complete",
        "lanes": output,
        "accounting": {
            "lanes": len(output),
            "nominees": sum(row["nominee_count"] for row in output),
            "positive_disagreement_lanes": sum(row["pair_disagreement_mass"] > 0 for row in output),
        },
        "interpretation": "Forecast-only nominal convention support; no detector outcomes or fit.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = analyze(json.loads(payload))
    result["source_sha256"] = {"dataset": hashlib.sha256(payload).hexdigest()}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
