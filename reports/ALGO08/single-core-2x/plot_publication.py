"""Plot the two published matched invocations of the same northern simulation."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    here = Path(__file__).resolve().parent
    files = ["north-candidate-first.json", "north-baseline-first.json"]
    rows = [json.loads((here / "measurements" / name).read_bytes()) for name in files]
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    colors = {"baseline": "#355577", "candidate": "#00765c"}
    for ax, field, title in zip(axes, ("elapsed_s", "cpu_s"), ("Elapsed time", "Single-core CPU time")):
        for index, row in enumerate(rows):
            for arm, shift in [("baseline", -.17), ("candidate", .17)]:
                value = row["runs"][arm][field]
                ax.bar(index + shift, value, width=.30, color=colors[arm],
                       label=arm.capitalize() if index == 0 else None, zorder=2)
                ax.text(index + shift, value + 1, f"{value:.1f}", ha="center", fontsize=9)
        ax.set_xticks([0, 1], ["Candidate first", "Baseline first"])
        ax.set_title(title, loc="left", fontsize=12)
        ax.grid(axis="y", alpha=.22)
        ax.spines[["right", "top"]].set_visible(False)
        ax.set_ylim(0, 90)
    axes[0].set_ylabel("Seconds")
    fig.legend(*axes[1].get_legend_handles_labels(), loc="upper right",
               bbox_to_anchor=(.99, 1.0), frameon=False, ncol=2)
    fig.suptitle("One northern simulation, two run orders", x=.07, y=.96, ha="left", fontsize=15)
    fig.subplots_adjust(top=.74, bottom=.18, wspace=.12)
    fig.savefig(here / "publication-timing.png", dpi=165, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
