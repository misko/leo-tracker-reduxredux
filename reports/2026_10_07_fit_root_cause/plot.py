"""Scientific figure from frozen numerical audit receipts; no fitting."""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    model = json.loads((HERE / "model/results.json").read_text())["cases"]
    path = json.loads((HERE / "derivatives/results.json").read_text())["paths"]
    intervention = json.loads((HERE / "mode_escape.json").read_text())["results"]
    improved = next(r for r in intervention if r["arm"] == "fitted-c")
    labels = ["Original near fit\n5.94 km error", "Original selected fit\n296.82 km error",
              "Timing alternatives tested\n4.80 km error"]
    cases = [model["near-original-free"], model["far-original-free"], improved]
    data = np.array([r["data_nll"] for r in cases])
    penalty = np.array([r["common_timing_penalty"] + r["relative_timing_penalty"] for r in cases])
    calibration = np.array([r["selection_score"] - r["data_nll"]
                            - r["common_timing_penalty"] - r["relative_timing_penalty"] for r in cases])
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.1), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axes[0]
    x = np.arange(3)
    ax.bar(x, data, color="#3977a5", label="Frequency data NLL")
    ax.bar(x, penalty, bottom=data, color="#de8f44", label="Timing penalty")
    ax.bar(x, calibration, bottom=data + penalty, color="#333333", label="Calibration penalty")
    for i, row in enumerate(cases):
        ax.text(i, row["selection_score"] + 600, f'{row["selection_score"]:,.0f}', ha="center", weight="bold")
        ax.text(i, data[i] / 2, f'{data[i]:,.0f}', ha="center", color="white")
        if penalty[i] > 3000:
            ax.text(i, data[i] + penalty[i] / 2, f'{penalty[i]:,.0f}', ha="center")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 54000)
    ax.set_ylabel("Selection score (lower is better)")
    ax.set_title("Timing costs reversed the location ranking", loc="left", weight="bold", pad=16)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.15), ncol=2)
    ax = axes[1]
    fraction = np.array([r["fraction"] for r in path]) * 100
    delta = np.array([r["objective"] - path[0]["objective"] for r in path])
    ax.plot(fraction, delta, "o-", color="#3977a5", markersize=4)
    ax.axhline(0, color="#555555", lw=1, linestyle="--")
    ax.scatter([fraction[1]], [delta[1]], color="#de8f44", zorder=5, s=50)
    ax.annotate("Initially 472 points worse", (fraction[1], delta[1]), xytext=(25, 700),
                arrowprops={"arrowstyle": "->", "color": "#555555"})
    ax.set_ylim(min(delta) - 200, 1100)
    ax.set_xlabel("Progress along a feasible path to the saved zero-c solution (%)")
    ax.set_ylabel("Objective change from original near fit")
    ax.set_title("A local optimizer faces a score barrier", loc="left", weight="bold", pad=16)
    ax.text(.02, .05, "This is an objective diagnostic,\nnot the optimizer's trajectory.",
            transform=ax.transAxes, fontsize=9, color="#555555")
    fig.suptitle("18:38 capture: V16 timing-mode failure", x=.06, ha="left", weight="bold", fontsize=15)
    fig.subplots_adjust(left=.065, right=.985, top=.83, bottom=.23, wspace=.34)
    fig.savefig(HERE / "diagnosis.png", dpi=170)
    fig.savefig(HERE / "diagnosis.svg")


if __name__ == "__main__":
    main()
