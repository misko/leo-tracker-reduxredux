"""Measured error and northern raw publication timings at their observed boundaries."""

import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt


def plot(root):
    records = root / "measurements"
    interlaced = json.loads((records/"interlaced-lanes.json").read_bytes())["cases"]
    north = json.loads(gzip.decompress((records/"north-interlaced-raw.json.gz").read_bytes()))
    fig, (err, timing) = plt.subplots(1, 2, figsize=(10.8, 4.6), constrained_layout=True)
    sites = {"DS30-0016": interlaced["DS30-0016"], "South · simulated": interlaced["south-containing"],
             "North · simulated": {new: dict(arms=north["transfer"]["scores"][old])
                                   for new, old in (("complete", "baseline"), ("interlaced","candidate"))}}
    for y, (name, values) in enumerate(sites.items()):
        for mode, offset, marker, color in (("complete", -.12, "o", "#156b79"), ("interlaced", .12, "D", "#b84c20")):
            for arm, fill in (("c0", "white"), ("fitted_c", color)):
                x = values[mode]["arms"][arm]["error_km"]
                err.scatter(x, y+offset, marker=marker, s=67, facecolor=fill, edgecolor=color, lw=1.5, zorder=3,
                            label=(("Complete" if mode=="complete" else "Staggered")
                                   + (" · zero" if arm=="c0" else " · fitted")) if y==0 else None)
    err.set(yticks=range(3), yticklabels=list(sites), xlabel="Horizontal error (km)", title="Matched containing offers",
            xlim=(0, 1.82), ylim=(-.45, 2.6))
    err.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(.53,1.), fontsize=8)
    phases = [("acquisition_lock_to_detections", "Through detections", "#37788b"),
              ("detections_to_terminal", "Through position", "#5f8d67"),
              ("terminal_to_report", "Through web report", "#ca955a")]
    for i, run in enumerate(("baseline","candidate")):
        start = 0.
        times = north["runs"][run]["file_stamp_intervals_s"]
        for key, label, color in phases:
            duration = times[key]
            timing.barh(i, duration, left=start, color=color, height=.42, label=label if i==0 else None)
            start += duration
        timing.text(start+.12, i, f"{start:.2f} s", va="center")
    timing.set(xlabel="Seconds between publication file timestamps", title="Northern raw-to-web transfer",
               yticks=[0,1], yticklabels=["ALGO08v3","Staggered"], xlim=(0,17.5), ylim=(-.55,1.9))
    timing.legend(frameon=False, ncol=1, fontsize=8, loc="upper right")
    for ax in (err,timing):
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=.18)
        ax.spines[["right","top"]].set_visible(False)
    fig.savefig(root/"development/interlaced-transfer.png", dpi=175)
    plt.close(fig)


if __name__ == "__main__":
    plot(Path(__file__).resolve().parent)
