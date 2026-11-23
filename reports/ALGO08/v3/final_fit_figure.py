"""Draw measured elapsed times and position errors from the two sealed 0402 studies."""

import gzip
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


HERE = Path(__file__).resolve().parent


def load_receipt(name):
    with gzip.open(HERE / "measurements" / (name + ".json.gz"), "rt") as stream:
        return json.load(stream)


def render():
    first = load_receipt("isolated-salvage-0402")
    final = load_receipt("named-survivor-fit-0402")
    keys = ("named", "cumulative", "endpoint_only", "isolated_plus_endpoint")
    labels = ["Named ALGO08v3", "Fast solver", "Repair endpoint", "Isolate family + repair", "Add original final fit"]
    times = [first["comparison_clocks"][k]["elapsed_s"] for k in keys[:3]] + [
        first["process"]["elapsed_s"], final["clocks"]["fixed"]["timing"]["elapsed_s"]]
    colors = ["#404966", "#b7c2d2", "#a3b6ca", "#62959d", "#087b70"]
    y = np.arange(len(labels))
    fig, (time_ax, error_ax) = plt.subplots(1, 2, figsize=(10.8, 4.2), sharey=True, layout="constrained")
    time_ax.barh(y, times, color=colors, height=.54)
    for i, t in enumerate(times):
        time_ax.text(t + 1, i, f"{t:.2f}", va="center", fontsize=9)
    time_ax.set(yticks=y, yticklabels=labels, xlim=(0, 86), xlabel="Saved detections to process exit (s)")
    time_ax.invert_yaxis()
    for arm, offset, marker, color, label in (
            ("c0", -.10, "o", "#33538a", "Zero calibration"),
            ("fitted_c", .10, "D", "#cc7317", "Fitted calibration")):
        values = [1000 * first["scores"][k][arm]["horizontal_error_km"] for k in keys]
        values.append(1000 * final["horizontal_error_km"]["fixed"][arm])
        error_ax.scatter(values, y + offset, s=30, marker=marker, color=color, label=label)
    error_ax.set(xlim=(849, 963), xlabel="Horizontal position error (m)")
    error_ax.legend(loc="upper center", bbox_to_anchor=(.5, -.18), ncol=2, frameon=False, fontsize=9)
    for ax in (time_ax, error_ax):
        ax.grid(axis="x", alpha=.18)
        ax.set_axisbelow(True)
        ax.spines[["right", "top", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("DS30-0402   ·   Original final fit recovers the v3 position", fontsize=15, fontweight="bold")
    fig.savefig(HERE / "development/final-fit-0402.png", dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    render()
