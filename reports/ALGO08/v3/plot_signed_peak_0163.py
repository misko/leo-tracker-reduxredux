"""Render the sealed signed-peak neighborhood grids without touching any samples."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path


PIN = "77dabc6821d2cd2134187e320478ddd43b30f9dd6ca38478ec0ca045e4a2ceeb"


def plot(receipt, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    from matplotlib.lines import Line2D
    import numpy as np

    raw = receipt.read_bytes()
    if sha256(raw).hexdigest() != PIN:
        raise ValueError("The sealed local score grid changed")
    result = json.loads(gzip.decompress(raw))["results"]
    fig, axes = plt.subplots(2, 2, sharex=True, sharey=True, figsize=(8.4, 6.0), layout="constrained")
    fig.suptitle("DS30-0163 · Channel 6 · Receiver 0\nOriginal 20 ms pilot verifier at both recorded peaks", fontsize=14)
    cmap = matplotlib.colormaps["RdBu_r"].copy()
    cmap.set_bad("#e1e1e1")
    norm = TwoSlopeNorm(vmin=-.01, vcenter=.025, vmax=.09)
    for row, visit in enumerate(("61", "53")):
        for col, (mode, title) in enumerate((("named", "Installed center"), ("integrated", "Sparse center"))):
            ax = axes[row, col]
            grid = result[visit]["neighborhoods"][mode]
            center = grid["center"]
            margin = np.full((17, 33), np.nan)
            for p in grid["cells"]:
                if p["inside"]:
                    margin[p["f"]+8, p["t"]+16] = p["margin"]
            image = ax.imshow(margin, origin="lower", aspect="auto", interpolation="nearest",
                              extent=(-4.125, 4.125, -2.125, 2.125), cmap=cmap, norm=norm)
            if np.nanmin(margin) < .025 < np.nanmax(margin):
                ax.contour(np.arange(-16, 17)/4, np.arange(-8, 9)/4, margin, levels=[.025], colors="#4a4a4a", linewidths=.8)
            ax.scatter(0, 0, marker="x", color="black", s=36)
            top = grid["best_margin"]
            ax.scatter(top["t"]/4, top["f"]/4, marker="o", facecolors="none", edgecolors="black", s=48, linewidths=1.15)
            ax.set_title(f"Visit {visit} · {title}\n{center['phase']:.3f} samples · {center['reference_hz']/1000:+.3f} kHz", fontsize=10)
            if col == 0:
                ax.set_ylabel("Reference CFO offset (kHz)")
            if row == 1:
                ax.set_xlabel("Epoch offset (native samples)")
    color = fig.colorbar(image, ax=axes, shrink=.8, ticks=[-.01, 0, .025, .060, .09])
    color.set_label("Exact − rolled GLRT margin (same 15 frames)")
    fig.legend(handles=[Line2D([], [], marker="x", color="black", linestyle="none", label="Recorded center"),
                        Line2D([], [], marker="o", markerfacecolor="none", color="black", linestyle="none", label="Best local margin"),
                        Line2D([], [], color="#e1e1e1", linewidth=6, label="Emitted CFO outside box")],
               fontsize=8, ncols=3, loc="outside lower center", frameon=False)
    fig.savefig(output, dpi=160)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipt", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    plot(args.receipt, args.output)
