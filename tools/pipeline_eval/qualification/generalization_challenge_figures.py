"""Draw site-level geography and publication outcomes against tile-face clearance."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from ..__main__ import local_output
from ..scoring import ARMS
from .generalization_challenge import METHODS, OUT

LABELS = ("Smooth clock", "Joint orbit", "Fixed training")
TILES = ("omitted", "outside-edge", "inside-edge", "present")
CLEARANCE = ("−25 km", "−2 km", "+1.5 km", "+5 km")
STATUS = {"withheld": "W", "failed": "F", "timed_out": "T", "missing": "M", "unavailable": "U"}
PALETTE = ListedColormap(["#edf0f2", "#b8d9e5", "#f2ad94", "#edd9a4"])


def draw(report):
    data = json.loads((report / "scores.json").read_bytes())["rows"]
    rows = {(r["method"], r["arm"], r["site"], r["condition"]): r for r in data}
    sites = sorted({r["site"] for r in data if r["site"] is not None})
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.7), layout="constrained", sharey=True)
    for i, arm in enumerate(ARMS):
        for j, (method, title) in enumerate(zip(METHODS, LABELS, strict=True)):
            ax = axes[i, j]
            code = np.zeros((len(sites), len(TILES)))
            labels = {}
            for y, site in enumerate(sites):
                for x, condition in enumerate(TILES):
                    row = rows[method, arm, site, condition]
                    if row["published"]:
                        code[y, x] = 2 if row["boundary_clearance_km"] < 0 else 1
                        labels[x, y] = f"{row['position_error_km']:.2f}"
                    else:
                        code[y, x] = 0 if row["status"] == "withheld" else 3
                        labels[x, y] = STATUS[row["status"]]
            ax.imshow(code, cmap=PALETTE, vmin=0, vmax=3, aspect="auto")
            for (x, y), val in labels.items():
                ax.text(x, y, val, va="center", ha="center", color="#192d3d", fontsize=9)
            ax.set_xticks(range(len(TILES)), CLEARANCE)
            ax.set_yticks(range(len(sites)), [f"Site {s}" for s in sites])
            ax.tick_params(length=0)
            ax.axvline(1.5, color="white", linewidth=3)
            for spine in ax.spines.values():
                spine.set_visible(False)
            if i == 0:
                ax.set_title(title, fontweight="semibold", color="#192d3d")
            if j == 0:
                ax.set_ylabel("Zero calibration" if i == 0 else "Fitted calibration")
    fig.suptitle("Published position error by distance to the offered tile face", fontweight="bold")
    fig.supxlabel(
        "Numbers mark position error in km. Negative clearance means outside. "
        "W withheld · F failed · T timeout · M missing.",
        fontsize=9,
    )
    fig.savefig(report / "boundary-publication.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=OUT)
    draw(local_output(parser.parse_args().report))


if __name__ == "__main__":
    main()
