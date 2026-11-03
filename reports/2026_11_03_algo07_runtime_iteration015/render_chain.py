"""Plot exclusive published position-worker timings; explicitly exclude native GLRT."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent


def main():
    data = json.loads((ROOT / "receipts/position-chain.json").read_text())
    rows = data["stages"]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.barh([r["algorithm"] for r in rows], [r["worker_seconds"] for r in rows],
                   color=["#526c86", "#6488a2", "#639993", "#8db4ac", "#b7c9b9", "#c7895e"])
    ax.bar_label(bars, labels=[f"{r['worker_seconds']:.2f} s" for r in rows], padding=5)
    ax.invert_yaxis()
    ax.set(xlabel="Exclusive worker wall seconds", xlim=(0, 77))
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.grid(alpha=.2)
    ax.set_axisbelow(True)
    fig.suptitle(f"Published position workers · {data['position_worker_seconds']:.2f} seconds")
    fig.text(.5, .035, "One completed scan; observational timing only.\n"
             "Excludes native GLRT, queue waiting and watcher work outside worker timers.",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, .94))
    fig.savefig(ROOT / "position_chain.png", dpi=160)


if __name__ == "__main__":
    main()
