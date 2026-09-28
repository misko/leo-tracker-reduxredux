#!/usr/bin/env python3
"""Independent causal-history, replay, and arithmetic audit."""

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ARMS = ("D", "S", "T", "T_swap", "T_reverse", "T_shift")
ROLES = ("reception", "held_frequency")
PERIOD_SETTINGS = (0.2, 500.0, 10.0, 5000.0, 500.0)


def lane_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def wrapped(value, period):
    return (value + period / 2) % period - period / 2


def component_density(points, mean, sigma, period):
    points = np.asarray(points, dtype=float)
    delta = (points - mean + period / 2) % period - period / 2
    ratio = sigma / period
    if ratio < 0.2:
        images = max(1, int(math.ceil(8 * ratio)) + 1)
        offsets = np.arange(-images, images + 1) * period
        values = np.exp(-0.5 * ((delta[:, None] + offsets) / sigma) ** 2).sum(axis=1)
        return period * values / (sigma * math.sqrt(2 * math.pi))
    harmonic = np.arange(1, max(1, int(math.ceil(math.sqrt(
        -math.log(1e-15) / (2 * math.pi**2 * ratio**2)
    )))) + 1)
    coefficient = np.exp(-2 * math.pi**2 * ratio**2 * harmonic**2)
    return 1 + 2 * np.sum(coefficient * np.cos(
        2 * math.pi * delta[:, None] * harmonic / period
    ), axis=1)


def predict(history, time_s, points, period):
    birth, observation_sd, max_age, velocity_sd, acceleration_sd = PERIOD_SETTINGS
    if not history or time_s - history[-1][0] > max_age:
        return np.ones(len(points)), "uniform", []
    last_time, last = history[-1]
    horizon = time_s - last_time
    if len(history) < 2 or time_s - history[-2][0] > max_age:
        sigma = math.hypot(observation_sd, velocity_sd * horizon)
        components = [(value, sigma, 1 / len(last)) for value in last]
        mode = "one_history"
    else:
        previous_time, previous = history[-2]
        gap = last_time - previous_time
        raw = []
        for previous_value in previous:
            for last_value in last:
                velocity = wrapped(last_value - previous_value, period) / gap
                raw.append((last_value + velocity * horizon) % period)
        logs = [-0.5 * (wrapped(last - previous, period) / gap / velocity_sd) ** 2
                for previous in history[-2][1] for last in history[-1][1]]
        peak = max(logs)
        weights = [math.exp(value - peak) for value in logs]
        total = math.fsum(weights)
        ratio = horizon / gap
        sigma = math.sqrt(observation_sd**2 * (1 + ratio**2 + (1 + ratio) ** 2)
                          + (acceleration_sd * horizon) ** 2)
        components = [
            (mean, sigma, weight / total)
            for mean, weight in zip(raw, weights, strict=True)
        ]
        mode = "two_history"
    density = np.full(len(points), birth)
    for mean, sigma, weight in components:
        density += (1 - birth) * weight * component_density(points, mean, sigma, period)
    return density, mode, components


def audit(dataset, transfer, results):
    source = {lane_key(row["lane"]): row for row in dataset["lanes"]
              if row["recording_split"] == "calibration"}
    replay = {row["held_session"]: row for row in transfer["folds"]}
    if len(source) != 12 or len(results["folds"]) != 6:
        raise ValueError("population mismatch")
    reference_gains = {}
    density_values = 0
    mode_counts = {"uniform": 0, "one_history": 0, "two_history": 0}
    for fold in results["folds"]:
        sid = fold["held_session"]
        for arm in ARMS:
            expected = replay[sid]["families"]["within"]["evaluations"][arm]
            if fold["uniform"][arm] != expected:
                raise ValueError("uniform replay mismatch")
        gains = {role: 0.0 for role in ROLES}
        counts = {role: 0 for role in ROLES}
        for lane in fold["causal_frequency_diagnostics"]:
            raw = source[lane_key(lane["lane"])]
            period = float(raw["alias_period_hz"])
            windows = {row["source_window_id"]: row for row in raw["windows"]}
            for receiver_row in lane["receivers"]:
                receiver = receiver_row["receiver"]
                history = []
                last_time = None
                origin_ns = raw["windows"][0]["prediction_utc_ns"]
                for row in receiver_row["windows"]:
                    window = windows[row["source_window_id"]]
                    time_s = (window["prediction_utc_ns"] - origin_ns) / 1e9
                    if last_time is not None and time_s <= last_time:
                        raise ValueError("noncausal timestamp order")
                    points = np.asarray([item["canonical_rx0_hz"] for item in
                                         window["observed"][receiver]]) % period
                    density, mode, _ = predict(history, time_s, points, period)
                    if mode != row["predictor"]["mode"] or not np.allclose(
                        density, row["phase_density"], rtol=0, atol=1e-12
                    ):
                        difference = np.max(np.abs(density - row["phase_density"]), initial=0)
                        raise ValueError(
                            f"causal density reconstruction mismatch: {sid} "
                            f"{row['source_window_id']} {receiver} {mode} {difference}"
                        )
                    gains[window["role"]] += float(np.log(density).sum())
                    counts[window["role"]] += receiver == "rx0"
                    density_values += len(density)
                    mode_counts[mode] += 1
                    if len(points):
                        history.append((time_s, np.asarray(sorted(set(points.tolist())))))
                        history = history[-2:]
                    last_time = time_s
        reference_gains[sid] = {role: gains[role] / counts[role] for role in ROLES}
    aggregates = results["aggregate_equal_record"]
    for role in ROLES:
        exported = aggregates[f"{role}:causal_reference-uniform_reference"]
        records = {sid: values[role] for sid, values in reference_gains.items()}
        if any(not math.isclose(records[sid], exported["records"][sid], abs_tol=1e-10)
               for sid in records):
            raise ValueError("reference gain mismatch")
    for name, aggregate in aggregates.items():
        values = list(aggregate["records"].values())
        if not math.isclose(aggregate["mean"], math.fsum(values) / len(values), abs_tol=1e-12):
            raise ValueError(f"aggregate mean mismatch: {name}")
        if aggregate["positive_records"] != sum(value > 0 for value in values):
            raise ValueError(f"aggregate sign mismatch: {name}")
    return {"schema": "rx-causal-geometry-audit/v1", "status": "pass", "lanes": len(source),
            "folds": len(results["folds"]), "density_values": density_values,
            "predictor_window_modes": mode_counts}


def main():
    parser = argparse.ArgumentParser()
    for name in ("dataset", "transfer", "results", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    payloads = {
        name: getattr(args, name).read_bytes()
        for name in ("dataset", "transfer", "results")
    }
    receipt = audit(*(json.loads(payloads[name]) for name in ("dataset", "transfer", "results")))
    receipt["source_sha256"] = {name: hashlib.sha256(value).hexdigest()
                                for name, value in payloads.items()}
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
