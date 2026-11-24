"""Plot paired elapsed times as a fraction of the v3 reference for each timed scope."""

import argparse
import gzip
import json
from pathlib import Path


def read(path):
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return json.load(source)


def measurements(short, north, long):
    short_named = short["prior"]["stock"]["process"]["clock"]
    short_candidate = short["guarded"]["process"]["clock"]
    north = north["sealed"]
    long = long["clocks"]
    return [
        ("DS30-0107  ·  29 visits", "Raw samples to withhold", short_named["elapsed_s"], short_candidate["elapsed_s"]),
        ("North simulation  ·  1,200 visits", "Raw samples to position and PNGs",
         north["controls"]["named_clock"]["elapsed_s"], north["clock"]["elapsed_s"]),
        ("DS30-0316  ·  3,042 visits", "Saved v3 detections to position and PNGs",
         long["recent_named"]["process"]["elapsed_s"], long["candidate"]["process"]["elapsed_s"]),
    ]


def draw(rows, output):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.ticker import PercentFormatter

    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    fig.subplots_adjust(left=.35, bottom=.20, right=.95, top=.80)
    fig.text(.04, .91, "Single-core time against ALGO08v3", fontsize=19, weight="bold")
    ys = [2, 1, 0]
    for y, (case, scope, reference, candidate) in zip(ys, rows, strict=True):
        ratio = candidate / reference
        ax.barh(y, 1.0, height=.40, color="#e6e9ee", zorder=1)
        ax.barh(y, ratio, height=.40, color="#137970" if y else "#4a6688", zorder=2)
        ax.text(.02, y, f"{candidate:.2f} s", va="center", color="white", weight="bold")
        ax.text(1.015, y, f"{reference:.2f} s", va="center", color="#434956", fontsize=9)
        ax.text(-.04, y+.085, case, ha="right", va="center", weight="bold")
        ax.text(-.04, y-.13, scope, ha="right", va="center", color="#596573", fontsize=9)
    ax.vlines(.5, -.44, 2.34, color="#932e40", ls="--", lw=1.5, zorder=3)
    ax.text(.5, 2.49, "2× target", ha="center", color="#932e40", fontsize=10)
    ax.text(1.01, 2.49, "v3 elapsed", fontsize=9, color="#434956")
    ax.set_xlim(0, 1.16)
    ax.set_ylim(-.44, 2.72)
    ax.set_xticks([0, .25, .5, .75, 1])
    ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_xlabel("Candidate elapsed as a fraction of the matching v3 elapsed")
    ax.set_yticks([])
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.text(.04, .04, "One comparison per recording. The DS30-0316 timings exclude acquisition.", fontsize=9, color="#596573")
    fig.savefig(output, dpi=155)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("short", "north", "long", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    draw(measurements(read(args.short), read(args.north), read(args.long)), args.output)
