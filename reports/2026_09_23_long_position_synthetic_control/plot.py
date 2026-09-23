#!/usr/bin/env python3
"""Render the synthetic control post-seal position and residual summary."""

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
    cases = list(data["cases"])
    labels = ["zero", "300 Hz", "300 Hz + epoch"]
    colours = {"sacramento": "#2563eb", "reno": "#dc2626"}
    x = np.arange(len(cases))
    figure, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for prior, delta in (("sacramento", -0.13), ("reno", 0.13)):
        rows = [
            next(
                row for row in data["fits"]
                if row["case"] == case and row["prior"] == prior
            )
            for case in cases
        ]
        axes[0].bar(
            x + delta,
            [row["postseal_error_km"] for row in rows],
            width=0.25,
            label=prior.title(),
            color=colours[prior],
        )
        axes[1].plot(
            x,
            [row["training_uncapped_rmse_hz"] for row in rows],
            "o-",
            color=colours[prior],
            label=f"{prior.title()} train",
        )
        axes[1].plot(
            x,
            [row["held_uncapped_rmse_hz"] for row in rows],
            "s--",
            color=colours[prior],
            label=f"{prior.title()} held",
        )
    axes[0].axhline(
        0.3, color="black", linestyle=":", linewidth=1, label="0.3 km control check"
    )
    axes[0].set_ylabel("Post-seal horizontal error (km)")
    axes[0].set_yscale("symlog", linthresh=0.001)
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel("Uncapped residual RMS (Hz)")
    axes[1].set_yscale("symlog", linthresh=0.001)
    axes[1].legend(fontsize=8)
    for axis in axes:
        axis.set_xticks(x, labels)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Direct-SGP4 synthetic control (conditional retained support)")
    figure.tight_layout()
    figure.savefig(args.output, dpi=180)


if __name__ == "__main__":
    main()
