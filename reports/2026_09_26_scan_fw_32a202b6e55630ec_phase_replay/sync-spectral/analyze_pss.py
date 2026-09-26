#!/usr/bin/env python3
"""Leakage-safe held-frame PSS carrier and timing diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def wrap(values: np.ndarray, period: float) -> np.ndarray:
    return (values + period / 2) % period - period / 2


def weighted_line(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    design = np.column_stack((x - np.mean(x), np.ones(x.size)))
    return np.linalg.lstsq(design * np.sqrt(weights)[:, None], y * np.sqrt(weights), rcond=None)[0]


def score_lane(windows: list[dict], policy: str) -> dict | None:
    if len(windows) < 8:
        return None
    times = np.asarray([w["fractional_global_device_sample"] / 10_000_000 for w in windows])
    phases = np.asarray([w["correlation_phase_cycles"] for w in windows])
    timing = np.asarray([w["frame_phase_samples"] for w in windows])
    scores = np.asarray([w["peak_to_local_median"] for w in windows])
    train = np.arange(times.size) % 2 == 0
    held = ~train
    center = float(np.mean(times[train]))
    tx = times - center
    unwrapped = np.unwrap(2 * np.pi * phases) / (2 * np.pi)
    if policy == "equal":
        weights = np.ones(times.size)
    elif policy == "score":
        weights = np.minimum(scores, np.median(scores[train]) * 4)
    elif policy == "robust":
        initial = weighted_line(tx[train], unwrapped[train], np.ones(np.count_nonzero(train)))
        residual = unwrapped[train] - (initial[0] * tx[train] + initial[1])
        scale = max(float(np.median(np.abs(residual - np.median(residual))) / 0.67449), 1e-6)
        weights = np.ones(times.size)
        weights[train] = np.minimum(1, 1.345 * scale / np.maximum(np.abs(residual), 1e-12))
    else:
        raise ValueError(policy)
    carrier = weighted_line(tx[train], unwrapped[train], weights[train])
    carrier_error = wrap(unwrapped[held] - (carrier[0] * tx[held] + carrier[1]), 1.0)
    period = 10_000_000 / 750
    timing_center = float(np.median(timing[train]))
    timing_residual = wrap(timing - timing_center, period) / 10_000_000
    timing_fit = weighted_line(tx[train], timing_residual[train], weights[train])
    timing_error = timing_residual[held] - (timing_fit[0] * tx[held] + timing_fit[1])
    increments = wrap(np.diff(phases), 1.0)
    return {
        "frame_count": len(windows),
        "train_count": int(np.count_nonzero(train)),
        "held_count": int(np.count_nonzero(held)),
        "carrier_frequency_residual_hz": float(carrier[0]),
        "carrier_held_rms_cycles": float(np.sqrt(np.mean(carrier_error**2))),
        "carrier_increment_concentration": float(abs(np.mean(np.exp(2j * np.pi * increments)))),
        "timing_rate_s_s": float(timing_fit[0]),
        "timing_held_rms_ns": float(np.sqrt(np.mean(timing_error**2)) * 1e9),
    }


def run(source: Path, output: Path) -> None:
    rows = []
    for line in source.read_text().splitlines():
        visit = json.loads(line)
        for rx in visit["results"]:
            for lane in ("independent_blind", "glrt_conditioned", "independent_sss"):
                result = rx[lane]
                if not result or not result["windows"]:
                    continue
                candidate = result["candidates"][0]["candidate_index"]
                windows = [w for w in result["windows"] if w["candidate_index"] == candidate]
                for policy in ("equal", "score", "robust"):
                    scored = score_lane(windows, policy)
                    if scored:
                        rows.append(
                            {
                                "schema": "scan-pss-held-phase/v1",
                                "visit_index": visit["visit_index"],
                                "split": visit["split"],
                                "receiver_id": rx["receiver_id"],
                                "lane": lane,
                                "weight_policy": policy,
                                **scored,
                            }
                        )
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    summary = {}
    for split in ("development", "evaluation"):
        for lane in ("independent_blind", "glrt_conditioned", "independent_sss"):
            for policy in ("equal", "score", "robust"):
                chosen = [
                    r
                    for r in rows
                    if r["split"] == split
                    and r["lane"] == lane
                    and r["weight_policy"] == policy
                ]
                key = f"{split}:{lane}:{policy}"
                summary[key] = {"count": len(chosen)}
                for field in (
                    "carrier_held_rms_cycles",
                    "carrier_increment_concentration",
                    "timing_held_rms_ns",
                ):
                    summary[key][f"median_{field}"] = (
                        float(np.median([r[field] for r in chosen])) if chosen else None
                    )
    output.with_suffix(".summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)


if __name__ == "__main__":
    main()
