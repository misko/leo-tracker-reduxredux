"""Render report-only comparisons from completed fits; never optimize a position."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_18_dsx01_orbit_uncertainty"


def run():
    influence = json.loads((OUTPUT / "scan_influence_summary.json").read_text())
    following = json.loads((OUTPUT / "following_diagnostic_summary.json").read_text())
    baseline = json.loads(
        (ROOT / "reports/2026_10_18_dsx01_receiver_geometry/pooled_summary.json").read_text()
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    x = np.arange(5)
    for arm, color, offset in (("c0", "#2369ad", -0.13), ("fitted_c", "#db8521", 0.13)):
        values = [
            next(
                r["position_error_km"]
                for r in influence
                if r["omitted_scan"] == f"DSX01-S0{k}" and r["arm"] == arm
            )
            for k in range(1, 6)
        ]
        axes[0].bar(x + offset, values, width=0.25, color=color, label=arm)
        # The full-data comparator precedes the separate exact-SGP4 continuation.
        full = next(
            r
            for r in baseline
            if r["method"] == "orbit_em" and r["arm"] == arm and r["mean_sigma"] == 10
        )
        axes[0].axhline(
            full["position_error_km"], color=color, ls=":", alpha=0.8, label=f"all five, {arm}"
        )
    axes[0].set(
        xticks=x,
        xticklabels=[f"omit S0{k}" for k in range(1, 6)],
        ylabel="Position error (km)",
        title="Joint orbital fit: whole-scan influence",
    )
    axes[0].axhline(1, color="black", ls="--", lw=1)
    axes[0].legend()
    for version, marker, color in (("causal", "o", "#2369ad"), ("following", "s", "#b54b43")):
        for arm, ls in (("c0", "-"), ("fitted_c", ":")):
            values = [
                next(
                    r["position_error_km"]
                    for r in following
                    if r["case"] == f"DSX01-S0{k}" and r["version"] == version and r["arm"] == arm
                )
                for k in range(1, 6)
            ]
            axes[1].plot(x, values, marker=marker, ls=ls, color=color, label=f"{version}, {arm}")
    axes[1].set(
        xticks=x,
        xticklabels=[f"S0{k}" for k in range(1, 6)],
        ylabel="Position error (km)",
        title="Following TLE: diagnostic only",
    )
    axes[1].axhline(1, color="black", ls="--", lw=1)
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    fig.savefig(OUTPUT / "scan_influence_and_future_tle.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    run()
