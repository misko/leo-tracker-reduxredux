"""Plot conditional tile mass and its independent held comparison by offer."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from ..__main__ import local_output
from .tile_region_support_trials import OUT, read_rows

MODES = {"matched-tile": "containing", "edge-tile": "near edge", "omitted-tile": "omitted"}


def offer_label(row, index):
    site = row["capture_id"]
    if row["cohort"] == "fresh":
        name = f"Fresh site {list(index['fresh']).index(site) + 1}"
    else:
        name = f"Prior {index['replay'][site]['previous_study']}"
    return f"{name} · {MODES[row['mode']]}"


def draw(report):
    rows = read_rows(report / "raw-positions.jsonl.gz")
    index = json.loads((report / "labels.json").read_bytes())
    mode_order = {mode: i for i, mode in enumerate(MODES)}
    rows.sort(
        key=lambda row: (
            row["cohort"] != "fresh",
            list(index[row["cohort"]]).index(row["capture_id"]),
            mode_order[row["mode"]],
        )
    )
    labels = []
    mass, gain = [], []
    for row in rows:
        labels.append(offer_label(row, index))
        metrics = row["result"]["metrics"].get("geographic_gate", {})
        mass.append(metrics.get("conditional_tile_mass_lower"))
        gain.append(metrics.get("worst_delete_orbit_held_gain"))

    fig, (a, b) = plt.subplots(1, 2, figsize=(9.3, 4.4), sharey=True, layout="constrained")
    y = np.arange(len(rows))
    a.set_yticks(y, labels)
    a.invert_yaxis()
    a.axvline(0.95, color="#687786", linestyle="--", linewidth=1)
    b.axvline(0.0, color="#687786", linestyle="--", linewidth=1)
    a.set_xlim(-0.035, 1.04)
    a.set_xlabel("Conditional tile mass lower bound")
    b.set_xlabel("Held log gain per orbit after strongest vote removed")
    b.set_xscale("symlog", linthresh=0.02)
    for axes in (a, b):
        axes.grid(axis="x", color="#d7dfe6", linewidth=0.65, alpha=0.8)
        axes.spines[["top", "right"]].set_visible(False)
    for j, row in enumerate(rows):
        status = row["result"]["status"]
        filled = status == "ok"
        color = "#b94f31" if row["mode"] == "omitted-tile" else "#0b6586"
        for axes, values in ((a, mass), (b, gain)):
            if values[j] is None:
                axes.text(
                    0.04,
                    j,
                    status.replace("_", " "),
                    transform=axes.get_yaxis_transform(),
                    va="center",
                    color="#4a545c",
                    fontsize=9,
                )
            else:
                axes.scatter(
                    values[j],
                    j,
                    s=46,
                    facecolors=color if filled else "white",
                    edgecolors=color,
                    linewidth=1.4,
                    zorder=3,
                )
    fig.suptitle("Doppler support for the offered tile", weight="bold", x=0.04, ha="left")
    b.legend(
        handles=[
            Line2D(
                [],
                [],
                marker="o",
                color="none",
                markeredgecolor="#273846",
                markerfacecolor=face,
                label=label,
            )
            for face, label in (("#273846", "Published"), ("white", "Withheld"))
        ],
        loc="lower left",
        frameon=False,
        fontsize=8,
    )
    fig.savefig(
        report / "held-region-support.png",
        dpi=160,
        metadata={"Title": "Held Doppler region support"},
    )
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    args = parser.parse_args()
    draw(local_output(args.report))


if __name__ == "__main__":
    main()
