#!/usr/bin/env python3
"""Independent reconstruction audit for the temporal-alignment artifact."""

import argparse
import hashlib
import json
import math
from pathlib import Path

EDGES = (0, 30, 60, 90, 120, 180, math.inf)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lane_key(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def close(left, right, tolerance=1e-12):
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=tolerance)


def label(elapsed):
    for left, right in zip(EDGES[:-1], EDGES[1:], strict=True):
        if left <= elapsed < right:
            return f"{left}-{'infinity' if math.isinf(right) else right}"
    raise ValueError("negative elapsed time")


def nearest(values, prediction, period):
    if not values:
        return math.inf
    return min(abs((value - prediction + period / 2) % period - period / 2) for value in values)


def transfer_map(document):
    output = {}
    for fold in document["folds"]:
        maps = {}
        for arm in ("D", "T"):
            current = {}
            evaluation = fold["families"]["within"]["evaluations"][arm]
            for lane in evaluation["lanes"]:
                for window, presence in zip(lane["windows"], lane["window_presence"], strict=True):
                    current[window["source_window_id"]] = (
                        lane_key(lane["lane"]), window["role"], window["prediction_utc_ns"],
                        float(presence), float(window["relative_log_score"]),
                    )
            maps[arm] = current
        if set(maps["D"]) != set(maps["T"]):
            raise ValueError("D/T transfer populations differ")
        for window_id, d_value in maps["D"].items():
            t_value = maps["T"][window_id]
            if d_value[:3] != t_value[:3] or window_id in output:
                raise ValueError("transfer metadata or uniqueness failure")
            output[window_id] = (fold["held_session"], *d_value[:3], d_value[3], t_value[3],
                                 d_value[4], t_value[4])
    return output


def audit(dataset, transfer, results):
    joined = transfer_map(transfer)
    expected = {}
    origins = {}
    for lane in dataset["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        key = (lane["lane"]["session_id"], lane_key(lane["lane"]))
        reception = [w["prediction_utc_ns"] for w in lane["windows"] if w["role"] == "reception"]
        origins[key] = min(reception)
    for lane in dataset["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        sid = lane["lane"]["session_id"]
        lkey = lane_key(lane["lane"])
        period = float(lane["alias_period_hz"])
        components = lane["components"][:-1]
        logs = [float(component["log_prior"]) for component in components]
        maximum = max(logs)
        denominator = math.fsum(math.exp(value - maximum) for value in logs)
        weights = [math.exp(value - maximum) / denominator for value in logs]
        for window in lane["windows"]:
            wid = window["source_window_id"]
            frozen = joined[wid]
            if frozen[:4] != (sid, lkey, window["role"], window["prediction_utc_ns"]):
                raise ValueError("dataset/transfer join mismatch")
            frequencies = [[float(x["canonical_rx0_hz"]) for x in window["observed"][rx]]
                           for rx in ("rx0", "rx1")]
            values = [[0.0, 0.0], [0.0, 0.0]]
            visible = 0.0
            for weight, component, prediction in zip(
                weights, components, window["predictions"], strict=True
            ):
                component_key = (component["track_id"], component["catalog_number"])
                prediction_key = (prediction["track_id"], prediction["catalog_number"])
                if component_key != prediction_key:
                    raise ValueError("nominee alignment mismatch")
                if not prediction["visible"]:
                    continue
                visible += weight
                for rx in range(2):
                    distance = nearest(
                        frequencies[rx], float(prediction["mu_canonical_rx0_hz"]), period
                    )
                    values[0][rx] += weight * (distance <= 500)
                    values[1][rx] += weight * (distance <= 1500)
            elapsed = (window["prediction_utc_ns"] - origins[(sid, lkey)]) / 1e9
            expected[wid] = {
                "session_id": sid, "lane": lane["lane"], "role": window["role"],
                "prediction_utc_ns": window["prediction_utc_ns"], "elapsed_s": elapsed,
                "elapsed_bin_s": label(elapsed), "candidate_count_rx0": len(frequencies[0]),
                "candidate_count_rx1": len(frequencies[1]), "visible_prior_mass": visible,
                "prior_probability_nearest_le_500hz_rx0": values[0][0],
                "prior_probability_nearest_le_500hz_rx1": values[0][1],
                "prior_probability_nearest_le_1500hz_rx0": values[1][0],
                "prior_probability_nearest_le_1500hz_rx1": values[1][1],
                "D_presence_probability": frozen[4], "T_presence_probability": frozen[5],
                "D_relative_log_score": frozen[6], "T_relative_log_score": frozen[7],
            }
    exported = {row["source_window_id"]: row for row in results["windows"]}
    if set(exported) != set(expected) or len(exported) != len(results["windows"]):
        raise ValueError("result window population mismatch")
    numeric = set(expected[next(iter(expected))]) - {"session_id", "lane", "role", "elapsed_bin_s"}
    for wid, row in expected.items():
        for key, value in row.items():
            if key in numeric:
                if not close(exported[wid][key], value):
                    raise ValueError(f"numeric mismatch: {wid} {key}")
            elif exported[wid][key] != value:
                raise ValueError(f"metadata mismatch: {wid} {key}")
    metrics = [key for key in expected[next(iter(expected))] if key not in
               {"session_id", "lane", "role", "prediction_utc_ns", "elapsed_s", "elapsed_bin_s"}]
    sessions = sorted({row["session_id"] for row in expected.values()})
    for group, aggregate in results["aggregate_equal_record"].items():
        role, bin_name = group.split(":", 1)
        means = {}
        count = 0
        for sid in sessions:
            rows = [row for row in expected.values() if row["session_id"] == sid and
                    row["role"] == role and (bin_name == "all" or row["elapsed_bin_s"] == bin_name)]
            if rows:
                count += len(rows)
                means[sid] = {metric: math.fsum(float(row[metric]) for row in rows) / len(rows)
                              for metric in metrics}
        if count != aggregate["windows"] or len(means) != aggregate["recordings_with_windows"]:
            raise ValueError("aggregate denominator mismatch")
        for sid, values in means.items():
            for metric, value in values.items():
                if not close(value, aggregate["record_means"][sid][metric]):
                    raise ValueError("record mean mismatch")
        for metric in metrics:
            value = None if not means else math.fsum(x[metric] for x in means.values()) / len(means)
            exported_value = aggregate["equal_record_mean"][metric]
            if value is None and exported_value is None:
                continue
            if not close(value, exported_value):
                raise ValueError("equal-record mean mismatch")
    return {"schema": "rx-temporal-alignment-audit/v1", "status": "pass",
            "windows": len(expected), "recordings": len(sessions),
            "reception_windows": sum(x["role"] == "reception" for x in expected.values()),
            "held_frequency_windows": sum(x["role"] == "held_frequency" for x in expected.values())}


def main():
    parser = argparse.ArgumentParser()
    for name in ("dataset", "transfer", "results", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    receipt = audit(json.loads(args.dataset.read_text()), json.loads(args.transfer.read_text()),
                    json.loads(args.results.read_text()))
    receipt["source_sha256"] = {name: digest(getattr(args, name))
                                for name in ("dataset", "transfer", "results")}
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    main()
