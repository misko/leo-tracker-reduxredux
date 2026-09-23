"""Render the frozen-position, whole-scan orbit-correction comparison."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    root = Path(__file__).resolve().parent
    summary = json.loads((root / "summary.json").read_text())
    rows = summary["scans"]
    x = np.arange(1, len(rows) + 1)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), constrained_layout=True)
    for key, label in [("causal_mean", "Causal mean only"), ("fitted", "Fitted shared rates")]:
        delta = [r["scores"][key] - r["scores"]["original"] for r in rows]
        axes[0].plot(x, delta, "o-", label=label)
        axes[1].plot(x, np.cumsum(delta), "o-", label=label)
    for ax in axes:
        ax.axhline(0, color="black", linewidth=0.8)
        ax.grid(alpha=0.2)
        ax.set_xticks(x)
    axes[0].set_ylabel("Per-scan score gain over original orbit")
    axes[0].legend()
    axes[1].set_ylabel("Cumulative score gain")
    axes[1].set_xlabel("Unseen scan in chronological order")
    fig.suptitle(
        "Frozen five-scan position: prediction on 14 entirely unseen scans\n"
        "Higher is better · composite Doppler-shape scores · no parameters refitted"
    )
    fig.savefig(root / "whole-scan-orbit-comparison.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
