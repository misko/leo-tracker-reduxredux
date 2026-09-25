#!/usr/bin/env python3
"""Plot paired iteration-31 exact-state preflight evidence without truth."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
RESULT = HERE / "preflight-v2.json"
OUTPUT = HERE / "preflight-summary.png"


def main() -> None:
    result = json.loads(RESULT.read_text())
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for column, dataset in enumerate(("DS1", "DS3")):
        row = result["datasets"][dataset]
        cells = row["cells"]
        east = sorted({cell["east_km"] for cell in cells})
        north = sorted({cell["north_km"] for cell in cells})
        surface = np.full((len(north), len(east)), np.nan)
        for cell in cells:
            surface[north.index(cell["north_km"]), east.index(cell["east_km"])] = cell["score"]
        east_step = east[1] - east[0]
        north_step = north[1] - north[0]
        image = axes[0, column].imshow(
            surface,
            origin="lower",
            extent=(
                min(east) - east_step / 2,
                max(east) + east_step / 2,
                min(north) - north_step / 2,
                max(north) + north_step / 2,
            ),
            aspect="auto",
            cmap="viridis_r",
        )
        winner = min(cells, key=lambda cell: cell["score"])
        axes[0, column].scatter(
            winner["east_km"], winner["north_km"], marker="*", s=180, color="red", edgecolor="black"
        )
        axes[0, column].set_title(f"{dataset} exact-state bounded RF surface")
        axes[0, column].set_xlabel("East offset (km)")
        axes[0, column].set_ylabel("North offset (km)")
        fig.colorbar(image, ax=axes[0, column], label="Soft capped score")

        summary = row["candidate_summary"]
        counts = [
            summary["tracks"] - summary["ambiguous_tracks"],
            summary["top2_tracks"],
            summary["top3_tracks"],
        ]
        axes[1, column].bar(
            ["fixed K=1", "soft K=2", "soft K=3"], counts, color=["#4c78a8", "#f58518", "#e45756"]
        )
        axes[1, column].set_title(
            f"{dataset} exact cross-fit retention · T={summary['temperature_hz']:.0f} Hz"
        )
        axes[1, column].set_ylabel("Tracks")
        axes[1, column].grid(axis="y", alpha=0.25)
    fig.suptitle(
        "Iteration 31 exact-state paired preflight · no full search",
        fontsize=15,
    )
    fig.savefig(OUTPUT, dpi=180)
    plt.close(fig)


if __name__ == "__main__":
    main()
