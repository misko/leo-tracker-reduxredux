#!/usr/bin/env python3
"""Section-specific static figures for the expanded, sealed continental study.

Geographic outlines are sourced Natural Earth polygons, not guessed coastlines.
This reporting adapter may consume evaluation truth; no output is fed to search.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

from leo.analysis.research.regional_doppler import Region

COLORS = ("#176b9a", "#c06920", "#248461", "#8d4eaa", "#b64250")


def load(path):
    return json.loads(path.read_text())


def border(region):
    x = np.linspace(-region.width_km / 2, region.width_km / 2, 101)
    y = np.linspace(-region.height_km / 2, region.height_km / 2, 101)
    east = np.r_[x, np.full(101, x[-1]), x[::-1], np.full(101, x[0]), x[0]]
    north = np.r_[np.full(101, y[0]), y, np.full(101, y[-1]), y[::-1], y[0]]
    return region.coordinates(east, north)


def land(ax, data):
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        for polygon in polygons:
            points = np.array(polygon[0])
            # Avoid projecting a dateline-spanning polygon across this regional map.
            if np.ptp(points[:, 0]) > 180:
                continue
            ax.add_patch(
                Polygon(
                    points,
                    closed=True,
                    facecolor="#e8ece9",
                    edgecolor="#a1aaa5",
                    linewidth=0.6,
                    zorder=0,
                )
            )
    ax.set(
        xlabel="Longitude (degrees)", ylabel="Latitude (degrees)", xlim=(-155, -65), ylim=(15, 72)
    )
    ax.grid(alpha=0.2)


def save(fig, root, name):
    fig.savefig(root / name, dpi=190, facecolor="white")
    plt.close(fig)


def introduction(root):
    data = load(root / "natural-earth-110m-land.geojson")
    fig, ax = plt.subplots(figsize=(11, 7), constrained_layout=True)
    land(ax, data)
    regions = [Region(37.8044, -122.2712, n, n) for n in (100, 500, 1000, 2000)]
    regions.append(Region(43.6914344, -106.8991205, 5000, 5000))
    all_lat, all_lon = [], []
    for region, color in zip(regions, COLORS, strict=True):
        lat, lon = border(region)
        all_lat.extend(lat)
        all_lon.extend(lon)
        ax.plot(
            lon,
            lat,
            color=color,
            linewidth=1.8,
            label=f"{region.width_km:g} × {region.height_km:g} km",
        )
    ax.set(xlim=(min(all_lon) - 3, max(all_lon) + 3), ylim=(min(all_lat) - 3, max(all_lat) + 3))
    ax.scatter([-122.2712, -106.8991205], [37.8044, 43.6914344], color="black", marker="+", s=65)
    ax.annotate(
        "Oakland-centred priors",
        (-122.2712, 37.8044),
        xytext=(-144, 33),
        arrowprops={"arrowstyle": "-"},
    )
    ax.annotate(
        "New user-defined centre\n43.6914344, −106.8991205",
        (-106.8991205, 43.6914344),
        xytext=(-106, 29),
        arrowprops={"arrowstyle": "-"},
    )
    ax.legend(loc="upper right", title="Independent starting regions")
    ax.set_title(
        "Introduction · Can Doppler localize us without a nearby starting position?\n"
        "Square bounds use spherical azimuthal map distances; Doppler geometry uses WGS84"
    )
    save(fig, root, "07-introduction-starting-regions.png")


def approach(root):
    fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
    ax.set(xlim=(0, 12), ylim=(0, 6))
    ax.axis("off")
    boxes = [
        (0.2, 3.7, "Declared region\nRecorded UTC\nCausal TLE catalogue"),
        (3.2, 3.7, "Fractional RF evidence\nNormalize actual RF\nTrain / held-out split"),
        (6.2, 3.7, "Whole-region search\nUnknown satellite IDs\nUnassigned alternative"),
        (9.2, 3.7, "Retain alternatives\nRefine training modes\nCross-check resolution"),
        (9.2, 1.2, "Physical local fits\nNominal / bounded time\nUnknown-height alternative"),
        (6.2, 1.2, "Freeze predictions\nSeal outputs and inputs\nSHA-256 evidence"),
        (3.2, 1.2, "Separate evaluation\nPosition error\nIntegrity controls"),
    ]
    for i, (x, y, label) in enumerate(boxes):
        ax.add_patch(
            FancyBboxPatch(
                (x, y), 2.5, 1.3, boxstyle="round,pad=.08", facecolor="#f0f5f7", edgecolor="#5b7788"
            )
        )
        ax.text(x + 1.25, y + 0.65, label, ha="center", va="center", fontsize=10)
        if i:
            px, py, _ = boxes[i - 1]
            if y == py:
                a, b = (
                    ((px + 2.6, py + 0.65), (x - 0.1, y + 0.65))
                    if x > px
                    else ((px - 0.1, py + 0.65), (x + 2.6, y + 0.65))
                )
            else:
                a, b = (px + 1.25, py - 0.1), (x + 1.25, y + 1.4)
            ax.add_patch(
                FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, color="#4a6472")
            )
    ax.text(
        1.35,
        1.8,
        "User's true coordinate\nEVALUATION ONLY",
        ha="center",
        color="#a8323c",
        weight="bold",
    )
    ax.add_patch(
        FancyArrowPatch(
            (2.55, 1.85), (3.05, 1.85), arrowstyle="-|>", mutation_scale=14, color="#a8323c"
        )
    )
    ax.text(
        6,
        0.25,
        "No truth-to-estimator feedback; no known-site satellite assignments; no new RF collection",
        ha="center",
        fontsize=11,
    )
    ax.set_title("Approaches · A truth-isolated regional-search and evaluation workflow", pad=15)
    save(fig, root, "08-approaches-truth-isolated-workflow.png")


def motivation(root):
    run = root / "region5000-grid125"
    grid = np.load(run / "grid.npz")
    history = load(run / "history.json")
    first = np.load(run / f"{history[0]['session_id']}.npz")
    chosen = np.argsort([-r["points"] for r in history[0]["episodes"]])[:3]
    scores = [first["train_logbf"][i] for i in chosen]
    scores.append(np.load(run / "accumulated.npz")["train"])
    labels = [f"One RF episode: {history[0]['episodes'][i]['episode_id']}" for i in chosen] + [
        "All 502 episodes / 24 scans"
    ]
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), constrained_layout=True)
    for index, (ax, score, label) in enumerate(zip(axes.flat, scores, labels, strict=True)):
        artist = ax.scatter(
            grid["east_km"],
            grid["north_km"],
            c=score - score.max(),
            cmap="viridis",
            s=10,
            marker="s",
            vmin=-200 if index == 3 else -max(20, float(np.ptp(score))),
            vmax=0,
        )
        ax.set(
            xlabel="East of declared centre (km)",
            ylabel="North of declared centre (km)",
            title=label,
            xlim=(-2500, 2500),
            ylim=(-2500, 2500),
            aspect="equal",
        )
        fig.colorbar(
            artist,
            ax=ax,
            label="Δ composite training score",
            shrink=0.75,
            extend="min" if index == 3 else "neither",
        )
    fig.suptitle(
        "Motivation · One short arc supports many location / satellite explanations\n"
        "More scans sharpen the sampled score, but a coarse grid can still pick the wrong region"
    )
    save(fig, root, "09-motivation-single-arc-ambiguity.png")


def methods(root, evidence):
    history = load(root / "region5000-grid125/history.json")
    doc = load(evidence / "evidence" / f"{history[0]['session_id']}.json")
    series = {row["tracklet_id"]: row for row in doc["series"]}
    pairs = [
        (series[merge["left_tracklet_id"]], series[merge["right_tracklet_id"]])
        for merge in doc["edge_merges"]
    ]
    a, b = max(
        pairs,
        key=lambda pair: (
            min(max(pair[0]["t_s"]), max(pair[1]["t_s"]))
            - max(min(pair[0]["t_s"]), min(pair[1]["t_s"]))
        ),
    )
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for row, color in zip((a, b), COLORS, strict=False):
        t, y = np.array(row["t_s"]), np.array(row["y_hz"])
        order = np.argsort(t)
        t, y = t[order], y[order]
        k = int(0.6 * len(t))
        centered = y - y[:k].mean()
        raw = centered * row["actual_rf_hz"] / 11.2e9
        label = f"{row['edge']} · {row['actual_rf_hz'] / 1e9:.4f} GHz"
        axes[0].plot(t, raw / 1000, ".-", color=color, label=label, markersize=3)
        axes[1].plot(t, centered / 1000, ".-", color=color, label=label, markersize=3)
        axes[2].scatter(t[:k], centered[:k] / 1000, s=14, color=color)
        axes[2].scatter(t[k:], centered[k:] / 1000, s=18, edgecolor=color, facecolor="none")
        axes[2].axvline((t[k - 1] + t[k]) / 2, color=color, alpha=0.35)
    for ax in axes:
        ax.set(xlabel="Time since scan start (s)", ylabel="Training-offset-centred CFO (kHz)")
        ax.grid(alpha=0.2)
    axes[0].set_title("Actual RF: differential Doppler remains")
    axes[1].set_title("Normalize to 11.2 GHz before joining")
    axes[2].set_title("Filled: train; hollow: held out")
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Methods · Actual RF scaling, segment offsets and chronological holdout\n"
        "RF-associated upper/lower pair; no catalogue identity or receiver truth required"
    )
    save(fig, root, "10-methods-rf-normalization-and-holdout.png")


def evolution(root):
    run = root / "region5000-grid50"
    grid, history = np.load(run / "grid.npz"), load(run / "history.json")
    total = np.zeros(len(grid["east_km"]))
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
    panels = {1: axes[0, 0], 2: axes[0, 1], 3: axes[1, 0], 24: axes[1, 1]}
    for index, record in enumerate(history, 1):
        total += np.load(run / f"{record['session_id']}.npz")["train_logbf"].sum(axis=0)
        if index not in panels:
            continue
        ax = panels[index]
        artist = ax.scatter(
            grid["longitude_deg"],
            grid["latitude_deg"],
            c=total - total.max(),
            s=3,
            cmap="viridis",
            vmin=-max(20, index * 35),
            vmax=0,
            rasterized=True,
        )
        best = np.argmax(total)
        ax.scatter(
            grid["longitude_deg"][best], grid["latitude_deg"][best], marker="x", color="red", s=50
        )
        ax.set(
            xlabel="Longitude (degrees)",
            ylabel="Latitude (degrees)",
            title=f"After {index} {'scan' if index == 1 else 'scans'}",
        )
        fig.colorbar(artist, ax=ax, label="Δ composite score", shrink=0.7, extend="min")
    fig.suptitle(
        "Results · Chronological accumulation across the full 5,000 km region\n"
        "50 km grid, training data only; the leading location is not a confidence guarantee"
    )
    save(fig, root, "11-results-continental-search-evolution.png")


def results(root, evaluation):
    reveal = load(evaluation)
    sizes = (100, 500, 1000, 2000, 5000)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for timing, offset, color, label in (
        (False, -0.18, COLORS[0], "Nominal TLE"),
        (True, 0.18, COLORS[1], "Shared ±2 s orbit-time model"),
    ):
        rows = [
            next(
                r
                for r in reveal["polishes"]
                if r["region_km"] == size
                and r["fit_height"]
                and r["fit_orbit_time"] == timing
                and (size != 5000 or r["parent_run"] == "region5000-fine")
            )
            for size in sizes
        ]
        bars = axes[0].bar(
            np.arange(5) + offset,
            [r["horizontal_error_m"] / 1000 for r in rows],
            width=0.34,
            color=color,
            label=label,
        )
        axes[0].bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
        axes[1].bar(
            np.arange(5) + offset,
            [r["heldout_rms_hz"] for r in rows],
            width=0.34,
            color=color,
            label=label,
        )
    for ax in axes:
        ax.set_xticks(range(5), [str(s) for s in sizes])
        ax.set_xlabel("Starting square side length (km)")
        ax.grid(axis="y", alpha=0.2)
    axes[0].set(
        ylabel="Evaluation-only horizontal error (km)",
        title="Unknown height: all five starting bounds",
    )
    axes[0].margins(y=0.28)
    axes[1].set(
        ylabel="Held-out CFO RMS (Hz)", title="Prediction fit does not certify positioning accuracy"
    )
    axes[0].legend(fontsize=9)
    save(fig, root, "12-results-five-starting-bounds.png")

    names = [
        "region5000-grid250",
        "region5000-grid125",
        "region5000-refined",
        "region5000-grid50",
        "region5000-local",
        "region5000-fine",
    ]
    labels = [
        "250 km\nfull grid",
        "125 km\nfull grid",
        "125 km branch\nlocal search",
        "50 km\nfull grid",
        "50 km branch\nlocal search",
        "Final\nfine grid",
    ]
    rows = [next(r for r in reveal["runs"] if r["run"] == name) for name in names]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    bars = axes[0].bar(
        range(len(rows)),
        [r["horizontal_error_m"] / 1000 for r in rows],
        color=[COLORS[4]] * 3 + [COLORS[0]] * 3,
    )
    axes[0].bar_label(bars, fmt="%.2f", fontsize=8, padding=3)
    axes[0].set_yscale("log")
    axes[0].margins(y=0.15)
    axes[0].set(
        ylabel="Horizontal error after reveal (km)",
        title="Details · Grid resolution and missed geographic modes",
    )
    offsets = [(0, 16), (5, -15), (12, 4), (-8, -18), (-40, -10), (-20, 14)]
    for name, color, offset in zip(names, [COLORS[4]] * 3 + [COLORS[0]] * 3, offsets, strict=True):
        result = load(root / name / "result.json")
        axes[1].scatter(
            result["train_score"], result["heldout_score_at_train_best"], color=color, s=40
        )
        axes[1].annotate(
            name.replace("region5000-", ""),
            (result["train_score"], result["heldout_score_at_train_best"]),
            xytext=offset,
            textcoords="offset points",
            fontsize=8,
        )
    axes[0].set_xticks(range(len(rows)), labels, fontsize=8)
    axes[1].set(
        xlabel="Training score at selected location",
        ylabel="Held-out score at selected location",
        title="Independent whole-region refinement checks",
    )
    axes[1].margins(x=0.10, y=0.10)
    for ax in axes:
        ax.grid(alpha=0.2)
    save(fig, root, "13-details-resolution-and-failed-branches.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--initial-only", action="store_true")
    args = parser.parse_args()
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    introduction(args.root)
    approach(args.root)
    motivation(args.root)
    methods(args.root, args.evidence)
    if not args.initial_only:
        evolution(args.root)
        results(args.root, args.evaluation)


if __name__ == "__main__":
    main()
