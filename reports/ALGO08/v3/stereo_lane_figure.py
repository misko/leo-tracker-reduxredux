"""Horizontal position errors from the saved physical/South and original-IQ North comparisons."""

import argparse
from pathlib import Path

from solver_transfer_budget import DATA, receipt


def figure(output):
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    saved = receipt("stereo-mask-summary.json")["cases"]
    raw = receipt("stereo-lane-raw-north.json.gz")["score"]["outcomes"]
    north_full = receipt("anchor-cycle-route.json.gz")["revealed"]["north"]["reference"]["unfiltered_error_km"]
    labels = ["DS30-0008 · dense", "DS30-0016 · weak", "South simulation", "North simulation"]
    styles = [
        ("ALGO08v3", "o", "#364868", -.25),
        ("Both short calls", "s", "#258C87", -.08),
        ("Omit 25% of short calls", "^", "#B56B12", .09),
        ("Omit 37.5% of short calls", "D", "#973952", .26),
    ]
    fig = Figure(figsize=(10.5, 5.4))
    axes = fig.subplots(1, 2, sharey=True)
    fig.subplots_adjust(left=.19, right=.97, top=.71, bottom=.2, wspace=.085)
    fig.text(.025, .94, "Position error when one radio skips short measurements", fontsize=18, weight="bold",
             color="#21344b")
    handles = [Line2D([], [], linestyle="none", marker=m, color=c, label=t) for t, m, c, _ in styles]
    fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(.019, .885), ncol=4, frameon=False)
    for index, (ax, arm, title) in enumerate(zip(axes, ("c0", "fitted_c"), ("Fixed calibration, c = 0", "Fitted calibration"), strict=True)):
        rows = []
        for case in ("DS30-0008", "DS30-0016", "south"):
            r = saved[case]
            rows.append([r["reference"][mode][arm]["error_km"] for mode in ("named", "full")]
                        + [r["scores"][m]["arms"][arm]["error_km"] for m in ("quarter", "target")])
        rows.append([raw["stock"][arm]["error_km"], north_full[index], None, raw["candidate"][arm]["error_km"]])
        for y, row in enumerate(rows):
            for value, (_, marker, color, offset) in zip(row, styles, strict=True):
                if value is not None:
                    ax.scatter(value, y + offset, color=color, marker=marker, s=52, zorder=3)
        ax.set(xlim=(0, 2.38), ylim=(3.55, -.55), xlabel="Horizontal error (km)")
        ax.set_title(title, loc="left", weight="bold", fontsize=12)
        ax.set_yticks(range(len(labels)), labels)
        ax.grid(axis="x", color="#e1e6ea")
        ax.axhline(1.5, color="#c9d0d6", lw=.8)
        ax.tick_params(axis="both", length=0)
        ax.spines[["top", "right", "left"]].set_visible(False)
    fig.text(.025, .048, "DS30 recordings share one physical site. North’s 37.5% run started from signed I/Q. The 25% mask was not run on North.",
             fontsize=9, color="#46576a")
    fig.savefig(output, dpi=150)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=DATA.parent / "development/stereo-lane-errors.png")
    figure(parser.parse_args().output)
