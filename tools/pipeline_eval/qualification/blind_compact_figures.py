"""Matched-recording runtime and unconditional horizontal error distributions."""

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter, StrMethodFormatter

from .blind_compact_roster import METHODS

PANELS = ("DS26", "DS29")
NAMES = {
    "original": "Original GLRT",
    "checked": "Checked one scan",
    "cancellation": "Two-scan cancellation",
}
COLORS = {"original": "#2d4263", "checked": "#007e68", "cancellation": "#a34b16"}
MARKERS = {"original": "o", "checked": "s", "cancellation": "^"}
LINES = {"original": "-", "checked": (0, (5, 2)), "cancellation": (0, (2, 1.6))}


def cumulative(values, assigned, limits):
    """Every assigned recording contributes to the denominator, including a withheld fix."""
    if len(values) != assigned or not assigned:
        raise ValueError("a curve needs every assigned recording")
    finite = sorted(v for v in values if v is not None)
    if any(not math.isfinite(v) or not limits[0] <= v <= limits[1] for v in finite):
        raise ValueError("an observation falls outside the plotted range")
    return [limits[0], *finite, limits[1]], [
        0,
        *(i / assigned for i in range(1, len(finite) + 1)),
        len(finite) / assigned,
    ]


def canvas(title, subtitle):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.4))
    fig.subplots_adjust(left=0.12, right=0.975, top=0.79, bottom=0.12, hspace=0.50, wspace=0.20)
    fig.text(0.055, 0.96, title, fontsize=21, fontweight="bold", color="#182d39")
    fig.text(0.056, 0.918, subtitle, fontsize=11, color="#495d65")
    handles = [
        Line2D(
            [0],
            [0],
            color=COLORS[m],
            lw=2.4,
            linestyle=LINES[m],
            marker=MARKERS[m],
            markerfacecolor="white",
            markersize=5,
            label=NAMES[m],
        )
        for m in METHODS
    ]
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.052, 0.902),
        ncol=3,
        frameon=False,
        handlelength=3.6,
        columnspacing=2,
    )
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#adbbc0")
        ax.tick_params(colors="#344952", length=3)
        ax.grid(axis="both", color="#dfe6e8", linewidth=0.8)
        ax.set_axisbelow(True)
    return fig, axes


def cdf_axis(ax):
    ax.set_ylim(-0.025, 1.045)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))


def line(ax, method, values, limits):
    x, y = cumulative(values, len(values), limits)
    ax.step(x, y, where="post", color=COLORS[method], lw=2.1, linestyle=LINES[method])
    ax.plot(
        x[1:-1],
        y[1:-1],
        ls="none",
        marker=MARKERS[method],
        markerfacecolor="white",
        markeredgecolor=COLORS[method],
        markersize=4,
        alpha=0.95,
    )
    ax.set_xlim(*limits)


def times(rows, output):
    rows = [r for r in rows if r["calibration"] == "fitted_c"]
    max_time = max(r["end_to_end_wall_s"] / 60 for r in rows)
    limits = (0, max_time * 1.05)
    fig, axes = canvas(
        "How long did each recording take?",
        "Gauss wall time from reading signed I/Q to compact v5 returning a fix or a failure.",
    )
    for j, dataset in enumerate(PANELS):
        subset = [r for r in rows if r["dataset"] == dataset]
        ids = sorted({r["case"] for r in subset})
        top, bottom = axes[:, j]
        top.set_title(f"{dataset}  ·  {len(ids)} recordings", loc="left", fontweight="bold", pad=10)
        cdf_axis(top)
        span = np.median([r["hardware_span_s"] for r in subset]) / 60
        for ax in (top, bottom):
            ax.axvline(span, color="#748388", ls=":", lw=1.5, zorder=1)
        for i, ident in enumerate(ids):
            values = [r["end_to_end_wall_s"] / 60 for r in subset if r["case"] == ident]
            bottom.plot([min(values), max(values)], [i, i], color="#aebcc0", lw=1.2)
        for method in METHODS:
            points = sorted((r for r in subset if r["method"] == method), key=lambda r: r["case"])
            minutes = [r["end_to_end_wall_s"] / 60 for r in points]
            line(top, method, minutes, limits)
            bottom.plot(
                minutes,
                np.arange(len(ids)),
                ls="none",
                marker=MARKERS[method],
                markeredgecolor=COLORS[method],
                markerfacecolor="white",
                markeredgewidth=1.5,
            )
        bottom.set_yticks(np.arange(len(ids)), [s.split("-")[-1] for s in ids])
        bottom.invert_yaxis()
        bottom.set_xlim(*limits)
        bottom.set_title("Same recording, three runs", loc="left", fontsize=11)
        bottom.set_xlabel("End-to-end runtime (minutes)")
    axes[0, 0].set_ylabel("Fraction of all recordings")
    axes[1, 0].set_ylabel("Recording ID")
    fig.text(
        0.055,
        0.032,
        "Dotted vertical lines mark the five-minute recording span. "
        "All three runs share a pinned CPU per recording on a shared Gauss host.",
        fontsize=9,
        color="#495d65",
    )
    fig.savefig(output / "runtime.png", dpi=165, facecolor="white")
    plt.close(fig)


def positions(rows, output):
    errors = [r["error_km"] for r in rows if r["error_km"] is not None]
    positive = [x for x in errors if x > 0]
    low = min(positive or [0.1]) * 0.65 if len(positive) == len(errors) else 0
    high = max(errors or [1.0]) * 1.35 or 1
    use_log = low > 0 and high / low > 8
    if not use_log:
        low = 0
    limits = (low, high)
    fig, axes = canvas(
        "How often did compact v5 fix within the stated error?",
        "Each step is one returned position. "
        "The denominator includes every recording, including misses.",
    )
    for i, (arm, label) in enumerate((("fitted_c", "Fitted c"), ("c0", "c = 0"))):
        for j, dataset in enumerate(PANELS):
            ax = axes[i, j]
            subset = [r for r in rows if (r["dataset"], r["calibration"]) == (dataset, arm)]
            n = len({r["case"] for r in subset})
            ax.set_title(
                f"{dataset}  ·  {label}  ·  {n} recordings",
                loc="left",
                fontweight="bold",
                fontsize=12,
            )
            cdf_axis(ax)
            if use_log:
                ax.set_xscale("log")
                ticks = [
                    s * 10.0**p
                    for p in range(math.floor(math.log10(low)), math.ceil(math.log10(high)) + 1)
                    for s in (1, 2, 5)
                    if low <= s * 10.0**p <= high
                ]
                ax.set_xticks(ticks)
                ax.xaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
                ax.minorticks_off()
            for method in METHODS:
                line(ax, method, [r["error_km"] for r in subset if r["method"] == method], limits)
            if i == 1:
                ax.set_xlabel("Horizontal position error (km)")
            if j == 0:
                ax.set_ylabel("Fraction of all recordings")
    fig.text(
        0.055,
        0.032,
        "At 1 km, read the share fixed within 1 km. The final height is the fix rate. "
        "Both datasets are from the same roof.",
        fontsize=9,
        color="#495d65",
    )
    fig.savefig(output / "position-error.png", dpi=165, facecolor="white")
    plt.close(fig)


def figures(rows, output):
    times(rows, output)
    positions(rows, output)
