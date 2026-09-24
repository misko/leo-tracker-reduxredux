#!/usr/bin/env python3
"""Render the DS2 portable development comparison."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    result = json.loads((HERE / "evaluation.json").read_text())
    single = [row for row in result["rows"] if row["scope"] == "single"]
    coarse = {row["method"]: row for row in result["coarse_joint_rows"]}
    refined = {row["method"]: row for row in result["refined_joint_rows"]}
    joint = result["joint_rows"]
    labels = [
        "baseline",
        "shared-time",
        "causal-rate",
        "independent-track-time",
        "soft-identity",
    ]
    names = [
        "Baseline Doppler",
        "Shared global time",
        "Causal per-NORAD rate",
        "Independent track time",
        "Soft identity mixture",
    ]
    values = [
        [row["postseal_error_km"] for row in single if row["method"] == label]
        for label in labels
    ]
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.4), constrained_layout=True)

    axes[0].boxplot(values, tick_labels=names, showfliers=False)
    for index, series in enumerate(values, 1):
        jitter = np.linspace(-0.09, 0.09, len(series))
        axes[0].scatter(index + jitter, series, s=22, alpha=0.75, zorder=3)
    axes[0].set_yscale("log")
    axes[0].set_ylabel("Post-seal position error (km, log scale)")
    axes[0].set_title("20 whole-session estimates")
    axes[0].tick_params(axis="x", rotation=18)
    axes[0].grid(axis="y", alpha=0.25)

    joint_names = [row["method"] for row in joint]
    joint_error = [row["postseal_error_km"] for row in joint]
    coarse_error = [coarse[row["method"]]["postseal_error_km"] for row in joint]
    refined_error = [refined[row["method"]]["postseal_error_km"] for row in joint]
    y = np.arange(len(joint))
    axes[1].barh(y - 0.26, coarse_error, height=0.24, label="Coarse")
    axes[1].barh(y, refined_error, height=0.24, label="0.391 km")
    bars = axes[1].barh(y + 0.26, joint_error, height=0.24, label="0.098 km")
    axes[1].set_yticks(y, labels=joint_names)
    axes[1].bar_label(bars, fmt="%.2f km", padding=4, fontsize=8)
    axes[1].set_xlabel("Post-seal position error (km)")
    axes[1].set_title("Equal-scan joint estimates: coarse vs refined")
    axes[1].grid(axis="x", alpha=0.25)
    axes[1].legend()

    ref = result["reference_coordinate"]
    axes[2].scatter(
        ref["longitude_deg"],
        ref["latitude_deg"],
        marker="*",
        s=220,
        c="red",
        edgecolor="black",
        label="Reference",
    )
    for row in joint:
        axes[2].scatter(row["longitude_deg"], row["latitude_deg"], s=65, label=row["method"])
    axes[2].set_xlabel("Longitude (degrees)")
    axes[2].set_ylabel("Latitude (degrees)")
    axes[2].set_title("Fine joint selected coordinates")
    axes[2].grid(alpha=0.25)
    axes[2].legend(fontsize=8)
    figure.suptitle(
        "DS2 Sept 24 portable positioning · reference introduced only after inference seals",
        fontsize=14,
    )
    figure.savefig(HERE / "portable-model-comparison.png", dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
