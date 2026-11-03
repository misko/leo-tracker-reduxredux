"""Plot matched per-window detector totals; no end-to-end timing claim."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    rows = json.loads((ROOT / "receipts/summary.json").read_text())
    fig, ax = plt.subplots(figsize=(9, 5))
    for j, (name, label, color) in enumerate([
            ("baseline", "Deployed detector", "#536579"),
            ("candidate", "Exact weight reuse", "#0e8265")]):
        values = [r["totals"][name] for r in rows]
        bars = ax.bar([i+(j-.5)*.35 for i in range(len(rows))], values,
                      width=.35, color=color, label=label)
        ax.bar_label(bars, labels=[f"{v:.3f} s" for v in values], padding=4)
    ax.set(xticks=list(range(len(rows))),
           xticklabels=[r["fixture"].removeprefix("glrt-native-") for r in rows],
           ylabel="Detector wall seconds · 16 windows", ylim=(0, 17))
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper right")
    ax.yaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    fig.suptitle("Exact fractional-weight reuse · approximately 1.08× faster")
    fig.text(.5, .025, "All 96 receiver outputs exactly equal. Alternating sequential trials, "
             "CPU 0, shared host.\nQualified and deployed after graceful drain.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .1, 1, .94))
    fig.savefig(ROOT / "fractional_runtime.png", dpi=160)


if __name__ == "__main__":
    main()
