#!/usr/bin/env python3
"""Post-fit, no-refit null and concentration audit for the geometry pilot."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from tools.rx_geometry_fit import evaluate, lane_loglik, prepare, signal_arrays


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def clutter_window_log_density(
    counts: tuple[int, int], lambdas: np.ndarray, period: float
) -> float:
    """Poisson-process set density for two zero-signal receiver views."""
    values = -lambdas + np.asarray(counts, dtype=float) * np.log(lambdas / period)
    return float(values.sum())


def clutter_evaluation(dataset: dict, lambdas: np.ndarray) -> dict:
    recordings: dict[str, dict[str, float | int]] = {}
    for lane in dataset["lanes"]:
        if lane["recording_split"] != "evaluation":
            continue
        sid = lane["lane"]["session_id"]
        row = recordings.setdefault(sid, {"held_windows": 0, "held_log_score": 0.0})
        for window in lane["windows"]:
            if window["role"] != "held_frequency":
                continue
            counts = tuple(len(window["observed"][key]) for key in ("rx0", "rx1"))
            row["held_windows"] += 1
            row["held_log_score"] += clutter_window_log_density(
                counts, lambdas, float(lane["alias_period_hz"])
            )
    for row in recordings.values():
        row["log_score_per_window"] = row["held_log_score"] / row["held_windows"]
    return {
        "recordings": recordings,
        "equal_record_mean_log_score": float(
            np.mean([row["log_score_per_window"] for row in recordings.values()])
        ),
    }


def fixed_prior_evaluation(lanes: list[dict], beta: np.ndarray, lambdas: np.ndarray) -> dict:
    """Score held windows against the unchanged training mixture, without filtering."""
    recordings: dict[str, dict[str, float | int]] = {}
    for lane in lanes:
        source = lane["source"]
        if source["recording_split"] != "evaluation":
            continue
        prior = lane["prior"] - logsumexp(lane["prior"])
        likelihood = lane_loglik(lane, beta, lambdas)
        held = lane["roles"] == "held_frequency"
        scores = logsumexp(likelihood[held] + prior[None, :], axis=1)
        sid = source["lane"]["session_id"]
        row = recordings.setdefault(sid, {"held_windows": 0, "held_log_score": 0.0})
        row["held_windows"] += int(held.sum())
        row["held_log_score"] += float(scores.sum())
    for row in recordings.values():
        row["log_score_per_window"] = row["held_log_score"] / row["held_windows"]
    return {
        "recordings": recordings,
        "equal_record_mean_log_score": float(
            np.mean([row["log_score_per_window"] for row in recordings.values()])
        ),
    }


def contrast(left: dict, right: dict) -> dict:
    per_record = {
        sid: left["recordings"][sid]["log_score_per_window"]
        - right["recordings"][sid]["log_score_per_window"]
        for sid in left["recordings"]
    }
    return {
        "per_record": per_record,
        "equal_record_mean": float(np.mean(list(per_record.values()))),
        "positive_records": sum(value > 0 for value in per_record.values()),
    }


def concentration(decomposition: dict) -> dict:
    by_arm = {
        arm: {tuple(sorted(row["lane"].items())): row for row in value["lane_scores"]}
        for arm, value in decomposition["evaluations"].items()
        if arm in {"D", "S"}
    }
    by_record: dict[str, list[float]] = defaultdict(list)
    for key, s_row in by_arm["S"].items():
        d_row = by_arm["D"][key]
        sid = dict(key)["session_id"]
        by_record[sid].extend(
            left - right
            for left, right in zip(
                s_row["full_window_log_scores"], d_row["full_window_log_scores"], strict=True
            )
        )

    def reduced(values: list[float], drop_each_tail: int) -> float:
        ordered = sorted(values)
        selected = ordered[drop_each_tail : len(ordered) - drop_each_tail]
        return float(np.mean(selected))

    records = {}
    for sid, values in by_record.items():
        array = np.asarray(values)
        order = np.argsort(np.abs(array))[::-1]
        records[sid] = {
            "windows": len(values),
            "mean": float(array.mean()),
            "median": float(np.median(array)),
            "positive_windows": int(np.sum(array > 0)),
            "negative_windows": int(np.sum(array < 0)),
            "zero_windows": int(np.sum(array == 0)),
            "symmetric_trim_1pct_mean": reduced(values, max(1, len(values) // 100)),
            "drop_largest_absolute_1_mean": float(np.delete(array, order[:1]).mean()),
            "drop_largest_absolute_5_mean": float(np.delete(array, order[:5]).mean()),
            "largest_absolute_contributions": array[order[:10]].tolist(),
        }
    return {
        "records": records,
        "equal_record_mean": float(np.mean([row["mean"] for row in records.values()])),
        "equal_record_trim_1pct_mean": float(
            np.mean([row["symmetric_trim_1pct_mean"] for row in records.values()])
        ),
        "equal_record_drop_largest_absolute_1_mean": float(
            np.mean([row["drop_largest_absolute_1_mean"] for row in records.values()])
        ),
        "equal_record_drop_largest_absolute_5_mean": float(
            np.mean([row["drop_largest_absolute_5_mean"] for row in records.values()])
        ),
    }


def build(dataset: dict, results: dict, decomposition: dict) -> dict:
    lanes, center, scale = prepare(dataset)
    if not np.array_equal(center, np.asarray(results["feature_center"])):
        raise ValueError("feature center changed")
    if not np.array_equal(scale, np.asarray(results["feature_scale"])):
        raise ValueError("feature scale changed")
    signal_arrays(lanes, float(results["sigma_hz"]))
    lambdas = np.asarray(results["clutter_intensities"], dtype=float)
    d_beta = np.asarray(results["fits"]["D"]["parameters"], dtype=float)
    s_beta = np.asarray(results["fits"]["S"]["parameters"], dtype=float)
    elevation_beta = s_beta.copy()
    elevation_beta[4:6] = 0.0

    clutter = clutter_evaluation(dataset, lambdas)
    d = results["evaluations"]["D"]
    s = results["evaluations"]["S"]
    elevation = evaluate(lanes, elevation_beta, lambdas, center, scale)
    fixed_d = fixed_prior_evaluation(lanes, d_beta, lambdas)
    fixed_s = fixed_prior_evaluation(lanes, s_beta, lambdas)
    return {
        "schema": "rx-geometry-null-audit/v1",
        "status": "complete",
        "method": {
            "clutter": "zero signal; frozen RX intensities; uniform circle set density",
            "elevation_only": "frozen S coefficients with north/east set to zero; no refit",
            "fixed_prior": "each held window scored from unchanged training mixture; no updates",
            "concentration": "paired S-minus-D primary one-step held scores",
        },
        "scores": {
            "clutter": clutter,
            "D": d,
            "S": s,
            "elevation_only": elevation,
            "fixed_prior_D": fixed_d,
            "fixed_prior_S": fixed_s,
        },
        "contrasts": {
            "D_minus_clutter": contrast(d, clutter),
            "S_minus_clutter": contrast(s, clutter),
            "S_minus_D": contrast(s, d),
            "S_minus_elevation_only": contrast(s, elevation),
            "elevation_only_minus_D": contrast(elevation, d),
            "fixed_prior_S_minus_D": contrast(fixed_s, fixed_d),
        },
        "s_minus_d_concentration": concentration(decomposition),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--decomposition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payloads = {name: path.read_bytes() for name, path in vars(args).items() if name != "output"}
    report = build(
        *(json.loads(payloads[name]) for name in ("dataset", "results", "decomposition"))
    )
    report["source_sha256"] = {name: digest(value) for name, value in payloads.items()}
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
