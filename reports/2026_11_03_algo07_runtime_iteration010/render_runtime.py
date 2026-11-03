"""Render matched full-native wall and CPU timings from committed receipts."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    rows = [json.loads((ROOT / "receipts" / (name + "-timing.json")).read_text())
            for name in ("baseline16", "candidate16")]
    parity = json.loads((ROOT / "receipts/full-native-matched-parity.json").read_text())
    if not (parity["exact"] and parity["matched_timing_configuration"]):
        raise ValueError("Matched exact native replay required")
    wall = [r["wall_seconds"] / 60 for r in rows]
    cpu = [(r["user_cpu_seconds"] + r["system_cpu_seconds"]) / 60 for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax, values, title, unit in zip(axes, (wall, cpu), ("Wall time", "CPU work"),
                                     ("Minutes", "Aggregate core-minutes"), strict=True):
        bars = ax.bar([0, 1], values, color=["#536579", "#0e8265"], width=.58)
        ax.bar_label(bars, labels=[f"{v:.2f}" for v in values], padding=6, fontsize=12)
        ax.set_xticks([0, 1], ["Installed baseline", "Tiled candidate"])
        ax.set_ylabel(unit)
        ax.set_ylim(0, max(values) * 1.25)
        ax.set_title(f"{title}: {values[0] / values[1]:.2f}× improvement")
        ax.spines[["top", "right"]].set_visible(False)
        ax.yaxis.grid(alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle("DS27-0004 · Complete native GLRT replay · 16 workers", fontsize=15)
    fig.text(.5, .04, "All 6,772 window results and 108,272 hypotheses exactly equal.\n"
             "One sequential pair on a shared host; this is a GLRT-stage measurement.",
             ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .13, 1, .94))
    fig.savefig(ROOT / "native_runtime.png", dpi=160)


if __name__ == "__main__":
    main()
