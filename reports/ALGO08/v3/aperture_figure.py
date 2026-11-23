"""Plot saved solve accuracy and separately scoped acquisition costs."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter


COLORS = {"DS30-0008": "#017477", "north": "#4c55a4", "south": "#b44c22"}
LABELS = {"DS30-0008": "DS30-0008", "north": "North", "south": "South"}
MARKERS = {"full": "o", "fixed": "s", "guarded": "^"}


def figure(numbers, output):
    data = json.loads(numbers.read_text())
    fig = plt.figure(figsize=(13, 7.5), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=[2.15, 1])
    for axis, contains in zip((fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])), (True, False), strict=True):
        empty = {mode: {"withheld": 0, "failed": 0, "assigned": 0} for mode in MARKERS}
        for case, runs in data["cases"].items():
            if runs["full"]["contained"] != contains:
                continue
            key = case if case.startswith("DS30") else case.split("-")[0]
            color = COLORS[key]
            for mode, row in runs.items():
                empty[mode]["assigned"] += 1
                if row["status"] != "ok":
                    empty[mode][row["status"]] += 1
                    continue
                for arm, scores in row["arm_scores"].items():
                    filled = arm == "fitted_c"
                    axis.scatter(row["cpu_s"], scores["error_km"], edgecolors=color,
                                 facecolors=color if filled else "none", marker=MARKERS[mode],
                                 s=55 if filled else 100, linewidths=1.4, zorder=4 if filled else 5)
        axis.set(title="Offers containing the site" if contains else "Displaced offers",
                 xlabel="Measured saved solve and grid CPU (s)", ylabel="Horizontal error (km)")
        if contains:
            axis.set_xscale("log")
            axis.xaxis.set_major_locator(FixedLocator([5, 8, 12, 20, 35, 55]))
            axis.xaxis.set_major_formatter(ScalarFormatter())
            axis.xaxis.set_minor_formatter(NullFormatter())
        axis.grid(alpha=0.2)
        counts = "  ·  ".join(f"{mode} {row['withheld']}/{row['failed']}/{row['assigned']}"
                             for mode, row in empty.items())
        axis.annotate("Withheld / failed / assigned    " + counts,
                      xy=(0, -0.23), xycoords="axes fraction", fontsize=9)
    sites = [Line2D([], [], color=color, linewidth=3, label=LABELS[case]) for case, color in COLORS.items()]
    modes = [Line2D([], [], color="#2b3034", linestyle="none", marker=marker, label=mode.title())
             for mode, marker in MARKERS.items()]
    arms = [Line2D([], [], color="#2b3034", linestyle="none", marker="o", markerfacecolor=face, label=label)
            for face, label in (("none", "c = 0"), ("#2b3034", "Fitted c"))]
    fig.legend(handles=[*sites, *modes, *arms], ncols=8, frameon=False, loc="outside upper center")

    budget = fig.add_subplot(grid[1, :])
    cost = data["budget"]
    prefix = cost["prefix_medians"]
    dense = cost["masks"]
    labels = ("Fixed prefix acquisition, measured", "Zero-DSP prefix acquisition, measured",
              "Fixed dense pipeline, projected", "Guarded dense pipeline, projected")
    fractions = (prefix["fixed"]["cpu_s"] / prefix["full"]["cpu_s"],
                 prefix["no-dsp"]["cpu_s"] / prefix["full"]["cpu_s"],
                 dense["fixed"]["optimistic_total_cpu_ratio"], dense["guarded"]["optimistic_total_cpu_ratio"])
    y = tuple(reversed(range(len(labels))))
    budget.barh(y, fractions, color=["#017477", "#017477", "#8d93aa", "#8d93aa"], height=0.58)
    budget.axvline(0.5, color="#b44c22", linestyle="--", linewidth=1.3)
    budget.axvline(1.0, color="#2b3034", linewidth=0.8, alpha=0.65)
    for index, fraction in zip(y, fractions, strict=True):
        budget.text(fraction + 0.012, index, f"{fraction:.1%}", va="center", fontsize=9)
    budget.set(yticks=y, yticklabels=labels, xlim=(0, 1.12),
               xlabel="Fraction of v3 CPU at the corresponding boundary  ·  50% marks the whole-pipeline target")
    budget.spines[["top", "right"]].set_visible(False)
    fig.savefig(output, dpi=160, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", type=Path)
    parser.add_argument("output", type=Path)
    figure(**vars(parser.parse_args()))
