#!/usr/bin/env python3
"""Render a truth-revealed convergence report from sealed blind regional runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HORIZONS = (("30m", 0.5), ("1h", 1.0), ("2h", 2.0), ("4h", 4.0), ("8h", 8.0))


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat = lat2 - lat1
    dlon = math.radians(b[1] - a[1])
    value = math.sin(dlat / 2) ** 2
    value += math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def load_rows(base: Path, truth: tuple[float, float]) -> list[dict]:
    rows = []
    for label, requested_h in HORIZONS:
        coarse_path = base / f"{label}-coarse125" / "result.json"
        fine_path = base / f"{label}-refine5" / "result.json"
        history_path = base / f"{label}-coarse125" / "history.json"
        polish_path = base / f"{label}-polish.json"
        coarse = json.loads(coarse_path.read_text())
        fine = json.loads(fine_path.read_text())
        history = json.loads(history_path.read_text())
        polish = json.loads(polish_path.read_text())
        nominal = next(model for model in polish["models"] if not model["fit_orbit_time"])
        bounded = next(model for model in polish["models"] if model["fit_orbit_time"])
        grid = np.load(base / f"{label}-refine5" / "grid.npz")
        scores = np.load(base / f"{label}-refine5" / "accumulated.npz")["train"]
        best = fine["best_index"]
        near = scores >= scores[best] - 10
        extent = np.hypot(
            grid["east_km"][near] - grid["east_km"][best],
            grid["north_km"][near] - grid["north_km"][best],
        )
        rows.append(
            {
                "label": label,
                "requested_hours": requested_h,
                "observed_span_hours": (
                    history[-1]["reference_utc_ns"] - history[0]["reference_utc_ns"]
                )
                / 3.6e12,
                "scan_count": coarse["scan_count"],
                "episode_count": coarse["episode_count"],
                "polish_episode_count": polish["episode_count"],
                "orbit_group_count": polish["orbit_group_count"],
                "coarse_latitude_deg": coarse["latitude_deg"],
                "coarse_longitude_deg": coarse["longitude_deg"],
                "coarse_error_km": haversine_km(
                    (coarse["latitude_deg"], coarse["longitude_deg"]), truth
                ),
                "coarse_runner_gap": coarse["separated_modes"][1]["delta_score"],
                "grid_latitude_deg": fine["latitude_deg"],
                "grid_longitude_deg": fine["longitude_deg"],
                "grid_error_km": haversine_km((fine["latitude_deg"], fine["longitude_deg"]), truth),
                "score_drop_10_cells": int(near.sum()),
                "score_drop_10_extent_km": float(extent.max()),
                "nominal_latitude_deg": nominal["latitude_deg"],
                "nominal_longitude_deg": nominal["longitude_deg"],
                "nominal_error_km": haversine_km(
                    (nominal["latitude_deg"], nominal["longitude_deg"]), truth
                ),
                "nominal_train_rms_hz": nominal["training_rms_hz"],
                "nominal_heldout_rms_hz": nominal["heldout_rms_hz"],
                "bounded_time_error_km": haversine_km(
                    (bounded["latitude_deg"], bounded["longitude_deg"]), truth
                ),
                "bounded_time_heldout_rms_hz": bounded["heldout_rms_hz"],
                "source_digests": {
                    "coarse_result": digest(coarse_path),
                    "fine_result": digest(fine_path),
                    "polish_result": digest(polish_path),
                },
            }
        )
    return rows


def plot_prior(base: Path, rows: list[dict], truth: tuple[float, float], output: Path) -> None:
    fig, (ax, zoom) = plt.subplots(1, 2, figsize=(14, 6.2), constrained_layout=True)
    prior = np.load(base / "30m-coarse125" / "grid.npz")
    ax.scatter(
        prior["longitude_deg"],
        prior["latitude_deg"],
        s=5,
        color="#d9d2c3",
        label="sampled prior",
    )
    ax.scatter(
        -98.5795, 39.8283, marker="+", s=180, linewidth=2.5, color="#555555", label="prior centre"
    )
    ax.scatter(
        truth[1], truth[0], marker="*", s=230, color="black", label="evaluation site", zorder=5
    )
    colours = plt.cm.viridis(np.linspace(0.1, 0.9, len(rows)))
    for row, colour in zip(rows, colours, strict=True):
        point = (row["nominal_longitude_deg"], row["nominal_latitude_deg"])
        ax.scatter(*point, s=55, color=colour, zorder=4)
        zoom.scatter(*point, s=70, color=colour, label=row["label"], zorder=4)
    ax.set_title("Declared 5,000 × 5,000 km prior")
    ax.set_xlabel("Longitude (degrees)")
    ax.set_ylabel("Latitude (degrees)")
    ax.legend(loc="lower left")
    zoom.scatter(
        truth[1],
        truth[0],
        marker="*",
        s=230,
        color="black",
        label="evaluation site",
        zorder=5,
    )
    zoom.set(xlim=(-122.55, -122.30), ylim=(37.78, 37.95))
    zoom.set_title("Continuous nominal-TLE estimates")
    zoom.set_xlabel("Longitude (degrees)")
    zoom.set_ylabel("Latitude (degrees)")
    zoom.legend(ncol=2)
    for panel in (ax, zoom):
        panel.set_facecolor("#f5f1e8")
        panel.grid(color="white", linewidth=1.2)
    fig.suptitle("Blind location convergence; site coordinate revealed after inference")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_convergence(rows: list[dict], output: Path) -> None:
    x = [row["requested_hours"] for row in rows]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), constrained_layout=True)
    axes[0].plot(x, [r["grid_error_km"] for r in rows], "o-", label="5 km training grid")
    axes[0].plot(x, [r["nominal_error_km"] for r in rows], "o-", label="continuous nominal-TLE fit")
    axes[0].set(
        xlabel="Requested elapsed scanning window (h)",
        ylabel="Horizontal error after truth reveal (km)",
        title="Observed location error",
    )
    axes[0].set_xticks(x, [r["label"] for r in rows])
    axes[0].set_ylim(bottom=0)
    axes[0].grid(alpha=0.3)
    axes[0].legend()
    axes[1].plot(x, [r["coarse_runner_gap"] for r in rows], "o-", color="#7b3294")
    axes[1].set(
        xlabel="Requested elapsed scanning window (h)",
        ylabel="Training-score gap (composite units)",
        title="Best basin vs next separated coarse mode",
    )
    axes[1].set_xticks(x, [r["label"] for r in rows])
    axes[1].set_yscale("log")
    axes[1].grid(alpha=0.3)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_maps(base: Path, rows: list[dict], truth: tuple[float, float], output: Path) -> None:
    fig, axes = plt.subplots(
        1, 5, figsize=(18, 4.2), sharex=True, sharey=True, constrained_layout=True
    )
    for ax, row in zip(axes, rows, strict=True):
        label = row["label"]
        grid = np.load(base / f"{label}-coarse125" / "grid.npz")
        score = np.load(base / f"{label}-coarse125" / "accumulated.npz")["train"]
        relative = np.maximum(score - score.max(), -250)
        artist = ax.scatter(
            grid["longitude_deg"],
            grid["latitude_deg"],
            c=relative,
            s=18,
            cmap="magma",
            vmin=-250,
            vmax=0,
        )
        ax.scatter(
            truth[1], truth[0], marker="*", color="#31a354", edgecolor="white", s=100, linewidth=0.7
        )
        ax.scatter(
            row["coarse_longitude_deg"],
            row["coarse_latitude_deg"],
            marker="x",
            color="#2b8cbe",
            s=70,
            linewidth=2,
        )
        ax.set_title(f"{label} · {row['scan_count']} scans")
        ax.grid(alpha=0.15)
    axes[0].set_ylabel("Latitude (degrees)")
    for ax in axes:
        ax.set_xlabel("Longitude")
    fig.colorbar(artist, ax=axes, label="Training score relative to best (clipped)", shrink=0.82)
    fig.suptitle("Global training-only score maps; green star revealed only for evaluation")
    fig.savefig(output, dpi=180)
    plt.close(fig)


def plot_validation(rows: list[dict], output: Path) -> None:
    x = np.arange(len(rows))
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5), constrained_layout=True)
    axes[0].bar(x, [r["nominal_heldout_rms_hz"] for r in rows], color="#3182bd")
    axes[0].set_xticks(x, [r["label"] for r in rows])
    axes[0].set(
        ylabel="Chronological held-out RMS (Hz)",
        title="Prediction residual after frozen identities",
    )
    axes[0].grid(axis="y", alpha=0.3)
    axes[1].bar(x, [r["episode_count"] for r in rows], color="#31a354", label="RF episodes")
    axes[1].plot(
        x,
        [r["orbit_group_count"] for r in rows],
        "o-",
        color="#de2d26",
        label="independent orbit groups",
    )
    axes[1].set_xticks(x, [r["label"] for r in rows])
    axes[1].set(ylabel="Count", title="Evidence accumulated by each cut")
    axes[1].grid(axis="y", alpha=0.3)
    axes[1].legend()
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--truth-lat", type=float, required=True)
    parser.add_argument("--truth-lon", type=float, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output must be fresh")
    args.output.mkdir(parents=True)
    truth = (args.truth_lat, args.truth_lon)
    rows = load_rows(args.experiment, truth)
    with (args.output / "horizon-results.csv").open("w", newline="") as stream:
        flat = [{k: v for k, v in row.items() if k != "source_digests"} for row in rows]
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    (args.output / "results.json").write_text(
        json.dumps(
            {
                "scientific_status": (
                    "retrospective truth-revealed evaluation of sealed blind inference"
                ),
                "truth_latitude_deg": truth[0],
                "truth_longitude_deg": truth[1],
                "truth_used_by_inference": False,
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    plot_prior(args.experiment, rows, truth, args.output / "01-prior-and-estimates.png")
    plot_convergence(rows, args.output / "02-error-and-ambiguity.png")
    plot_maps(args.experiment, rows, truth, args.output / "03-global-score-maps.png")
    plot_validation(rows, args.output / "04-heldout-and-evidence.png")
    print(f"Rendered {len(rows)} horizons to {args.output}")


if __name__ == "__main__":
    main()
