"""Render geographical outcomes directly from independently scored summaries."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
COHORTS = [("field", "StarLoc field captures"), ("synthetic", "Simulated locations"),
           ("recorded", "DS29 same-roof control"), ("field2", "UK spectra (no tracks)")]
METRICS = [
    ("forced_rf", "present", "correct_region_all_attempts", "Correct region\nif forced", "#657c91"),
    ("region_only", "present", "correct_region_all_attempts",
     "Correct region\naccepted", "#337fa6"),
    ("receiver", "present", "joint_within_5km_all_attempts",
     "Fix within 5 km\nall present", "#217864"),
    ("receiver", "missing", "false_publications", "False fix\nregion missing", "#b3593c"),
]


def main():
    values = []
    for name, label in COHORTS:
        summary = json.loads((ROOT / "results" / name / "summary.json").read_bytes())
        values.append((label, summary["overall"]["by_policy"]))
    fig, axes = plt.subplots(1, len(METRICS), figsize=(11, 3.55), sharey=True)
    for i, (ax, (policy, cond, key, title, color)) in enumerate(zip(axes, METRICS, strict=True)):
        for y, (_, cohort) in enumerate(values):
            item = cohort[policy][cond][key]
            rate = item["rate"]
            ax.barh(y, 1, height=.19, color="#e9edef", zorder=0)
            ax.barh(y, rate, height=.19, color=color)
            ax.scatter(rate, y, s=23, color=color, clip_on=False, zorder=3)
            ax.text(.5, y - .17, f"{item['count']} / {item['denominator']}",
                    ha="center", va="bottom", fontsize=9, color="#26363b")
        ax.set_title(title, fontsize=11, loc="left", fontweight="bold", pad=11)
        ax.set_xlim(-.02, 1.02)
        ax.set_xticks([0, .5, 1])
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.tick_params(axis="both", length=0, labelsize=9)
        ax.spines[:].set_visible(False)
        ax.grid(axis="x", color="#edf0f1", linewidth=.6)
        ax.set_axisbelow(True)
        if i == 0:
            ax.set_yticks(range(len(values)), [label for label, _ in values])
            ax.set_ylim(len(values) - .55, -.55)
    fig.subplots_adjust(left=.215, right=.985, top=.78, bottom=.10, wspace=.25)
    fig.suptitle("Blind four-region search", x=.032, y=.985, ha="left",
                 fontweight="bold", fontsize=16)
    fig.savefig(ROOT / "results" / "blind-outcomes.png", dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
