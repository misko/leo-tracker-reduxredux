#!/usr/bin/env python3
"""Static scientific figures from sealed regional inference and evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SIZES = (100, 500, 1000, 2000)
COLORS = ("#176b9a", "#c06920", "#248461", "#8d4eaa")


def plot(root, evaluation):
    reveal = json.loads(evaluation.read_text())
    records = {r["run"]: r for r in reveal["runs"]}
    plt.rcParams.update({"font.size": 10, "axes.grid": True, "grid.alpha": 0.15})
    coarse = ["region100-coarse", "region500-coarse", "coarse50", "region2000-coarse"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
    for ax, size, name in zip(axes.flat, SIZES, coarse, strict=True):
        run = root / name
        grid = np.load(run / "grid.npz")
        score = np.load(run / "accumulated.npz")["train"]
        value = score - score.max()
        scale = size / 20
        artist = ax.scatter(
            grid["east_km"],
            grid["north_km"],
            c=value,
            marker="s",
            s=100,
            vmin=-1000,
            vmax=0,
            cmap="viridis",
            rasterized=True,
        )
        best = np.argmax(score)
        ax.scatter(grid["east_km"][best], grid["north_km"][best], marker="x", c="red", s=65)
        ax.set(
            xlabel="East of Oakland centre (km)",
            ylabel="North of Oakland centre (km)",
            xlim=(-size / 2, size / 2),
            ylim=(-size / 2, size / 2),
            aspect="equal",
            title=f"{size} × {size} km prior; {scale:g} km grid",
        )
    fig.colorbar(
        artist,
        ax=axes,
        label="Composite training score relative to best (not confidence)",
        shrink=0.7,
    )
    fig.suptitle(
        "Independent full-region searches, all 24 scans\n"
        "No receiver truth, known-site IDs, or calibrated orbit corrections in inference"
    )
    fig.savefig(root / "01-independent-regional-searches.png", dpi=170)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    for size, color, name in zip(SIZES, COLORS, coarse, strict=True):
        error = np.array(records[name]["history_horizontal_error_m"]) / 1000
        ax.plot(
            np.arange(1, len(error) + 1), error, marker=".", color=color, label=f"{size} km prior"
        )
    ax.set(
        xlabel="Completed 300 s scans incorporated",
        ylabel="Horizontal error after evaluation reveal (km)",
        yscale="log",
        title=(
            "Chronological broad-grid estimates\n"
            "Grid quantization remains; fine-grid early histories are not prospective"
        ),
    )
    ax.legend()
    fig.savefig(root / "02-coarse-convergence-over-scans.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
    for ax, size in zip(axes.flat, SIZES, strict=True):
        run = root / f"region{size}-fine"
        grid = np.load(run / "grid.npz")
        score = np.load(run / "accumulated.npz")["train"]
        best = np.argmax(score)
        proposal = json.loads((root / f"region{size}-fine-points.json").read_text())
        width = proposal["half_width_km"]
        near = (np.abs(grid["east_km"] - grid["east_km"][best]) <= width * 2) & (
            np.abs(grid["north_km"] - grid["north_km"][best]) <= width * 2
        )
        local_artist = ax.scatter(
            grid["longitude_deg"][near],
            grid["latitude_deg"][near],
            c=(score - score.max())[near],
            s=45,
            marker="s",
            cmap="viridis",
            vmin=-30,
            vmax=0,
        )
        ax.scatter(
            reveal["truth"]["longitude_deg"],
            reveal["truth"]["latitude_deg"],
            marker="*",
            s=100,
            color="red",
            label="Evaluation truth",
        )
        for timing, marker, color in ((False, "o", "white"), (True, "^", "orange")):
            model = next(
                m
                for m in reveal["polishes"]
                if m["region_km"] == size and m["fit_orbit_time"] == timing and m["fit_height"]
            )
            ax.scatter(
                model["longitude_deg"],
                model["latitude_deg"],
                marker=marker,
                s=60,
                color=color,
                edgecolor="black",
                label="Shared orbit-time fit" if timing else "Nominal-TLE fit",
            )
        ax.ticklabel_format(useOffset=False)
        ax.set(
            xlabel="Longitude (deg)",
            ylabel="Latitude (deg)",
            title=f"{size} km prior; final local mode",
        )
        ax.legend(fontsize=8)
    fig.colorbar(
        local_artist,
        ax=axes,
        shrink=0.7,
        label="Composite training score relative to best; not confidence",
    )
    fig.suptitle(
        "Training-selected local score samples and continuous fits\n"
        "Red truth marker added only after inference was frozen; no basemap implied"
    )
    fig.savefig(root / "03-local-modes-after-reveal.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    variants = [
        (False, False, "Fixed height, nominal TLE"),
        (True, False, "Fixed height, bounded time"),
        (False, True, "Unknown height, nominal TLE"),
        (True, True, "Unknown height, bounded time"),
    ]
    for j, (timing, height, label) in enumerate(variants):
        rows = [
            next(
                m
                for m in reveal["polishes"]
                if m["region_km"] == size
                and m["fit_orbit_time"] == timing
                and m["fit_height"] == height
            )
            for size in SIZES
        ]
        x = np.arange(4) + (j - 1.5) * 0.19
        axes[0].bar(x, [r["horizontal_error_m"] for r in rows], width=0.18, label=label)
        axes[1].bar(x, [r["heldout_rms_hz"] for r in rows], width=0.18, label=label)
    for ax in axes:
        ax.set_xticks(range(4), [str(s) for s in SIZES])
        ax.set_xlabel("Starting square side length (km)")
    axes[0].set(ylabel="Horizontal error (m)", title="Evaluation-only positioning error")
    axes[1].set(ylabel="Held-out CFO RMS (Hz)", title="Prediction quality on later CFO samples")
    axes[0].legend(fontsize=8)
    fig.suptitle("Small residual improvements are not automatically position improvements")
    fig.savefig(root / "04-position-and-orbit-time-ablation.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for size, color in zip(SIZES, COLORS, strict=True):
        model = next(
            m
            for m in reveal["polishes"]
            if m["region_km"] == size and m["fit_orbit_time"] and m["fit_height"]
        )
        shifts = np.sort(model["orbit_times_s"])
        axes[0].plot(
            shifts, np.arange(1, len(shifts) + 1) / len(shifts), label=f"{size} km", color=color
        )
        axes[1].scatter(
            model["heldout_rms_hz"], model["horizontal_error_m"], color=color, marker="^"
        )
        plain = next(
            m
            for m in reveal["polishes"]
            if m["region_km"] == size and not m["fit_orbit_time"] and m["fit_height"]
        )
        axes[1].plot(
            [plain["heldout_rms_hz"], model["heldout_rms_hz"]],
            [plain["horizontal_error_m"], model["horizontal_error_m"]],
            color=color,
            label=f"{size} km",
        )
        axes[1].scatter(
            plain["heldout_rms_hz"], plain["horizontal_error_m"], color=color, marker="o"
        )
    axes[0].set(
        xlabel="Shared orbit-phase correction (s)",
        ylabel="Cumulative fraction of NORAD/TLE groups",
        xlim=(-2.1, 2.1),
        title="Zero-centred 0.5 s prior; hard ±2 s bound",
    )
    axes[1].set(
        xlabel="Held-out CFO RMS (Hz)",
        ylabel="Horizontal error (m)",
        title="Circle: nominal; triangle: bounded correction",
    )
    axes[0].legend()
    axes[1].legend()
    fig.savefig(root / "05-orbit-time-corrections.png", dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for name, label in (
        ("coarse50", "Recorded times"),
        ("control-time-600", "Times −600 s"),
        ("control-time600", "Times +600 s"),
    ):
        hist = json.loads((root / name / "history.json").read_text())
        axes[0].plot(np.arange(1, len(hist) + 1), [r["train_score"] for r in hist], label=label)
        axes[1].plot(
            np.arange(1, len(hist) + 1),
            [r["heldout_score_at_train_best"] for r in hist],
            label=label,
        )
    axes[0].set(
        ylabel="Cumulative composite training score",
        title="Every control re-searches the catalogue and region",
    )
    axes[1].set(
        ylabel="Held-out score at training-selected location",
        title="Time specificity; not a false-fix probability",
    )
    for ax in axes:
        ax.set_xlabel("Scans incorporated")
        ax.legend()
    fig.savefig(root / "06-wrong-time-controls.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    args = parser.parse_args()
    plot(args.root, args.evaluation)


if __name__ == "__main__":
    main()
