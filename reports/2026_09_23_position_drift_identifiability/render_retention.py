#!/usr/bin/env python3
"""Render per-scan scan-slope sensitivity retention from the saved result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = json.loads(args.input.read_text())
    scan = result["scans"]
    labels = [row["session_id"].removeprefix("scan-fw-")[:8] for row in scan]
    trace = [100 * row["slope_absorption"]["trace_retained_fraction"] for row in scan]
    east = [100 * row["slope_absorption"]["east_column_norm_retained_fraction"] for row in scan]
    north = [100 * row["slope_absorption"]["north_column_norm_retained_fraction"] for row in scan]
    x = np.arange(len(scan))
    figure, axis = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    axis.plot(x, trace, marker="o", linewidth=1.8, label="2-D trace")
    axis.plot(x, east, marker="s", linewidth=1.2, label="east column")
    axis.plot(x, north, marker="^", linewidth=1.2, label="north column")
    axis.axhline(100, color="0.4", linestyle="--", linewidth=1, label="CFO-only baseline")
    axis.set(
        xlabel="Frozen random-training scan order",
        ylabel="Sensitivity retained after shared scan slope (%)",
        ylim=(0, 105),
        xticks=x,
        xticklabels=labels,
    )
    axis.tick_params(axis="x", rotation=35, labelsize=8)
    axis.grid(axis="y", alpha=0.25)
    axis.legend(ncol=2, fontsize=8)
    figure.savefig(args.output, dpi=180)


if __name__ == "__main__":
    main()
