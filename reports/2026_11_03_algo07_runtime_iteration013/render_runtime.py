"""Render measured native hotspots and rejected execution-tile trials."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    profile = json.loads((ROOT / "receipts/profile-summary.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    detector, coarse = profile["detector_seconds"], profile["coarse_seconds"]
    axes[0].barh([0], [coarse], color="#48769b", label="Coarse correlation")
    axes[0].barh([0], [detector-coarse], left=[coarse], color="#b3c4d1",
                 label="Other detector work")
    axes[0].set(title="Deployed native profile · 16 windows", xlabel="Seconds",
                yticks=[], xlim=(0, 20))
    axes[0].text(coarse/2, 0, f"{coarse:.2f} s\n{100*coarse/detector:.1f}%",
                 ha="center", va="center", color="white")
    axes[0].legend(loc="upper left")
    for i, tile in enumerate([8, 4]):
        data = json.loads((ROOT / f"receipts/tile{tile}-paired.json").read_text())
        values = [data["totals"][v] for v in ["baseline", "candidate"]]
        for j, value in enumerate(values):
            bars = axes[1].bar(i+(j-.5)*.35, value, width=.35,
                              color=["#48769b", "#d28b55"][j],
                              label=["Deployed 12 lanes", "Probe"][j] if i == 0 else None)
            axes[1].bar_label(bars, labels=[f"{value:.2f}"], padding=3)
    axes[1].set(title="Alternating paired trials · no profiling", ylabel="Detector seconds",
                xticks=[0, 1], xticklabels=["8-lane probe", "4-lane probe"], ylim=(0, 22))
    axes[1].legend(loc="upper left")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Smaller execution tiles preserve results but do not improve runtime")
    fig.text(.5, .025, "Full receiver outputs exactly equal. Shared host, CPU 0. "
             "Neither probe deployed; these are not end-to-end ALGO07 timings.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .93))
    fig.savefig(ROOT / "native_tile_audit.png", dpi=160)


if __name__ == "__main__":
    main()
