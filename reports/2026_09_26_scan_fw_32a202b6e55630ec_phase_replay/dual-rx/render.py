"""Render package F figures from compact saved CSV output."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).parent


def main() -> None:
    with (HERE / "method24-corrected-direct-iq.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    completed = [row for row in rows if row["status"] == "completed"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    evaluation = [row for row in completed if row["split"] == "evaluation"]
    axes[0].scatter(
        [float(row["random_cfo_rate_median_coherence"]) for row in evaluation],
        [float(row["random_cfo_rate_r"]) for row in evaluation],
        c=[int(row["channel"]) for row in evaluation],
        cmap="viridis",
        s=24,
    )
    axes[0].set(xlabel="Median direct coherence", ylabel="Random-held phase R")
    axes[0].grid(alpha=0.25)
    x = np.arange(2)
    axes[1].boxplot(
        [
            [float(row["random_cfo_rate_r"]) for row in evaluation],
            [float(row["forward_cfo_rate_r"]) for row in evaluation],
        ],
        tick_labels=["random held", "forward held"],
        widths=0.55,
    )
    axes[1].scatter(
        np.repeat(x + 1, len(evaluation)),
        np.concatenate(
            (
                [float(row["random_cfo_rate_r"]) for row in evaluation],
                [float(row["forward_cfo_rate_r"]) for row in evaluation],
            )
        ),
        alpha=0.25,
        s=10,
    )
    axes[1].set(ylabel="Phase concentration R", ylim=(0, 1))
    axes[1].grid(axis="y", alpha=0.25)
    figure.suptitle(
        "Direct dual-RX phase after training-only symbol-alias/CFO restoration\n"
        "29 evaluation visits with phase-blind dual-RX acquisition; all 96 remain denominator"
    )
    figure.savefig(HERE / "method24-held-phase.png", dpi=180, facecolor="white")


if __name__ == "__main__":
    main()
