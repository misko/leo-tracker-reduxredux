"""Show charged saved-solve CPU and errors from diagnostic and terminal positions."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


LABELS = {"DS30-0008": "DS30-0008", "south-containing": "South containing", "south-far": "South omitted"}
COLORS = {"DS30-0008": "#007176", "south-containing": "#9c4928", "south-far": "#655399"}
STAGES = {"proposal": "Cold proposal", "one_finish": "One finish\n(rejected)", "terminal": "Terminal\n(v3 fallback)"}


def figure(pins, output):
    cases = json.loads(pins.read_text())["cases"]
    fig = plt.figure(figsize=(12, 7.8), layout="constrained")
    grid = fig.add_gridspec(2, 2, height_ratios=[1., 1.3])
    timing = fig.add_subplot(grid[0, :])
    names = list(LABELS)
    y = tuple(reversed(range(len(names))))
    left = [0.] * len(names)
    for key, label, color in (
        ("shared_prep_other_cpu_s", "Shared preparation and other", "#a3aab0"),
        ("proposal_cpu_s", "Mixture proposal", "#007176"),
        ("validation_cpu_s", "Full-data finish", "#d1a33b"),
        ("fallback_cpu_s", "Checked v3 fallback", "#5f5987"),
    ):
        values = [cases[name]["stages"][key] / cases[name]["stages"]["archived_v3_cpu_s"] for name in names]
        timing.barh(y, values, left=left, color=color, height=.53, label=label)
        left = [a + b for a, b in zip(left, values, strict=True)]
    for name, end, index in zip(names, left, y, strict=True):
        stages = cases[name]["stages"]
        timing.text(end + .018, index, f"{stages['charged_cpu_s']:.2f} vs {stages['archived_v3_cpu_s']:.2f} s",
                    va="center", fontsize=9)
    timing.axvline(1., color="#303942", linestyle="--", linewidth=1.1)
    timing.set(title="Charged saved solve through terminal evidence", xlim=(0., 1.48), yticks=y,
               yticklabels=[LABELS[name] for name in names], xlabel="CPU relative to matched saved v3 control")
    timing.legend(ncols=4, frameon=False, loc="upper center", bbox_to_anchor=(.5, 1.02), fontsize=8.5)
    timing.set_ylim(-.5, 3.0)
    timing.spines[["top", "right"]].set_visible(False)

    for axis, contained in zip((fig.add_subplot(grid[1, 0]), fig.add_subplot(grid[1, 1])), (True, False), strict=True):
        for name, row in cases.items():
            if row["contained"] != contained:
                continue
            for arm, marker, shift in (("c0", "o", -.065), ("fitted_c", "s", .065)):
                xs, ys = [], []
                for i, stage in enumerate(STAGES):
                    error = row[stage]["arms"][arm]["error_km"]
                    if error is not None:
                        xs.append(i + shift)
                        ys.append(error)
                axis.plot(xs, ys, color=COLORS[name], alpha=.67, linewidth=1.1)
                axis.scatter(xs, ys, color=COLORS[name], marker=marker, zorder=3, s=32,
                             facecolors="white" if arm == "c0" else COLORS[name])
        names_in_plot = [name for name, row in cases.items() if row["contained"] == contained]
        handles = [Line2D([], [], color=COLORS[name], label=LABELS[name]) for name in names_in_plot]
        handles += [Line2D([], [], color="#313c43", marker=marker, linestyle="none", label=label,
                           markerfacecolor="white" if marker == "o" else "#313c43")
                    for marker, label in (("o", "c = 0"), ("s", "Fitted c"))]
        axis.legend(handles=handles, ncols=2, frameon=False, fontsize=8.5, loc="upper right")
        axis.set(title="Containing offers" if contained else "Omitted offer", ylabel="Horizontal error (km)",
                 xticks=range(len(STAGES)), xticklabels=tuple(STAGES.values()), xlim=(-.18, 2.28),
                 ylim=(0., 9.2) if contained else (0., 100.))
        if not contained:
            axis.text(2., 25., "Withheld\nin both arms", ha="center", va="center", fontsize=10)
        axis.grid(axis="y", alpha=.22)
        axis.spines[["top", "right"]].set_visible(False)
    fig.savefig(output, dpi=170, facecolor="white")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pins", type=Path)
    parser.add_argument("output", type=Path)
    figure(**vars(parser.parse_args()))
