#!/usr/bin/env python3
"""Render truth-blind and separately labelled post-seal iteration-28 plots."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    cells = json.loads((HERE / "cells.json").read_text())["cells"]
    inference = json.loads((HERE / "inference.json").read_text())
    east = np.asarray([row["east_m"] for row in cells])
    north = np.asarray([row["north_m"] for row in cells])
    score = np.asarray([row["actual_material_score"] for row in cells])
    best = cells[int(np.argmin(score))]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), constrained_layout=True)
    scatter = axes[0].scatter(east / 1000, north / 1000, c=score, s=65, cmap="viridis_r")
    axes[0].scatter([0], [0], marker="+", s=180, c="black", linewidths=2, label="sealed anchor")
    axes[0].scatter(
        [best["east_m"] / 1000],
        [best["north_m"] / 1000],
        marker="x",
        s=120,
        c="red",
        linewidths=2,
        label="lowest visited point (not estimate)",
    )
    axes[0].set_title("Truth-blind visited RF surface")
    axes[0].set_xlabel("East of sealed anchor (km)")
    axes[0].set_ylabel("North of sealed anchor (km)")
    axes[0].axis("equal")
    axes[0].grid(alpha=0.25)
    axes[0].legend(loc="best")
    fig.colorbar(scatter, ax=axes[0], label="Expected capped TRAIN score")

    ordered = sorted(cells, key=lambda row: row["actual_material_score"])
    axes[1].plot(
        np.arange(len(ordered)),
        [row["actual_material_score"] for row in ordered],
        "o-",
        markersize=4,
    )
    axes[1].set_title("Scores of all 20 visited cells")
    axes[1].set_xlabel("Rank among visited cells")
    axes[1].set_ylabel("Expected capped TRAIN score")
    axes[1].grid(alpha=0.25)
    axes[1].text(
        0.03,
        0.97,
        "UNQUALIFIED\ntransverse refinement gap\n1.30e-11 < 1e-10",
        transform=axes[1].transAxes,
        va="top",
        bbox={"facecolor": "white", "alpha": 0.85},
    )
    fig.suptitle(
        "DS1 iteration 28 · bracketed primary ray, stopped at optimizer resolution\n"
        f"{inference['cell_count']} cells · no position estimate · no truth used"
    )
    fig.savefig(HERE / "basin-search.png", dpi=180)
    plt.close(fig)

    evaluation = json.loads((HERE / "evaluation" / "postseal-evaluation.json").read_text())
    reference = evaluation["reference_coordinate"]
    # Convert reference to a local display offset using the short-range tangent approximation.
    anchor_lat, anchor_lon = 37.85822833, -122.47896246
    ref_north = (reference["latitude_deg"] - anchor_lat) * 111.32
    ref_east = (reference["longitude_deg"] - anchor_lon) * 111.32 * np.cos(np.radians(anchor_lat))
    fig, ax = plt.subplots(figsize=(7.2, 6.1), constrained_layout=True)
    scatter = ax.scatter(east / 1000, north / 1000, c=score, s=65, cmap="viridis_r")
    ax.scatter([0], [0], marker="+", s=180, c="black", linewidths=2, label="sealed anchor")
    ax.scatter([ref_east], [ref_north], marker="*", s=230, c="red", label="reference (post-seal)")
    ax.scatter(
        [best["east_m"] / 1000],
        [best["north_m"] / 1000],
        marker="x",
        s=120,
        c="orange",
        linewidths=2,
        label="lowest visited point (not estimate)",
    )
    ax.set_title("Post-seal diagnostic · no qualified estimate")
    ax.set_xlabel("East of sealed anchor (km)")
    ax.set_ylabel("North of sealed anchor (km)")
    ax.axis("equal")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.colorbar(scatter, ax=ax, label="Expected capped TRAIN score")
    fig.savefig(HERE / "evaluation" / "postseal-reference.png", dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
