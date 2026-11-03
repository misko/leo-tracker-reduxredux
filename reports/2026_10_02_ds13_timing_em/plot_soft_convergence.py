"""Post-evaluation convergence traces; location error never feeds fitting."""

from __future__ import annotations

import json

import numpy as np
from finite_set_fit import assert_snapshot_unchanged
from joint_inputs import _coordinates, _ecef
from prepare_scans import ROOT


def plot():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result = json.loads((ROOT / "comparison-soft.json").read_text())
    assert_snapshot_unchanged(result["source_hashes"])
    figure, axes = plt.subplots(3, 2, figsize=(13, 11))
    for column, seed in enumerate(result["initializers"]):
        session = seed["session"]
        site = json.loads((ROOT / "scans" / session / "evaluation.json").read_text())[
            "reference_site"]
        reference = _ecef(site["latitude_deg"], site["longitude_deg"])
        rows = [row for row in result["rows"] if row["session"] == session
                and row["method"] != "direct" and row["error_km"] is not None]
        for row in rows:
            method, tolerance = row["method"], row["tolerance"]
            directory = (
                ROOT / "runs-soft" / session / f"fisher-{tolerance}" if method == "fisher"
                else ROOT / "runs-continuation" / session / tolerance)
            fitted = json.loads((directory / "fit.json").read_text())["fit"]
            trace = fitted["accepted_trace"]
            if not trace:
                continue
            elapsed = [entry["elapsed_s"] for entry in trace]
            label = f"{method} {tolerance}" + (" [converged]" if row["success"] else "")
            style = "--" if method == "continuation" else "-"
            axes[0, column].semilogy(
                elapsed, [max(entry["projected_gradient_inf_norm"], 1e-10) for entry in trace],
                linestyle=style, label=label)
            axes[1, column].semilogy(
                elapsed, [max(entry["objective"] - fitted["objective"], 1e-9) for entry in trace],
                linestyle=style)
            errors = [float(np.linalg.norm(_ecef(*_coordinates(
                np.asarray(entry["vector"])[:2])) - reference)) for entry in trace]
            axes[2, column].plot(elapsed, errors, linestyle=style)
        axes[0, column].axhline(1e-3, color="black", linestyle=":", label="Gradient threshold")
        axes[0, column].set_title(session)
        axes[0, column].legend(fontsize=8)
        axes[2, column].axhline(seed["error_km"], color="gray", linestyle="--")
        axes[2, column].axhline(1, color="gray", linestyle=":")
        for axis in axes[:, column]:
            axis.grid(alpha=0.2)
            axis.set_xlabel("Seconds within this fit (warm-start predecessor time excluded)")
    axes[0, 0].set_ylabel("Scaled projected gradient infinity norm")
    axes[1, 0].set_ylabel("Objective above returned best (floor 1e-9)")
    axes[2, 0].set_ylabel("Position error (km), post-fit evaluation only")
    figure.suptitle("DS13: local objective convergence versus localization accuracy")
    figure.tight_layout()
    figure.savefig(ROOT / "convergence-soft.png", dpi=150)
    figure.savefig(ROOT / "convergence-soft.svg")
    plt.close(figure)


if __name__ == "__main__":
    plot()
