"""Render recorded runtime and all-recording position-error distributions."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter
import numpy as np


ROOT = Path(__file__).resolve().parent
STOCK, CANDIDATE, REVERSE = "#333961", "#007f70", "#b25b22"
SCOPES = [
    ("release_100", "Historical baseline", "Original waveforms · 100-recording release panel"),
    ("matched_original", "End-to-end comparison", "Original waveforms · 0016 and 0107"),
    ("matched_saved", "Solver and publication", "Saved detections · 0163, 0173 and 0359"),
]


def series(rows, scope, error):
    group = [r for r in rows if r["scope"] == scope]
    stock = [r for r in group if r["algorithm"] == "ALGO08v3"]
    yield stock, STOCK, "-", "o", "ALGO08v3"
    candidates = [r for r in group if r["algorithm"] == "candidate"]
    if scope == "matched_original":
        first = [r for r in candidates if r["run"] == "fix first"]
        yield first, CANDIDATE, "-", "s", "Candidate" if error else "Fix first"
        reverse = [r for r in candidates if r["run"] == "withhold first"]
        if error:
            assert sorted((r["recording"], r["c0_error_km"], r["fitted_c_error_km"]) for r in first) == sorted(
                (r["recording"], r["c0_error_km"], r["fitted_c_error_km"]) for r in reverse)
        else:
            yield reverse, REVERSE, "--", "^", "Withhold first"
    elif candidates:
        yield candidates, CANDIDATE, "-", "s", "Candidate"


def ecdf(ax, values, denominator, color, linestyle, marker, xmax):
    x, counts = np.unique(values, return_counts=True)
    fraction = np.cumsum(counts) / denominator
    ax.step([0, *x, xmax], [0, *fraction, fraction[-1]], where="post", color=color,
            lw=2, linestyle=linestyle)
    if denominator < 10:
        ax.scatter(x, fraction, marker=marker, s=38, color="white", edgecolors=color,
                   linewidths=1.6, zorder=5)


def draw(rows, metric):
    error = metric == "error"
    fields = ["c0_error_km", "fitted_c_error_km"] if error else ["elapsed_s", "cpu_s"]
    labels = ["Fixed calibration · c = 0", "Fitted calibration"] if error else ["Wall time", "Process CPU time"]
    title = "Horizontal position error on DS30" if error else "Single-core runtime on DS30"
    subtitle = ("Fraction of all recordings with a fix at or below each horizontal error."
                if error else "Fraction of all timed recordings finishing at or before each threshold.")
    fig, axes = plt.subplots(2, 3, figsize=(13.5, 7.5), sharey=True)
    fig.subplots_adjust(left=0.078, right=0.98, top=0.68, bottom=0.14, hspace=0.60, wspace=0.19)
    fig.text(0.04, 0.95, title, fontsize=21, weight="bold", color="#1d2b36")
    fig.text(0.04, 0.902, subtitle, fontsize=11, color="#526574")
    for col, (scope, heading, subheading) in enumerate(SCOPES):
        series_data = list(series(rows, scope, error))
        limit = ([4.1, 1.95, 1.57] if error else [195, 12.25, 33])[col]
        left = axes[0, col].get_position().x0
        fig.text(left, .844, heading, weight="bold", fontsize=14, color="#1d2b36")
        fig.text(left, .807, subheading, fontsize=10, color="#526574")
        handles = []
        for runs, color, style, marker, label in series_data:
            if label == "Withhold first":
                continue
            name = "Candidate" if label == "Fix first" else label
            handles.append(Line2D([], [], color=color, ls=style, lw=2.5,
                                  label=f"{name} ({len(runs)})"))
        fig.legend(handles=handles, ncol=len(handles), loc="center left",
                   bbox_to_anchor=(left, .77), frameon=False, handlelength=2,
                   borderaxespad=0, borderpad=0, columnspacing=1, fontsize=9)
        if len(series_data) == 1:
            fig.text(left, .735, "Candidate: 0 recordings measured", fontsize=10, weight="bold", color="#44515b")
        elif scope == "matched_original" and not error:
            reverse = Line2D([], [], color=REVERSE, ls="--", lw=2.4, label="Candidate, reversed run order (2)")
            fig.legend(handles=[reverse], loc="center left", bbox_to_anchor=(left, .742), frameon=False,
                       handlelength=2, borderaxespad=0, borderpad=0, fontsize=9)
        for row, (field, label) in enumerate(zip(fields, labels)):
            ax = axes[row, col]
            for runs, color, style, marker, _ in series_data:
                vals = [float(run[field]) for run in runs if run[field] != ""]
                assert vals and min(vals) >= 0 and max(vals) < limit
                ecdf(ax, vals, len(runs), color, style, marker, limit)
            ax.set_xlim(0, limit)
            ax.set_ylim(-0.035, 1.055)
            ax.set_yticks([0, .25, .5, .75, 1])
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.grid(color="#dae2e5", lw=.7)
            ax.set_axisbelow(True)
            ax.tick_params(length=0, pad=5, labelsize=9, colors="#374750")
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.set_xlabel("Horizontal error (km)" if error else "Seconds", fontsize=10)
            if col == 0:
                ax.set_ylabel("Fraction of recordings", fontsize=10)
            ax.set_title(label, loc="left", pad=3, fontsize=10, color="#374750")
            if error:
                ax.text(.98, .06, ["92/100 fixes", "1/2 fixes each", "3/3 fixes each"][col],
                        transform=ax.transAxes, ha="right", fontsize=9, color="#425761",
                        bbox=dict(facecolor="white", edgecolor="none", alpha=.9, pad=1))
    note = ("Release panel: 3 withheld, 5 solver failures. Both original-input runs withheld on 0107. "
            "Error was identical in both run orders."
            if error else "All 100 release attempts contribute runtime. Each order on the two originals "
            "is a separate series. The three saved runs exclude receiver time.")
    fig.text(0.04, .038, note, fontsize=10, color="#526574")
    fig.savefig(ROOT / (metric + ".png"), dpi=155, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    with (ROOT / "recordings.csv").open() as stream:
        records = list(csv.DictReader(stream))
    for quantity in ("runtime", "error"):
        draw(records, quantity)
