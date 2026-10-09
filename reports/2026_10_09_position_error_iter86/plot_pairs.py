"""Visualize all paired outcomes without changing model or result selection."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def main():
    summary = json.loads((HERE / "summary.json").read_text())
    assert summary["complete"] and len(summary["cases"]) == 148
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for arm, color in [("fitted-c", "#1874b5"), ("zero-c", "#ca6d22")]:
        delta = []
        for row in summary["cases"]:
            fits = row["result"]["operational"]
            delta.append(1000 * (fits["protected0.25"][arm]["error_km"]
                                - fits["uniform0.5"][arm]["error_km"]))
        axes[0].plot(np.sort(delta), np.arange(1, 149) / 148, label=arm, color=color)
    axes[0].axvline(0, color="gray", linestyle="--")
    axes[0].set(xlabel="Candidate minus B7 error (m); positive is worse",
                ylabel="Fraction of all 148 scans", title="Paired error changes")
    axes[0].legend()
    groups = ["DS16", "DS17", "DS18", "Pooled"]
    x = np.arange(len(groups))
    for offset, variant, label, color in [
        (-0.18, "uniform0.5", "B7 / control", "#1874b5"),
        (0.18, "protected0.25", "Protected prior", "#ca6d22"),
    ]:
        means = [summary["groups"][g]["arms"]["fitted-c"]["variants"][variant]
                 ["position"]["mean"] for g in groups]
        axes[1].bar(x + offset, means, width=0.36, label=label, color=color)
    axes[1].axhline(0.4, color="#2c8545", linestyle="--", label="Goal: 0.4 km")
    axes[1].set(xticks=x, xticklabels=groups, ylabel="Mean position error (km)",
                title="Fitted-c; failures and fallbacks included")
    axes[1].legend()
    fig.suptitle("Geometry-prior experiment: complete consumed-development cohort")
    fig.savefig(HERE / "paired-errors.png", dpi=170)


if __name__ == "__main__":
    main()
