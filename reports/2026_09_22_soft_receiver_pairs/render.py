#!/usr/bin/env python3
"""Render the completed soft receiver-pair score stencil."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main() -> None:
    result = json.loads((HERE / "result.json").read_text())
    branch = next(row for row in result["branches"] if row["branch"].startswith("sacramento"))
    arms = [row for row in branch["arms"] if row["q"]]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.5), constrained_layout=True)
    for column, arm in enumerate(arms):
        east = np.asarray([row["east_km"] for row in arm["points"]]) - branch["center"][
            "east_km"
        ]
        north = np.asarray([row["north_km"] for row in arm["points"]]) - branch["center"][
            "north_km"
        ]
        for row, key, title in (
            (0, "soft_minus_independent_training_log_score", "training"),
            (1, "soft_minus_independent_heldout_log_score", "heldout"),
        ):
            values = np.asarray([point[key] for point in arm["points"]])
            scale = max(abs(values.min()), abs(values.max()), 1e-9)
            artist = axes[row, column].scatter(
                east,
                north,
                c=values,
                cmap="coolwarm",
                vmin=-scale,
                vmax=scale,
                s=260,
                marker="s",
            )
            axes[row, column].scatter([0], [0], facecolors="none", edgecolors="black", s=90)
            axes[row, column].set_aspect("equal")
            axes[row, column].set_title(f"q={arm['q']:.2f}, {title}")
            axes[row, column].set_xlabel("east from frozen finalist (km)")
            axes[row, column].set_ylabel("north from frozen finalist (km)")
            fig.colorbar(artist, ax=axes[row, column], label="soft − independent Δ")
    fig.suptitle(
        "Authorized-pair factor-only stencil (Sacramento coordinate frame)\n"
        "The stencil cannot select or move the joint receiver position",
        fontsize=12,
    )
    fig.savefig(HERE / "soft-pair-stencils.png", dpi=180)


if __name__ == "__main__":
    main()
