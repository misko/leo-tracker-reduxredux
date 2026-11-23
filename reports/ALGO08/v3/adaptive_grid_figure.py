"""Show actual conditional scores retained in the adaptive sampling experiment."""

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np

from .adaptive_grid_screen import DATA, HERE, checked_grid, coordinates, sources


def render():
    inputs = sources()
    results = json.loads((DATA/"adaptive-grid.json").read_bytes())
    fig, axes = plt.subplots(2, 2, figsize=(8, 7), layout="constrained", sharex=True, sharey=True)
    for column, case in enumerate(("DS30-0008", "DS30-0016")):
        root, reference = inputs[case]
        grid = checked_grid(Path(root), reference)
        selected = set(map(tuple, results[case]["selected_xy"]))
        values = [row["scores"]["fitted_c"] for row in grid["points"]]
        low = min(v for v in values if v is not None)
        for index, ax in enumerate(axes[:, column]):
            rows = [p for p in grid["points"] if not index or coordinates(p) in selected]
            xy = np.array([coordinates(p) for p in rows])
            colors = [p["scores"]["fitted_c"] - low if p["scores"]["fitted_c"] is not None else np.nan for p in rows]
            scatter = ax.scatter(*xy.T, c=colors, s=17, cmap="viridis_r", norm=Normalize(0, 4.5, clip=True))
            ax.set(aspect="equal", xlabel="East (km)", ylabel="North (km)",
                   title=f"{case} · {len(rows)} evaluated locations")
            ax.set_xticks([-12.5, 0, 12.5])
            ax.set_yticks([-12.5, 0, 12.5])
    fig.colorbar(scatter, ax=axes, shrink=.75, label="Fitted conditional loss above minimum (capped at 4.5)")
    fig.suptitle("Original grid (top) and retained measurements (bottom)", weight="bold")
    fig.savefig(HERE/"development/adaptive-grid.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    render()
