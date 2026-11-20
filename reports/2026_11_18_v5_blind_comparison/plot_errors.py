"""Plot empirical geographic errors from the scored sample CSV."""

import csv
import hashlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, PercentFormatter

from .run_v5_panel import HERE, ROLES

COLORS = {"baseline": "#31395e", "selective-gap": "#6874a4", "omitted-track-one": "#717990",
          "omitted-tracks": "#7a82a8", "grid_four": "#047b64", "grid_one": "#ac641c",
          "grid_forced_four": "#497c85"}
LABELS = {"baseline": "v5 · no repair", "selective-gap": "v5 · selective gap",
          "omitted-track-one": "v5 · one omitted", "omitted-tracks": "v5 · two omitted",
          "grid_four": "Prototype · published", "grid_one": "Prototype · single tile",
          "grid_forced_four": "Prototype · forced"}
METHODS = [*ROLES, "grid_four", "grid_one", "grid_forced_four"]


def select(rows, method, condition="present"):
    arm = "fitted_c" if method in ROLES else "shape"
    return [r for r in rows if (r["method"], r["condition"], r["arm"]) == (method, condition, arm)]


def errors(selected):
    return np.sort([float(r["error_km"]) for r in selected if r["error_km"] not in (None, "")])


def fractions(selected, x):
    return np.searchsorted(errors(selected), x, side="right") / len(selected)


def set_error_axis(ax, lo, hi):
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ticks = [.01, .03, .1, .3, .5, 1, 2, 3, 5, 10, 20, 30, 50, 100, 300, 1000, 3000, 10000]
    if hi <= 30:
        ticks = [.01, .03, .1, .3, 1, 2, 5, 10, 20]
    ax.xaxis.set_major_locator(FixedLocator([x for x in ticks if lo <= x <= hi]))
    axis_format = FuncFormatter(lambda x, _: f"{x:g}" if x < 1000 else f"{x/1000:g}k")
    ax.xaxis.set_major_formatter(axis_format)
    ax.tick_params(axis="both", which="both", length=0, pad=4, labelsize=9)
    ax.grid(axis="x", which="major", color="#dde3e5", linewidth=.65)
    ax.set_axisbelow(True)
    ax.spines[:].set_visible(False)
    ax.set_xlabel("Horizontal position error (km)", fontsize=10)


def cumulative_axis(ax):
    ax.set_ylim(-.035, 1.04)
    ax.set_yticks([0, .25, .5, .75, 1])
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="y", color="#ecf0f1", linewidth=.65)


