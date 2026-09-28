#!/usr/bin/env python3
"""Independent reconstruction audit for frozen residual trajectories."""

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path

ROLES = ("reception", "held_frequency")


def wrapped(value, period):
    return (value + period / 2) % period - period / 2


def close(left, right, tolerance=1e-10):
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=tolerance)


def nearest(candidates, forecast, period):
    if not candidates:
        return None
    residuals = [wrapped(float(row["canonical_rx0_hz"]) - forecast, period) for row in candidates]
    index = min(range(len(residuals)), key=lambda value: (abs(residuals[value]), value))
    return index, residuals[index]


def audit(dataset, results):
    calibration = [row for row in dataset["lanes"] if row["recording_split"] == "calibration"]
    if len(calibration) != 12 or len(results["lanes"]) != 12:
        raise ValueError("lane population mismatch")
    source = {json.dumps(row["lane"], sort_keys=True): row for row in calibration}
    checked_windows = set()
    nominee_receivers = 0
    boundary_pairs = 0
    for exported_lane in results["lanes"]:
        lane = source[json.dumps(exported_lane["lane"], sort_keys=True)]
        period = float(lane["alias_period_hz"])
        components = lane["components"][:-1]
        logs = [float(row["log_prior"]) if row["log_prior"] is not None else -math.inf
                for row in components]
        peak = max(logs)
        total = math.fsum(math.exp(value - peak) for value in logs)
        probabilities = [math.exp(value - peak) / total for value in logs]
        if len(exported_lane["nominees"]) != len(components):
            raise ValueError("nominee population mismatch")
        for index, nominee in enumerate(exported_lane["nominees"]):
            component = components[index]
            if (nominee["track_id"], nominee["catalog_number"]) != (
                component["track_id"], component["catalog_number"]
            ) or not close(nominee["prior_probability"], probabilities[index]):
                raise ValueError("nominee identity or prior mismatch")
            for receiver_index, receiver in enumerate(nominee["receivers"]):
                nominee_receivers += 1
                name = f"rx{receiver_index}"
                expected = []
                for window, exported in zip(lane["windows"], receiver["windows"], strict=True):
                    prediction = window["predictions"][index]
                    forecast = float(prediction["mu_canonical_rx0_hz"])
                    found = nearest(window["observed"][name], forecast, period)
                    if exported["source_window_id"] != window["source_window_id"]:
                        raise ValueError("window order mismatch")
                    if index == 0 and receiver_index == 0:
                        if window["source_window_id"] in checked_windows:
                            raise ValueError("duplicate source window")
                        checked_windows.add(window["source_window_id"])
                    if found is None:
                        if exported["nearest"] is not None:
                            raise ValueError("empty candidate mismatch")
                    else:
                        candidate_index, residual = found
                        got = exported["nearest"]
                        if got["candidate_index"] != candidate_index or not close(
                            got["signed_residual_hz"], residual
                        ):
                            raise ValueError("nearest residual mismatch")
                    expected.append(exported)
                for previous, current, step in zip(
                    expected[:-1], expected[1:], receiver["adjacent_steps"], strict=True
                ):
                    elapsed_step = current["elapsed_s"] - previous["elapsed_s"]
                    if not close(step["elapsed_step_s"], elapsed_step):
                        raise ValueError("step-time mismatch")
                    forecast_step = wrapped(
                        current["forecast_frequency_hz"] - previous["forecast_frequency_hz"], period
                    )
                    if not close(step["forecast_step_hz"], forecast_step):
                        raise ValueError("forecast-step mismatch")
                reception = [row for row in expected if row["role"] == "reception"]
                held = [row for row in expected if row["role"] == "held_frequency"]
                boundary = receiver["role_boundary"]
                if (boundary["last_reception_source_window_id"] != reception[-1]["source_window_id"]
                        or boundary["first_held_source_window_id"] != held[0]["source_window_id"]):
                    raise ValueError("boundary identity mismatch")
                boundary_pairs += 1
                for role, rows in (("reception", reception), ("held_frequency", held)):
                    stats = receiver["role_stats"][role]
                    observed = [row for row in rows if row["nearest"] is not None]
                    residuals = [row["nearest"]["signed_residual_hz"] for row in observed]
                    if stats["windows"] != len(rows) or stats["observed_windows"] != len(observed):
                        raise ValueError("role denominator mismatch")
                    signed = statistics.median(residuals) if residuals else None
                    absolute = (
                        statistics.median(abs(value) for value in residuals)
                        if residuals
                        else None
                    )
                    signed_ok = close(stats["median_signed_residual_hz_given_observed"], signed)
                    absolute_ok = close(
                        stats["median_absolute_residual_hz_given_observed"], absolute
                    )
                    if not signed_ok or not absolute_ok:
                        raise ValueError("role median mismatch")
                    for threshold in (500, 1500):
                        fraction = sum(
                            row["visible"] and row["nearest"] is not None
                            and row["nearest"]["absolute_residual_hz"] <= threshold for row in rows
                        ) / len(rows)
                        if not close(stats[f"within_{threshold}hz_fraction"], fraction):
                            raise ValueError("role alignment mismatch")
    return {"schema": "rx-residual-trajectories-audit/v1", "status": "pass",
            "lanes": len(calibration), "source_windows": len(checked_windows),
            "nominee_receiver_series": nominee_receivers, "boundary_pairs": boundary_pairs}


def main():
    parser = argparse.ArgumentParser()
    for name in ("dataset", "results", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    dataset_bytes, result_bytes = args.dataset.read_bytes(), args.results.read_bytes()
    receipt = audit(json.loads(dataset_bytes), json.loads(result_bytes))
    receipt["source_sha256"] = {
        "dataset": hashlib.sha256(dataset_bytes).hexdigest(),
        "results": hashlib.sha256(result_bytes).hexdigest(),
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
