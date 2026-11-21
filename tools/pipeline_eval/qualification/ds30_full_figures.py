"""Draw recording-level CDFs for the full DS30 comparison."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

from .blind_compact_figures import cumulative
from .ds30_full_inputs import METHODS, OUT
from .ds30_full_score import belongs

NAMES = {
    "algo07v5": "Original GLRT + algo07v5",
    "compact_two_scan": "Two-scan cancellation + compact v5",
}
COLORS = {"algo07v5": "#293d66", "compact_two_scan": "#a44a15"}
STYLES = {"algo07v5": "-", "compact_two_scan": (0, (4, 2))}


def style(fig, axes, title):
    fig.suptitle(title, x=0.068, ha="left", y=0.99, fontsize=19, fontweight="bold")
    fig.legend(
        handles=[
            Line2D([], [], color=COLORS[m], linestyle=STYLES[m], linewidth=2.5, label=NAMES[m])
            for m in METHODS
        ],
        loc="upper left",
        bbox_to_anchor=(0.061, 0.945),
        ncol=2,
        frameon=False,
        handlelength=3.4,
    )
    for ax in axes.flat:
        ax.spines[["right", "top"]].set_visible(False)
        ax.grid(color="#dce2e5", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_ylim(-0.025, 1.035)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))


def lines(ax, curves, upper):
    for method, values in curves.items():
        if not values:
            continue
        x, y = cumulative(values, len(values), (0, upper))
        ax.step(x, y, where="post", linestyle=STYLES[method], color=COLORS[method], linewidth=2)
    ax.set_xlim(0, upper)


def figures(rows, pairs):
    groups = [
        ("all", "All recordings"),
        ("complete", "Complete recordings"),
        ("incomplete", "Incomplete recordings"),
    ]
    largest = max((r["error_km"] for r in rows if r["error_km"] is not None), default=1)
    upper = max(1, largest * 1.08)
    ticks = [v for v in (0, 0.25, 0.5, 1, 2, 5, 10, 20, 50, 100) if v <= upper]
    fig, axes = plt.subplots(2, 3, figsize=(13.6, 8), sharex=True, sharey=True)
    style(fig, axes, "Cumulative horizontal position error on DS30")
    for i, (arm, cal) in enumerate(
        (("fitted_c", "Fitted calibration"), ("c0", "Zero calibration"))
    ):
        for j, (group, label) in enumerate(groups):
            ax = axes[i, j]
            sample = [
                r
                for r in rows
                if r["calibration"] == arm and r["reference_eligible"] and belongs(r, group)
            ]
            curves = {m: [r["error_km"] for r in sample if r["method"] == m] for m in METHODS}
            ax.set_xscale("symlog", linthresh=0.5, linscale=0.45)
            ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
            lines(ax, curves, upper)
            if i == 0:
                ax.set_title(f"{label} (n = {len(curves[METHODS[0]])})", fontsize=12)
            if i == 1:
                ax.set_xlabel("Horizontal position error (km)")
            if j == 0:
                ax.set_ylabel(cal + "\nFraction of recordings")
    fig.subplots_adjust(top=0.83, left=0.083, right=0.982, bottom=0.09, hspace=0.16, wspace=0.12)
    fig.savefig(OUT / "position-error.png", dpi=160, facecolor="white")
    plt.close(fig)

    fitted = [r for r in rows if r["calibration"] == "fitted_c"]
    timed = [p for p in pairs if p["calibration"] == "fitted_c"]
    panels = [
        ("solver_wall_s", "solver_speedup", "all", "Position solver, all paired attempts"),
        (
            "end_to_end_wall_s",
            "end_to_end_speedup",
            "complete",
            "Raw I/Q to result, complete captures",
        ),
        (
            "end_to_end_wall_s",
            "end_to_end_speedup",
            "incomplete",
            "Raw I/Q to result, incomplete captures",
        ),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 4.9), sharey=True)
    style(fig, axes, "Runtime on paired DS30 recordings on Gauss")
    for ax, (field, ratio, group, title) in zip(axes, panels, strict=True):
        cases = {p["case"] for p in timed if p[ratio] is not None and belongs(p, group)}
        curves = {
            m: [r[field] / 60 for r in fitted if r["case"] in cases and r["method"] == m]
            for m in METHODS
        }
        upper = max(1, max((v for values in curves.values() for v in values), default=1) * 1.08)
        lines(ax, curves, upper)
        ax.set_title(title + f"\n(n = {len(cases)})", fontsize=11.5)
        ax.set_xlabel("Elapsed minutes per recording")
    axes[0].set_ylabel("Fraction of timed recordings")
    fig.subplots_adjust(top=0.72, left=0.069, right=0.981, bottom=0.16, wspace=0.13)
    fig.savefig(OUT / "runtime.png", dpi=160, facecolor="white")
    plt.close(fig)