def plot_main(panels):
    fig = plt.figure(figsize=(13, 8.6))
    spec = fig.add_gridspec(2, 2, height_ratios=[1, 1.27])
    fig.subplots_adjust(left=.18, right=.975, bottom=.085, top=.825, wspace=.41, hspace=.43)
    samples = [errors(select(members, m)) for _, members in panels for m in METHODS]
    recorded = np.concatenate(samples)
    above_zero = recorded[recorded > 0]
    lo = min(.125, .83 * np.min(above_zero)) if len(above_zero) else .125
    hi = max(10.5, 1.10 * np.max(recorded))
    for col, (name, members) in enumerate(panels):
        group = {m: select(members, m) for m in METHODS}
        all_errors = np.concatenate([errors(v) for v in group.values()])
        positive = all_errors[all_errors > 0]
        x = np.unique([lo, *positive, hi])
        ax = fig.add_subplot(spec[0, col])
        set_error_axis(ax, lo, hi)
        cumulative_axis(ax)
        v5 = np.array([fractions(group[m], x) for m in ROLES])
        ax.fill_between(x, v5.min(axis=0), v5.max(axis=0), step="post", color="#9ca4c4", alpha=.8)
        for m, style, width in [("baseline", "-", 2.2), ("grid_forced_four", "--", 1.65),
                                ("grid_one", "-.", 1.7), ("grid_four", "-", 2.25)]:
            ax.step(x, fractions(group[m], x), where="post", color=COLORS[m],
                    linewidth=width, linestyle=style)
        ax.set_title(name, fontsize=14, loc="left", fontweight="bold", pad=11)
        if col == 0:
            ax.set_ylabel("Fraction of all recordings", fontsize=10)
        dot = fig.add_subplot(spec[1, col])
        set_error_axis(dot, lo, hi)
        ticks = []
        for i, method in enumerate(METHODS):
            items = group[method]
            pts = [(float(r["error_km"]), r["case"]) for r in items
                   if r["error_km"] not in (None, "")]
            ticks.append(f"{LABELS[method]}   {len(pts)}/{len(items)}")
            for val, case in pts:
                seed = int(hashlib.sha256(case.encode()).hexdigest()[:4], 16) / 65535
                dot.scatter(val, i + .55 * (seed - .5), color=COLORS[method], linewidth=0,
                            s=14 if len(items) > 10 else 25, alpha=.35 if len(items) > 10 else .7)
            if pts:
                med = np.median([v for v, _ in pts])
                dot.scatter(med, i, marker="D", c="white", edgecolors=COLORS[method],
                            linewidths=1.6, s=40, zorder=4)
        dot.set_yticks(range(len(METHODS)), ticks, fontsize=8.5)
        dot.set_ylim(len(METHODS)-.38, -.62)
        dot.set_title("Each dot is a returned position", loc="left", fontsize=11, pad=6)
    keys = [Line2D([], [], color=COLORS["baseline"], lw=2.3, label="v5 no repair"),
            Patch(color="#9ca4c4", label="Range of four v5 options"),
            Line2D([], [], color=COLORS["grid_four"], lw=2.5, label="Prototype published"),
            Line2D([], [], color=COLORS["grid_forced_four"], ls="--", label="Prototype forced"),
            Line2D([], [], color=COLORS["grid_one"], ls="-.", label="Prototype single tile")]
    fig.suptitle("Position error on the same roof recordings", fontsize=20, fontweight="bold",
                 x=.025, y=.985, ha="left")
    fig.legend(handles=keys, loc="upper left", bbox_to_anchor=(.022, .94), ncol=5,
               frameon=False, fontsize=9, handlelength=2.5, columnspacing=1.5)
    fig.text(.025, .018, "v5 uses fitted calibration. Curves count every recording. "
             "Diamonds mark the median among returned positions.", fontsize=9, color="#374650")
    fig.savefig(HERE / "matched-errors.png", dpi=165, facecolor="white")
    plt.close(fig)


def plot_transfer(rows):
    fig, (left, right) = plt.subplots(1, 2, figsize=(12.2, 4.75))
    fig.subplots_adjust(left=.075, right=.98, bottom=.23, top=.78, wspace=.24)
    for a, lo, hi in [(left, .1, 12), (right, 5, 20000)]:
        set_error_axis(a, lo, hi)
        cumulative_axis(a)
    left.set_ylabel("Fraction of all attempts")
    left.set_title("True tile offered", loc="left", weight="bold", fontsize=13)
    right.set_title("True tile missing", loc="left", weight="bold", fontsize=13)
    panels = [("StarLoc", "#2e638c"), ("Synthetic", "#087e65"), ("DS29", "#b66e22")]
    for p, color in panels:
        subset = [r for r in rows if r["panel"] == p]
        for method, st in [("grid_four", "-"), ("grid_forced_four", "--")]:
            for ax, condition, lo, hi in [(left, "present", .1, 12), (right, "missing", 5, 20000)]:
                selected = select(subset, method, condition)
                if method == "grid_four" and condition == "missing":
                    continue
                x = np.unique([lo, *errors(selected), hi])
                ax.step(x, fractions(selected, x), where="post", ls=st, color=color, lw=2)
    right.axhline(0, color="#263238", linewidth=2)
    fig.suptitle("Prototype error in the locked blind trials", fontsize=18, fontweight="bold",
                 ha="left", x=.025, y=.98)
    handles = [Line2D([], [], color=color, lw=3, label=p) for p, color in panels]
    handles += [Line2D([], [], color="#35464e", label="Published"),
                Line2D([], [], color="#35464e", ls="--", label="Forced estimate")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .06), ncol=5,
               frameon=False, fontsize=9)
    fig.text(.025, .025, "UK spectra yielded no positions in either condition. "
             "Every missing-region coordinate was withheld.", fontsize=9, color="#374650")
    fig.savefig(HERE / "blind-errors.png", dpi=165, facecolor="white")
    plt.close(fig)


def main():
    with (HERE / "sample-errors.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    plot_main([("DS26  ·  127 common recordings",
                [r for r in rows if r["panel"] == "DS26" and r["in_original_127"] == "1"]),
               ("DS29  ·  8 blind-panel recordings", [r for r in rows if r["panel"] == "DS29"])])
    plot_transfer(rows)


if __name__ == "__main__":
    main()
