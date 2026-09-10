#!/usr/bin/env python3
"""Separate known-increment error, cubic consistency, and acquisition coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from evaluate_scan_glrt_rms import bootstrap_scan_ratio, rms, write_json
from evaluate_scan_glrt_stride import polynomial_prediction
from replay_scan_glrt_search import FFT_SIZES, alias_difference


def conditional_match(row):
    """Association to the original track is a coverage diagnostic, not truth."""
    eligible = [
        c
        for c in row["candidates"]
        if c["fractional_cfo_hz"] is not None
        and c["fractional_margin"] >= 0.025
        and c["epoch_distance_to_original_samples"] <= 2
        and abs(alias_difference(c["fractional_cfo_hz"] - row["original_cfo_hz"])) <= 2500
    ]
    return max(eligible, key=lambda c: c["fractional_exact_score"]) if eligible else None


def common_metrics(rows, baseline):
    t = np.array([r["t_s"] for r in rows])
    y = np.array([r["y_hz"] for r in rows])
    bt = np.array([r["t_s"] for r in baseline])
    by = np.array([r["y_hz"] for r in baseline])
    fold = np.floor((bt - min(bt)) / 3).astype(int) % 5
    pred = np.zeros(len(t))
    pred_baseline = np.zeros(len(t))
    for f in np.unique(fold):
        training, testing = fold != f, fold == f
        pred[testing] = polynomial_prediction(
            t[training], y[training], t[testing], np.ones(sum(training))
        )
        pred_baseline[testing] = polynomial_prediction(
            t[training], y[training], bt[testing], np.ones(sum(training))
        )
    return {
        "self_block_rms_hz": rms(y - pred),
        "baseline_target_block_rms_hz": rms(by - pred_baseline),
        "self_full_rms_hz": rms(y - polynomial_prediction(t, y, t, np.ones(len(t)))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    glrt = [json.loads(p.read_text()) for p in sorted((args.output / "glrt").glob("*.json"))]
    acq = [json.loads(p.read_text()) for p in sorted((args.output / "acquisition").glob("*.json"))]
    if len(glrt) != 12 or len(acq) != 12:
        raise ValueError("all twelve scan artifacts from each replay are required")
    profiles = sorted({r["profile"] for d in glrt for r in d["rows"]})
    track_rows, increment_rows = [], []
    for d in glrt:
        by_profile = {
            name: {r["index"]: r for r in d["rows"] if r["profile"] == name and "y_hz" in r}
            for name in profiles
        }
        indexes = sorted(set.intersection(*(set(v) for v in by_profile.values())))
        baseline = [by_profile["fft_512"][i] for i in indexes]
        for name, points in by_profile.items():
            group = [r for r in d["rows"] if r["profile"] == name]
            track_rows.append(
                {
                    "session_id": d["session_id"],
                    "sample_rate_hz": d["sample_rate_hz"],
                    "profile": name,
                    "attempted": len(group),
                    "complete": len(points),
                    "passing": sum(r.get("margin", -1) >= 0.025 for r in group),
                    "common_points": len(indexes),
                    "median_scorer_ms": float(np.median([r["runtime_s"] * 1000 for r in group])),
                    "median_abs_cfo_change_hz": float(
                        np.median([abs(r["delta_to_original_hz"]) for r in points.values()])
                    ),
                    **common_metrics([points[i] for i in indexes], baseline),
                }
            )
        for nfft in FFT_SIZES:
            errors = [r["error_hz"] for r in d["injections"] if r["fft_size"] == nfft]
            increment_rows.append(
                {
                    "session_id": d["session_id"],
                    "sample_rate_hz": d["sample_rate_hz"],
                    "fft_size": nfft,
                    "comparisons": len(errors),
                    "rms_hz": rms(errors),
                }
            )
    summaries = []
    for name in profiles:
        group = [r for r in track_rows if r["profile"] == name]
        baseline = {r["session_id"]: r for r in track_rows if r["profile"] == "fft_512"}
        summaries.append(
            {
                "profile": name,
                **{
                    key: sum(r[key] for r in group)
                    for key in ("attempted", "complete", "passing", "common_points")
                },
                **{
                    "median_" + key: float(np.median([r[key] for r in group]))
                    for key in (
                        "self_block_rms_hz",
                        "baseline_target_block_rms_hz",
                        "self_full_rms_hz",
                        "median_scorer_ms",
                        "median_abs_cfo_change_hz",
                    )
                },
                "paired_self_block": bootstrap_scan_ratio(
                    [
                        (
                            r["session_id"],
                            r["self_block_rms_hz"],
                            baseline[r["session_id"]]["self_block_rms_hz"],
                        )
                        for r in group
                    ]
                ),
            }
        )
    increments = []
    baseline = {r["session_id"]: r for r in increment_rows if r["fft_size"] == 512}
    for nfft in FFT_SIZES:
        group = [r for r in increment_rows if r["fft_size"] == nfft]
        errors = [r["error_hz"] for d in glrt for r in d["injections"] if r["fft_size"] == nfft]
        increments.append(
            {
                "fft_size": nfft,
                "grid_spacing_hz": 1 / 4.4e-6 / nfft,
                "comparisons": len(errors),
                "pooled_increment_rms_hz": rms(errors),
                "median_scan_increment_rms_hz": float(np.median([r["rms_hz"] for r in group])),
                "p95_abs_increment_error_hz": float(np.quantile(np.abs(errors), 0.95)),
                "paired_increment_rms": bootstrap_scan_ratio(
                    [
                        (r["session_id"], r["rms_hz"], baseline[r["session_id"]]["rms_hz"])
                        for r in group
                    ]
                ),
            }
        )
    acquisition_rows = []
    for d in acq:
        baseline = {
            r["index"]: conditional_match(r) for r in d["rows"] if r["profile"] == "baseline"
        }
        for row in d["rows"]:
            match = conditional_match(row)
            base = baseline[row["index"]]
            acquisition_rows.append(
                {
                    "session_id": d["session_id"],
                    "sample_rate_hz": d["sample_rate_hz"],
                    "index": row["index"],
                    "profile": row["profile"],
                    "matched": match is not None,
                    "acquisition_ms": row["acquisition_runtime_s"] * 1000,
                    "complete_candidates": sum(
                        c["fractional_cfo_hz"] is not None for c in row["candidates"]
                    ),
                    "passing_candidates": sum(
                        c["fractional_margin"] is not None and c["fractional_margin"] >= 0.025
                        for c in row["candidates"]
                    ),
                    "delta_to_baseline_hz": None
                    if match is None or base is None
                    else alias_difference(match["fractional_cfo_hz"] - base["fractional_cfo_hz"]),
                    "matched_rank": None if match is None else match["rank"],
                    "baseline_contains_original_cfo": any(
                        c["fractional_cfo_hz"] is not None
                        and abs(c["fractional_cfo_hz"] - row["original_cfo_hz"]) < 1e-5
                        for c in row["candidates"]
                    ),
                }
            )
    acquisition_summary = []
    for name in sorted({r["profile"] for r in acquisition_rows}):
        group = [r for r in acquisition_rows if r["profile"] == name]
        delta = [r["delta_to_baseline_hz"] for r in group if r["delta_to_baseline_hz"] is not None]
        acquisition_summary.append(
            {
                "profile": name,
                "probes": len(group),
                "matched": sum(r["matched"] for r in group),
                "median_acquisition_ms": float(np.median([r["acquisition_ms"] for r in group])),
                "paired_probes": len(delta),
                "median_abs_cfo_change_hz": float(np.median(np.abs(delta))),
                "p95_abs_cfo_change_hz": float(np.quantile(np.abs(delta), 0.95)),
                "max_abs_cfo_change_hz": float(np.max(np.abs(delta))),
                "complete_candidates": sum(r["complete_candidates"] for r in group),
                "passing_candidates": sum(r["passing_candidates"] for r in group),
                "contains_original_cfo_probes": sum(
                    r["baseline_contains_original_cfo"] for r in group
                ),
            }
        )
    write_json(
        args.output / "search-summary.json",
        {
            "track_rows": track_rows,
            "glrt_summary": summaries,
            "increment_rows": increment_rows,
            "increment_summary": increments,
            "acquisition_rows": acquisition_rows,
            "acquisition_summary": acquisition_summary,
            "limits": (
                "Cubic metrics are conditional consistency, known increments test relative "
                "response, acquisition matches reuse original track identity."
            ),
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    x = list(FFT_SIZES)
    axes[0].plot(x, [r["pooled_increment_rms_hz"] for r in increments], "o-", color="#167b91")
    axes[0].set_ylabel("Known frequency-increment error RMS (Hz)")
    axes[0].set_title("72 recorded probes × 4 imposed shifts")
    selected = {r["profile"]: r for r in summaries}
    axes[1].plot(
        x, [selected[f"fft_{n}"]["median_self_block_rms_hz"] for n in x], "o-", color="#b76a2b"
    )
    axes[1].set_ylabel("Median self-target held-out cubic RMS (Hz)")
    axes[1].set_title("12 frozen tracks; consistency metric")
    for ax in axes:
        ax.set_xscale("log", base=2)
        ax.set_xticks(x, [str(n) for n in x])
        ax.set_xlabel("GLRT frequency-grid points")
        ax.grid(alpha=0.2)
    fig.suptitle(
        "Search resolution: controlled response and track consistency measure different things"
    )
    fig.tight_layout()
    fig.savefig(args.output / "search-resolution.png", dpi=160)
    plt.close(fig)
    for name, rows in (
        ("GLRT", summaries),
        ("INCREMENTS", increments),
        ("ACQUISITION", acquisition_summary),
    ):
        print(name)
        for row in rows:
            print(json.dumps(row))


if __name__ == "__main__":
    main()
