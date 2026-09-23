#!/usr/bin/env python3
"""Plot the predeclared multi-seed synthetic error distributions."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.results.read_text())
    cases = (
        ("gaussian_300hz", "300 Hz", "#2563eb"),
        ("gaussian_300hz_satellite_epoch_0p3s", "300 Hz + epoch", "#dc2626"),
    )
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for case, label, colour in cases:
        for prior, style in (("sacramento", "-"), ("reno", "--")):
            rows = sorted(
                (
                    row for row in data["fits"]
                    if row["case"] == case and row["prior"] == prior
                ),
                key=lambda row: row["postseal_error_km"],
            )
            errors = np.asarray([row["postseal_error_km"] for row in rows])
            axes[0].step(
                errors,
                np.arange(1, len(errors) + 1) / len(errors),
                where="post",
                linestyle=style,
                color=colour,
                label=f"{label}, {prior.title()}",
            )
        sacramento = {
            row["seed"]: row["postseal_error_km"]
            for row in data["fits"]
            if row["case"] == case and row["prior"] == "sacramento"
        }
        if case.endswith("epoch_0p3s"):
            noise = {
                row["seed"]: row["postseal_error_km"]
                for row in data["fits"]
                if row["case"] == "gaussian_300hz" and row["prior"] == "sacramento"
            }
            seeds = sorted(noise)
            axes[1].scatter(
                [noise[seed] for seed in seeds],
                [sacramento[seed] for seed in seeds],
                color=colour,
                alpha=0.8,
            )
    axes[0].axvline(0.3, color="black", linestyle=":", label="300 m")
    axes[0].set_xlabel("Post-seal horizontal error (km)")
    axes[0].set_ylabel("Empirical cumulative fraction")
    axes[0].legend(fontsize=7)
    limit = max(axes[1].get_xlim()[1], axes[1].get_ylim()[1])
    axes[1].plot([0, limit], [0, limit], color="black", linestyle=":")
    axes[1].axvline(0.3, color="grey", linewidth=0.8)
    axes[1].axhline(0.3, color="grey", linewidth=0.8)
    axes[1].set_xlim(0, limit)
    axes[1].set_ylim(0, limit)
    axes[1].set_xlabel("Paired 300 Hz error (km)")
    axes[1].set_ylabel("Paired 300 Hz + epoch error (km)")
    for axis in axes:
        axis.grid(alpha=0.25)
    figure.suptitle("Twenty-seed direct-SGP4 synthetic sensitivity")
    figure.tight_layout()
    figure.savefig(args.output, dpi=180)


if __name__ == "__main__":
    main()
