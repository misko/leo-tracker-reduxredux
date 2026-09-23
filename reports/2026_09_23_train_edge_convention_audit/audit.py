#!/usr/bin/env python3
"""Audit edge/CFO conventions and edge-time confounding on sealed TRAIN pairs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PAIRS = ROOT / "reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.json"
METADATA = Path("/tmp/leo-train-rx-metadata.json")
RATE = 2_500_000
SOURCE_PATHS = {
    "pilot_methods": ROOT / "src/leo/analysis/starlink/pilot_methods.py",
    "templates": ROOT / "src/leo/analysis/starlink/templates.py",
    "candidate_projection": ROOT / "src/leo/application/persistent_hop_trajectory.py",
    "trajectory_projection": ROOT / "src/leo/analysis/persistent_hop_trajectory.py",
}


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_score(
    edge,
    cfo_hz,
    rate_hz_s=0.0,
    sample_count=50_000,
    epoch=37,
    time_offset_s=0.0,
    acquired_seed_hz=None,
):
    samples = np.zeros(sample_count, dtype=np.complex128)
    template = qin_edge_pilot_frame(RATE, edge)
    frame = 0
    while True:
        start = epoch + round(frame * RATE / FRAME_RATE_HZ)
        if start + len(template) > len(samples):
            break
        indexes = np.arange(start, start + len(template))
        times = time_offset_s + indexes / RATE
        phase = 2 * np.pi * (cfo_hz * times + 0.5 * rate_hz_s * times**2)
        samples[start : start + len(template)] += template * np.exp(1j * phase)
        frame += 1
    seed = cfo_hz if acquired_seed_hz is None else acquired_seed_hz
    result = conditioned_glrt64_score(
        samples,
        RATE,
        epoch_sample=epoch,
        acquired_cfo_hz=seed,
        edge=edge,
    )
    return {
        "edge": edge,
        "injected_start_cfo_hz": cfo_hz,
        "injected_rate_hz_s": rate_hz_s,
        "time_offset_s": time_offset_s,
        "acquired_seed_hz": seed,
        "tracking_cfo_hz": result.tracking_cfo_hz,
        "residual_cfo_hz": result.residual_cfo_hz,
        "margin": result.margin,
    }


def time_summary(pairs, metadata):
    sessions = {row["session_id"]: row for row in metadata["sessions"]}
    rows = []
    for pair in pairs:
        recovered = {r["track_id"]: r for r in sessions[pair["session_id"]]["tracks"]}
        left, right = recovered[pair["rx0_track_id"]], recovered[pair["rx1_track_id"]]
        midpoint_ns = (
            max(left["support_start_utc_ns"], right["support_start_utc_ns"])
            + min(left["support_end_utc_ns"], right["support_end_utc_ns"])
        ) / 2
        edge = pair["lane"].split("/")[1]
        rows.append(
            {
                "edge": edge,
                "midpoint_utc_ns": midpoint_ns,
                "session_id": pair["session_id"],
                "differential_slope_hz_s": pair["differential_slope_hz_s"],
            }
        )
    values = {
        edge: np.asarray([r["midpoint_utc_ns"] for r in rows if r["edge"] == edge]) / 1e9
        for edge in ("lower", "upper")
    }
    pooled_sd = np.sqrt((np.var(values["lower"]) + np.var(values["upper"])) / 2)
    boundaries = np.quantile(np.concatenate(tuple(values.values())), [0.25, 0.5, 0.75])
    quartiles = Counter()
    for row in rows:
        quartile = int(np.searchsorted(boundaries, row["midpoint_utc_ns"] / 1e9, side="right") + 1)
        quartiles[(quartile, row["edge"])] += 1
    common_sessions = sorted(
        {r["session_id"] for r in rows if r["edge"] == "lower"}
        & {r["session_id"] for r in rows if r["edge"] == "upper"}
    )
    within = []
    for sid in common_sessions:
        lower = [
            r["differential_slope_hz_s"]
            for r in rows
            if r["session_id"] == sid and r["edge"] == "lower"
        ]
        upper = [
            r["differential_slope_hz_s"]
            for r in rows
            if r["session_id"] == sid and r["edge"] == "upper"
        ]
        within.append(float(np.mean(lower) - np.mean(upper)))
    return {
        "edge": {
            edge: {
                "pair_count": len(value),
                "minimum_utc_s": float(value.min()),
                "median_utc_s": float(np.median(value)),
                "maximum_utc_s": float(value.max()),
            }
            for edge, value in values.items()
        },
        "absolute_time_standardized_mean_difference_lower_minus_upper": float(
            (np.mean(values["lower"]) - np.mean(values["upper"])) / pooled_sd
        ),
        "absolute_time_quartile_counts": {
            str(q): {edge: quartiles[(q, edge)] for edge in ("lower", "upper")} for q in range(1, 5)
        },
        "sessions_with_both_edges": len(common_sessions),
        "within_session_lower_minus_upper_slope_hz_s": {
            "mean": float(np.mean(within)),
            "median": float(np.median(within)),
            "count": len(within),
            "minimum": float(np.min(within)),
            "maximum": float(np.max(within)),
        },
    }


def main():
    sealed, metadata = json.loads(PAIRS.read_text()), json.loads(METADATA.read_text())
    synthetic = [
        synthetic_score(edge, cfo, rate, time_offset_s=offset, acquired_seed_hz=seed)
        for edge in ("lower", "upper")
        for cfo, rate, offset, seed in (
            (42_000.0, 0.0, 0.0, 40_500.0),
            (-42_000.0, 0.0, 0.0, -40_500.0),
            (40_000.0, -1_800.0, 0.0, 40_000.0),
            (40_000.0, -1_800.0, 1.0, 40_000.0),
        )
    ]
    result = {
        "schema": "leo.train_edge_convention_audit.v1",
        "synthetic": synthetic,
        "time_confounding": time_summary(sealed["pairs"], metadata),
        "source_findings": {
            "glrt_projection": "tracking_cfo_hz = acquired_cfo_hz + residual_cfo_hz for both edges",
            "edge_selection": "edge changes the QIN pilot bins/template, not CFO sign",
            "rf_projection": (
                "actual_rf_hz = target.rf_center_hz - actual_if_offset_hz for both edges"
            ),
            "trajectory_projection": (
                "measured_cfo_hz is multiplied by positive canonical_rf_hz/actual_rf_hz"
            ),
        },
        "bindings": {
            "tool": digest(Path(__file__)),
            "sealed_pairs": digest(PAIRS),
            "metadata": digest(METADATA),
            "production_sources": {key: digest(path) for key, path in SOURCE_PATHS.items()},
        },
        "validation_or_test_used": False,
        "reference_coordinate_used": False,
        "position_refit_performed": False,
    }
    output = HERE / "results"
    output.mkdir(exist_ok=False)
    path = output / "audit.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":", 1)[1] + "\n")


if __name__ == "__main__":
    main()
