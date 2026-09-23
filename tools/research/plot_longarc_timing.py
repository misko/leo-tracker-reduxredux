"""Plot fixed-population long-arc timing sensitivity."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

DIRECTORY = Path(__file__).resolve().parents[2] / "reports/figures/2026_09_23_longarc_timing"


def main():
    document = json.loads((DIRECTORY / "evaluation.json").read_text())
    rows = document["results"]
    labels = ["Integer", "−1 sample", "+1 sample", "Saved fractional"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for index, row in enumerate(rows):
        gain = row["selected_vs_constant_rate"]
        mean = gain["mean_score_gain"]
        low, high = gain["percentile_95_interval"]
        axes[0].errorbar(mean, index, xerr=[[mean - low], [high - mean]], fmt="o", capsize=5)
    axes[0].axvline(0, color="gray", linewidth=1)
    axes[0].set_yticks(np.arange(4), labels)
    axes[0].set(
        xlabel="Held circular score gain over constant rate",
        title="No significant geometry gain at any timing offset",
    )
    axes[0].invert_yaxis()
    axes[1].plot(np.arange(4), [row["held_exact_coherence"] for row in rows], "o-")
    axes[1].set_xticks(np.arange(4), labels, rotation=20)
    axes[1].set(
        ylabel="Mean held exact-pilot coherence",
        ylim=(0.07, 0.076),
        title="Small coherence change; candidate stays 67702",
    )
    fig.suptitle("78 saved dwells • 42 train / 36 random held • fixed branches and phase pairs")
    fig.savefig(DIRECTORY / "timing-sensitivity.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
