"""Render the matched field region experiment in the original offer's local frame."""

import gzip
import json
import math
from pathlib import Path

from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from reports.ALGO08.v3.full_successor_score import ROOT, checked, roster


RECEIPT = "45ba5b1634f80a4b0f052f89281e44ba16eb4186fc70b79763336fd79120de2d"


def figure(summary, reference):
    center = summary["original"]["region"]["center"]
    scale = 111.32 * math.cos(math.radians(center[0]))
    roof = (reference[1] - center[1]) * scale
    fig = Figure(figsize=(10.1, 4.45), dpi=150)
    ax = fig.subplots()
    fig.subplots_adjust(left=.18, right=.835, top=.67, bottom=.21)
    fig.text(.045, .925, "The same recording with three search regions", fontsize=18, weight="bold")
    fig.text(.046, .851, "DS30-0086  ·  Candidate with fitted calibration  ·  East–west cross-section", fontsize=11)
    offered, point, truth = "#cbdfea", "#125278", "#a64320"
    rows = [(2, "original", "Original"), (1, "east", "12.5 km east"), (0, "west", "12.5 km west")]
    for y, key, _ in rows:
        record = summary[key]
        region, arm = record["region"], record["arms"]["fitted_c"]
        cx = (region["center"][1] - center[1]) * scale
        ax.barh(y, region["width_km"], left=cx-region["width_km"]/2, height=.43,
                color=offered, edgecolor="#789aab", linewidth=.85)
        x = (arm["latlon"][1] - center[1]) * scale
        ax.scatter(x, y, c=point, marker="D", s=48, edgecolor="white", linewidth=.7, zorder=4)
        ax.text(1.025, y, f"{arm['error_km']:.3f} km", va="center", transform=ax.get_yaxis_transform(), fontsize=10.5)
    ax.axvline(roof, color=truth, linewidth=1.5, linestyle="--", zorder=3)
    ax.text(1.025, 1.05, "Horizontal error", transform=ax.transAxes, weight="bold", fontsize=9)
    ax.set(yticks=[y for y, _, _ in rows], yticklabels=[name for _, _, name in rows],
           xlim=(-27, 27), ylim=(-.48, 2.48), xlabel="East of the original search center (km)")
    ax.spines[["top", "left", "right"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e3e8eb")
    ax.set_axisbelow(True)
    fig.legend(handles=[Patch(facecolor=offered, label="Offered width"),
                        Line2D([], [], color=truth, ls="--", label="Surveyed receiver"),
                        Line2D([], [], color=point, ls="", marker="D", label="Returned position")],
               loc="upper left", bbox_to_anchor=(.038, .827), frameon=False, ncols=3)
    fig.text(.046, .045, "All three runs returned a fix. The reported errors include both east–west and north–south displacement.",
             fontsize=9, color="#455663")
    return fig


if __name__ == "__main__":
    folder = ROOT/"reports/ALGO08/v3"
    receipt = json.loads(checked(gzip.decompress((folder/"measurements/field-offer-translation-0086.json.gz").read_bytes()), RECEIPT))
    figure(receipt["summary"], roster()["DS30-0086"]["reference"]).savefig(folder/"development/ds30-0086-region-translation.png")
