#!/usr/bin/env python3
"""Render the sealed DS1/DS2/DS3 post-seal comparison as a PNG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, default=HERE / "evaluation.json")
    parser.add_argument("--output", type=Path, default=HERE / "postseal-comparison.png")
    args = parser.parse_args()
    document = json.loads(args.evaluation.read_text())
    comparison = document["comparison"][:3]
    all56 = [row for row in document["rows"] if row["scope"] == "all56"]
    geometry = [row for row in document["rows"] if row["scope"] == "geometry5"]
    figure, axes = plt.subplots(1, 3, figsize=(15, 5), layout="constrained")
    panels = [
        (
            axes[0],
            [row["dataset_scope"] for row in comparison],
            [row["best_error_km"] for row in comparison],
            "Best by dataset",
            "#4c78a8",
        ),
        (
            axes[1],
            [row["model_id"] for row in all56],
            [row["postseal_error_km"] for row in all56],
            "DS3 all56 models",
            "#54a24b",
        ),
        (
            axes[2],
            [row["model_id"] for row in geometry],
            [row["postseal_error_km"] for row in geometry],
            "DS3 geometry5 diagnostics",
            "#e45756",
        ),
    ]
    for axis, labels, values, title, color in panels:
        bars = axis.bar(labels, values, color=color)
        axis.set_ylabel("Post-seal great-circle error (km)")
        axis.set_title(title)
        axis.tick_params(axis="x", rotation=32, labelsize=8)
        axis.margins(y=0.14)
        for bar, value in zip(bars, values, strict=True):
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                value,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    figure.suptitle("DS1 / DS2 / DS3 post-seal positioning comparison")
    figure.savefig(args.output, dpi=180)


if __name__ == "__main__":
    main()
