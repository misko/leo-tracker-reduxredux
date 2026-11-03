"""Render the prepared ALGO02 timing pair, with profiling kept separate."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    pair = json.loads((ROOT / "receipts/unprofiled-pair.json").read_text())
    if not (pair["exact"] and pair["matched_timing_configuration"]
            and not pair["cprofile_enabled"]):
        raise ValueError("Matched unprofiled exact replay required")
    stages = pair["stages"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, metric, title in zip(axes, ("seconds", "cpu_seconds"),
                                 ("Wall seconds", "Aggregate CPU seconds"), strict=True):
        values = [[r[f"{side}_{metric}"] for r in stages]
                  for side in ("baseline", "candidate")]
        for index, (side, color) in enumerate(zip(values, ("#536579", "#0e8265"), strict=True)):
            bars = ax.bar([i + (index-.5)*.36 for i in range(2)], side,
                          width=.36, color=color, label=("Original", "Candidate")[index])
            ax.bar_label(bars, fmt="%.1f", padding=3)
        ax.set(xticks=[0, 1], xticklabels=["Discovery + fitting", "Family comparison"],
               ylabel=title, ylim=(0, max(max(v) for v in values)*1.23))
        ax.legend()
        ax.spines[["top", "right"]].set_visible(False)
        ax.yaxis.grid(alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle(f"DS27-0004 · Prepared ALGO02 replay · {pair['wall_speedup']:.2f}×", fontsize=15)
    fig.text(.5, .035, "All six scientific outputs and both calibration arms exactly equal.\n"
             "One sequential pair on a shared host; excludes GLRT, "
             "graph preparation and ALGO03–07.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .94))
    fig.savefig(ROOT / "algo02_runtime.png", dpi=160)


if __name__ == "__main__":
    main()
