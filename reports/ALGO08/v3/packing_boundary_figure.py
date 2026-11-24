"""Draw paired physical-member timings directly from the verified receipts."""

import gzip
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent


def receipt(stem):
    with gzip.open(HERE / "measurements" / (stem + ".json.gz"), "rt") as stream:
        return json.load(stream)


def measurements():
    weak = receipt("ci16-packed-storage-0016")["final"]["data"]
    dense = receipt("ci16-packed-storage-0008")["data"]
    stages = []
    for case, data in (("DS30-0016", weak), ("DS30-0008", dense)):
        pairs = [(run["ordinary"]["capture_to_first"]["wall_ns"] / 1e6,
                  run["packed-ci16"]["capture_to_first"]["wall_ns"] / 1e6) for run in data["runs"]]
        stages.append((case, pairs))
    pairs = receipt("packed-combined-0016")["pairs"]
    cli = []
    for field in ("acquisition", "exit"):
        timings = []
        for pair in pairs:
            row = pair["measurements"]
            values = []
            for variant in ("ordinary", "packed"):
                entry = row[variant]
                clock = (entry["clocks"] if field == "exit"
                         else entry["evidence"]["phases"]["authenticated_raw_acquisition"])
                values.append(1000 * clock["elapsed_s"])
            timings.append(tuple(values))
        cli.append(("Acquisition" if field == "acquisition" else "Through exit", timings))
    return stages, cli


def draw(path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 3.6))
    fig.subplots_adjust(left=.115, right=.984, top=.74, bottom=.23, wspace=.49)
    colors = ["#354562", "#007c75"]
    fig.suptitle("Where lossless packing saves time", x=.027, y=.98, ha="left", fontsize=18, weight="bold")
    handles = [Line2D([], [], marker="o", color=color, linestyle="", label=name)
               for color, name in zip(colors, ("Ordinary Zstandard", "Packed CI16"))]
    fig.legend(handles=handles, loc="upper right", frameon=False, ncol=2, bbox_to_anchor=(.992, .992))
    for ax, groups, title, limits in zip(axes, measurements(),
            ("Capture write through first mixed analysis", "Combined receiver on DS30-0016"),
            ((280, 510), (200, 820)), strict=True):
        for row, (_, pairs) in enumerate(groups):
            for index, pair in enumerate(pairs):
                y = row + (index - (len(pairs) - 1) / 2) * .13
                ax.plot(pair, [y, y], color="#c0c7d2", lw=1.5, zorder=1)
                for elapsed, color in zip(pair, colors):
                    ax.scatter(elapsed, y, color=color, s=28, zorder=2)
            left, right = (median(values) for values in zip(*pairs))
            ax.text((left + right) / 2, row + .28, f"{left:.0f} → {right:.0f} ms",
                    ha="center", fontsize=10)
        ax.set(yticks=[0, 1], yticklabels=[name for name, _ in groups], xlim=limits, ylim=(1.49, -.38))
        ax.grid(axis="x", color="#e2e5e9")
        ax.set_axisbelow(True)
        ax.spines[["top", "left", "right"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_title(title, fontsize=11, loc="left", weight="bold")
        ax.set_xlabel("Elapsed time (ms)")
    fig.text(.027, .035, "Each line joins one paired order on one complete physical member. Labels give medians.", fontsize=9)
    fig.savefig(path, dpi=165, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    draw(HERE / "development/packing-boundaries.png")
