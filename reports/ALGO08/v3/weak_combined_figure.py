"""Render the paired development observation from its scored receipt."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def draw(source, output):
    rows = json.loads(source.read_bytes())["runs"]
    colors = ("#35486d", "#087f70")
    names = ("ALGO08v3", "Combined candidate")
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.25), layout="constrained")
    for axis, dimension in zip(axes, ("runtime", "error"), strict=True):
        for index, (name, row) in enumerate(zip(names, (rows["stock"], rows["candidate"]), strict=True)):
            values = ([row["report_write_s"], row["process"]["elapsed_s"]] if dimension == "runtime"
                      else [row["errors_km"]["c0"], row["errors_km"]["fitted_c"]])
            bars = axis.bar([x + .34 * (index - .5) for x in range(2)], values,
                            width=.32, color=colors[index], label=name)
            axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        clock = dimension == "runtime"
        axis.set_xticks([0, 1], ["Through web report", "Through exit"] if clock else ["Fixed c = 0", "Fitted c"])
        axis.set_title("Elapsed time (s)" if clock else "Horizontal error (km)", loc="left", fontweight="bold")
        axis.set_ylim(0, axis.get_ylim()[1] * 1.15)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.yaxis.grid(True, color="#d7dee1", linewidth=.7)
        axis.set_axisbelow(True)
    axes[0].legend(loc="lower center", bbox_to_anchor=(.5, -.36), ncol=2, frameon=False)
    fig.suptitle("DS30-0016   ·   One recording, both inputs fully cached", fontweight="bold", fontsize=14)
    fig.savefig(output, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    home = Path(__file__).resolve().parent
    draw(home / "measurements/weak-combined-raw.json", home / "development/weak-combined-raw.png")
