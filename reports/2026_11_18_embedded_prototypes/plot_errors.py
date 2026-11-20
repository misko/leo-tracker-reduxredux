"""Plot the independent, per-recording scores from compare.py."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bench import CASES


ROOT = Path(__file__).resolve().parent
LABELS = {
    "v5_r0": "Historical v5",
    "06_coreset": "12 tracks chosen by geometry",
    "10_network": "Tiny neural network",
    "01_stream": "Streaming tracker",
    "02_pilots": "Guided pilot search",
    "08_grid": "Marginalized position grid",
    "03_consensus": "Satellite-family consensus",
    "04_compact": "Packed orbit table",
    "07_differences": "Doppler changes only",
    "09_events": "Pass-event timing only",
    "05_stationary": "Prior-fix forecast",
}


def main():
    with (ROOT / "scores.csv").open(newline="") as handle:
        values = {(r["method"], r["case"]): float(r["error_km"]) if r["error_km"] else np.nan
                  for r in csv.DictReader(handle) if r["arm"] == "fitted_c"}
    data = np.array([[values[method, case] for case in CASES] for method in LABELS])
    fig, ax = plt.subplots(figsize=(10.2, 5.8))
    fig.subplots_adjust(left=.27, right=.975, top=.82, bottom=.105)
    cmap = plt.get_cmap("YlGnBu").copy()
    cmap.set_bad("#eeeeee")
    ax.imshow(data, vmin=0, vmax=11, aspect="auto", cmap=cmap)
    for row, vals in enumerate(data):
        for col, error in enumerate(vals):
            color = "white" if error >= 6.4 else "#182329"
            display = f"{error:.1f}" if np.isfinite(error) else "—"
            ax.text(col, row, display, ha="center", va="center", color=color, fontsize=10)
    for edge in (.5, 9.5):
        ax.axhline(edge, color="white", linewidth=4)
    ax.set_yticks(range(len(LABELS)), labels=list(LABELS.values()))
    ax.set_xticks(range(len(CASES)), labels=[c.removeprefix("DS26-") for c in CASES])
    ax.xaxis.tick_top()
    ax.tick_params(axis="both", length=0, pad=7, labelsize=10, colors="#152932")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.text(.04, .952, "Position error on eight DS26 scans", fontsize=19,
             fontweight="bold", color="#142b35")
    fig.text(.04, .895, "Kilometers from the receiver site with fitted calibration. Each column is a DS26 scan.",
             fontsize=10, color="#354850")
    fig.text(.04, .038, "Darker cells indicate larger error. A dash means the model withheld a fix. The last row uses earlier scans.",
             fontsize=9, color="#354850")
    fig.savefig(ROOT / "position-errors.png", dpi=160, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
