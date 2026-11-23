"""Plot the raw process boundaries and individual position errors, including withholds."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def render(panel, output):
    rows = panel["rows"]
    stages = ("Launch to detections", "Detections to decision", "Decision to exit")
    colors = ("#266678", "#62a9a2", "#c8d8ce")
    points = {"c0": ("o", "#365b91"), "fitted_c": ("D", "#bd651c")}
    fig, (timing, error) = plt.subplots(1, 2, width_ratios=(1.55, 1), sharey=True,
                                       figsize=(10.0, max(3.9, 1.0 + 1.35*len(rows))))
    labels, ticks = [], []
    for index, row in enumerate(rows):
        for arm_index, mode in enumerate(("stock", "candidate")):
            y = index * 2.65 + arm_index
            run = row["runs"][mode]
            left = 0.0
            for value, color in zip(run["stages_s"], colors, strict=True):
                timing.barh(y, value, left=left, color=color, height=.55, zorder=2)
                left += value
            timing.annotate(f"{left:.2f} s", (left, y), xytext=(4, 0), textcoords="offset points",
                            ha="left", va="center", fontsize=9)
            if run["decision"] == "complete":
                for arm, (marker, color) in points.items():
                    x = run["errors_km"][arm]
                    error.scatter(x, y, s=44, color=color, marker=marker, zorder=3)
            else:
                error.text(.04, y, "Withheld", va="center", transform=error.get_yaxis_transform(),
                           fontsize=9, color="#526570")
            version = "ALGO08v3" if mode == "stock" else "Candidate"
            labels.append(f"{row['case']}   ·   {version}")
            ticks.append(y)
    timing.set_yticks(ticks, labels)
    timing.invert_yaxis()
    timing.set(xlabel="Elapsed time (s)", title="Original samples through exit", xlim=(0, timing.get_xlim()[1]*1.13))
    errors = [v for row in rows for run in row["runs"].values() for v in run["errors_km"].values()]
    error.set(xlabel="Horizontal position error (km)", title="Error against the site reference",
              xlim=(0, 1.12 * max([0.1, *errors])))
    for ax in (timing, error):
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#e1e9eb", linewidth=.7, zorder=0)
    handles = [Patch(facecolor=c, label=l) for c,l in zip(colors, stages, strict=True)]
    handles.extend(Line2D([], [], linestyle="", marker=m, color=c, label=l) for (m,c),l in zip(
        points.values(), ("Fixed zero", "Fitted calibration"), strict=True))
    fig.suptitle("Matched single-core DS30 recordings", fontsize=16, weight="bold", x=.53)
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, .16, 1, .94), w_pad=2.2)
    fig.savefig(output, dpi=155, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("panel", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    render(json.loads(args.panel.read_bytes()), args.output)
