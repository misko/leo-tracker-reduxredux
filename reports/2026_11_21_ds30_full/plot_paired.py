"""Plot the per-recording fitted-calibration comparison from the published CSV."""

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import ScalarFormatter


def draw(folder):
    with (folder / "paired.csv").open() as stream:
        rows = [r for r in csv.DictReader(stream) if r["calibration"] == "fitted_c"]
    pairs = [r for r in rows if r["original_km"] and r["compact_km"]]
    original = np.array([float(r["original_km"]) for r in pairs])
    compact = np.array([float(r["compact_km"]) for r in pairs])
    closer = compact < original
    ink, teal, blue = "#192f3c", "#087d71", "#415985"
    fig, (plot, counts) = plt.subplots(1, 2, figsize=(10.8, 5.2),
                                       gridspec_kw={"width_ratios": [1.2, 1]})
    fig.subplots_adjust(left=.095, right=.955, bottom=.15, top=.76, wspace=.54)
    fig.text(.06, .92, "Two fixes for the same recording", weight="bold", fontsize=21, color=ink)
    fig.text(.06, .855, "Gauss roof  ·  DS30 revision 1  ·  fitted RF calibration",
             fontsize=11, color="#536675")
    ticks = [.03, .1, .3, 1, 3, 10]
    low = min(original.min(), compact.min()) * .8
    high = max(original.max(), compact.max()) * 1.2
    plot.plot([low, high], [low, high], color="#87959e", lw=1, ls="--", zorder=0)
    for mask, color in ((~closer, blue), (closer, teal)):
        plot.scatter(original[mask], compact[mask], s=14, color=color, alpha=.65, linewidths=0)
    plot.set(xscale="log", yscale="log", xlim=(low, high), ylim=(low, high),
             xlabel="algo07v5 error (km)", ylabel="Two-scan compact v5 error (km)")
    for axis in (plot.xaxis, plot.yaxis):
        axis.set_ticks([t for t in ticks if low <= t <= high])
        axis.set_major_formatter(ScalarFormatter())
    plot.set_aspect("equal", adjustable="box")
    plot.set_title(f"{len(pairs)} shared fixes", loc="left", weight="bold")
    plot.grid(alpha=.16)
    groups = [("Compact closer", int(closer.sum()), teal),
              ("Original closer", int((original < compact).sum()), blue),
              ("Compact only", sum(bool(r["compact_km"]) and not r["original_km"] for r in rows), teal),
              ("Original only", sum(bool(r["original_km"]) and not r["compact_km"] for r in rows), blue),
              ("Neither fixed", sum(not r["original_km"] and not r["compact_km"] for r in rows), "#7e8d97")]
    counts.set_title(f"All {len(rows)} recordings", loc="left", weight="bold")
    for i, (name, value, color) in enumerate(groups):
        counts.barh(i, value, color=color, height=.54)
        counts.text(value + 4, i, str(value), va="center", color=ink)
    counts.set_yticks(range(len(groups)), [g[0] for g in groups])
    counts.invert_yaxis()
    counts.set_xlim(0, max(g[1] for g in groups) * 1.16)
    counts.set_xlabel("Recordings")
    for ax in (plot, counts):
        ax.spines[["right", "top"]].set_visible(False)
    fig.savefig(folder / "paired-fixes.png", dpi=180, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    draw(Path(__file__).resolve().parent)
