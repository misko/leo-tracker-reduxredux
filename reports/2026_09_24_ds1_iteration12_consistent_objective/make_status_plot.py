#!/usr/bin/env python3
"""Plot the bounded-run outcome recorded in run-status.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    status = json.loads(args.status.read_text())
    attempts = status["attempts"]
    elapsed = [row["elapsed_s_approx"] / 60 for row in attempts]
    colors = ["#9e9e9e", "#e69f00", "#d55e00"]
    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8), constrained_layout=True)
    axes[0].bar(
        ["overlapping\nseeds", "120-iteration\ngate", "authoritative\nrun"], elapsed, color=colors
    )
    axes[0].set(ylabel="elapsed wall time (min)", title="Rejected and bounded attempts")
    axes[0].axhline(60, linestyle="--", color="0.3", label="one-hour bound")
    axes[0].legend()
    projection = status["authoritative_projected_runtime_min"]
    midpoint = (projection["low"] + projection["high"]) / 2
    error = (projection["high"] - projection["low"]) / 2
    axes[1].bar(
        ["measured at stop", "projected completion"],
        [elapsed[-1], midpoint],
        color=["#0072b2", "#cc79a7"],
    )
    axes[1].errorbar([1], [midpoint], yerr=[error], fmt="none", color="black", capsize=5)
    axes[1].axhline(60, linestyle="--", color="0.3")
    axes[1].set(ylabel="wall time (min)", title="Authoritative runtime projection")
    figure.suptitle("DS1 iteration 12 · consistent cap-800 objective · no winner published")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(args.output, dpi=180)


if __name__ == "__main__":
    main()
