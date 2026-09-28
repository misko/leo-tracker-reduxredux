#!/usr/bin/env python3
"""Plot geometry variance support and per-lane angular excursions."""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.results.read_text())
    if result.get("schema") != "rx-geometry-support/v1":
        raise ValueError("unsupported geometry-support result")
    outputs = [args.output_prefix.with_suffix(suffix) for suffix in (".png", ".svg")]
    if any(path.exists() for path in outputs):
        raise FileExistsError("plot output already exists")

    features = result["features"]
    decomposition = result["variance_decomposition"]
    within = np.asarray(decomposition["within_fraction"], dtype=float)
    between = 1.0 - within
    lanes = sorted(
        result["lanes"],
        key=lambda row: (
            row["weighted_nominee_los_first_last_excursion_deg"],
            row["lane"]["session_id"],
            row["lane"].get("channel", 0),
        ),
    )

    figure, axes = plt.subplots(1, 2, figsize=(12, 5.5), constrained_layout=True)
    x = np.arange(len(features))
    axes[0].bar(x, within, label="within-time", color="#2864a8")
    axes[0].bar(x, between, bottom=within, label="between group means", color="#c7c7c7")
    axes[0].set_xticks(x, features, rotation=30, ha="right")
    axes[0].set_ylim(0, 1)
    axes[0].set_ylabel("fraction of weighted variance")
    axes[0].set_title("Temporal versus static geometry support")
    axes[0].legend(frameon=False)
    axes[0].grid(axis="y", alpha=0.2)

    lane_x = np.arange(len(lanes))
    excursions = [row["weighted_nominee_los_first_last_excursion_deg"] for row in lanes]
    spans = [row["time_span_s"] for row in lanes]
    points = axes[1].scatter(lane_x, excursions, c=spans, cmap="viridis", s=42)
    axes[1].set_xticks(
        lane_x,
        [row["lane"]["session_id"].removeprefix("scan-fw-")[:6] for row in lanes],
        rotation=60,
        ha="right",
        fontsize=7,
    )
    axes[1].set_ylabel("prior-weighted first–last LOS excursion (deg)")
    axes[1].set_title("Calibration lane angular excursions")
    axes[1].grid(axis="y", alpha=0.2)
    figure.colorbar(points, ax=axes[1], label="reception time span (s)")
    figure.suptitle("Receiver geometry support in calibration reception windows")
    for path in outputs:
        figure.savefig(path, dpi=180 if path.suffix == ".png" else None)
    plt.close(figure)


if __name__ == "__main__":
    main()
