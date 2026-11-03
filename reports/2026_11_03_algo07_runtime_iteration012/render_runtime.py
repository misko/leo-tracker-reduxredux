"""Render cold and repeated discovery from the fixed whole-inventory measurement."""

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    data = json.loads((ROOT / "receipts/full-inventory.json").read_text())
    assert data["exact"] and data["cases"] == 897
    medians = [statistics.median(t["wall_seconds"] for t in data["trials"]
                                 if t["variant"] == side)
               for side in ("baseline", "candidate")]
    fig, ax = plt.subplots(figsize=(9, 5))
    for index, color in enumerate(("#536579", "#0e8265")):
        values = [data["cold"][index]["wall_seconds"], medians[index]]
        bars = ax.bar([x+(index-.5)*.35 for x in range(2)], values, width=.35,
                      color=color, label=("Original", "Digest reuse")[index])
        ax.bar_label(bars, labels=[f"{v:.3f} s" for v in values], padding=4)
    ax.set(xticks=[0, 1], xticklabels=["First pass", "Repeated pass · median of 3"],
           ylabel="Wall seconds", ylim=(0, 8))
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    ax.legend()
    fig.suptitle(f"897 fixed public inputs · {medians[0]/medians[1]:.2f}× repeated discovery",
                 fontsize=14)
    fig.text(.5, .035, "Identical job IDs, hashes, ordering and statuses.\n"
             "Full content hashing remains mandatory at consumption. Not end-to-end ALGO07 timing.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .12, 1, .94))
    fig.savefig(ROOT / "discovery_runtime.png", dpi=160)


if __name__ == "__main__":
    main()
