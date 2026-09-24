#!/usr/bin/env python3
"""Render the sealed DS1 iteration-12 comparison."""

# ruff: noqa: E402, I001

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402


HERE = Path(__file__).resolve().parent


def main() -> None:
    summary = json.loads((HERE / "summary.json").read_text())
    results = {row["id"]: row for row in summary["results"]}
    labels = [
        "Iteration 10\ncontrol",
        "Expanded exact\nrate-only",
        "Expanded exact\n+ session scale",
    ]
    errors = [
        results["iteration10_control"]["postseal_error_km"],
        results["expanded_rate_only_level2"]["postseal_error_km"],
        results["expanded_session_scale_level2"]["postseal_error_km"],
    ]
    losses = [
        results["iteration10_control"]["balanced_exact_capped_loss"],
        results["expanded_rate_only_level2"]["balanced_exact_capped_loss"],
        results["expanded_session_scale_level2"]["balanced_exact_capped_loss"],
    ]

    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    colors = ["#6c757d", "#2a9d8f", "#277da1"]
    axes[0].bar(labels, errors, color=colors)
    axes[0].axhline(1.0, color="#d62828", linestyle="--", linewidth=1.2, label="1 km")
    axes[0].set_ylabel("Post-seal position error (km)")
    axes[0].set_title("Position result")
    axes[0].legend(frameon=False)
    for index, value in enumerate(errors):
        axes[0].text(index, value + 0.025, f"{value:.3f}", ha="center")

    axes[1].bar(labels, losses, color=colors)
    axes[1].set_ylabel("Balanced exact capped loss")
    axes[1].set_title("RF fit objective")
    axes[1].set_ylim(0.055, 0.059)
    for index, value in enumerate(losses):
        axes[1].text(index, value + 0.00008, f"{value:.5f}", ha="center", fontsize=9)

    figure.suptitle("DS1 iteration 12: expanded exact search reaches 0.787 km")
    figure.savefig(HERE / "iteration12-comparison.png", dpi=180)


if __name__ == "__main__":
    main()
