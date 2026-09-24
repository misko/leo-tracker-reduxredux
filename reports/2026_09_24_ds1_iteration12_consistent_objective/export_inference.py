#!/usr/bin/env python3
"""Export reference-free iteration-12 comparison artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib
import numpy as np
from scipy.stats import spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def distance_km(first: dict[str, float], second: dict[str, float]) -> float:
    mean_latitude = math.radians((first["latitude_deg"] + second["latitude_deg"]) / 2)
    north = (first["latitude_deg"] - second["latitude_deg"]) * 111.32
    east = (first["longitude_deg"] - second["longitude_deg"]) * 111.32 * math.cos(mean_latitude)
    return math.hypot(east, north)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.inference.read_text())
    if data.get("reference_used_for_fit") is not False:
        raise ValueError("truth-contaminated inference")
    rows = []
    for rank, candidate in enumerate(data["exact_finalists"], 1):
        group00 = candidate["best_exact_by_group"]["20260921_00"]
        group16 = candidate["best_exact_by_group"]["20260921_16"]
        rows.append(
            {
                "exact_rank": rank,
                "east_km_from_iteration10": candidate["east_km_from_iteration10"],
                "north_km_from_iteration10": candidate["north_km_from_iteration10"],
                "latitude_deg": candidate["latitude_deg"],
                "longitude_deg": candidate["longitude_deg"],
                "balanced_proposal_cap800_loss": candidate["balanced_proposal_objective"],
                "balanced_exact_cap800_loss": candidate["balanced_exact_capped_loss"],
                "proposal_exact_delta": (
                    candidate["balanced_proposal_objective"]
                    - candidate["balanced_exact_capped_loss"]
                ),
                "group_00_tau_s": group00["tau_s"],
                "group_00_exact_loss": group00["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "group_16_tau_s": group16["tau_s"],
                "group_16_exact_loss": group16["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
            }
        )
    proposal = np.asarray([row["balanced_proposal_cap800_loss"] for row in rows])
    exact = np.asarray([row["balanced_exact_cap800_loss"] for row in rows])
    correlation = float(spearmanr(proposal, exact).statistic)
    winner = data["winner"]
    summary = {
        "schema": "ds1-iteration12-inference-summary/v1",
        "reference_used": False,
        "elapsed_s": data["elapsed_s"],
        "workers": data["workers"],
        "level_coordinate_counts": [row["coordinate_count"] for row in data["levels"]],
        "exact_audit_count": data["exact_audit_count"],
        "exact_gate_pass_count": sum(
            audit["exact_comparison"]["exact_sgp4_gate"]["passed"]
            for candidate in data["exact_finalists"]
            for audit in candidate["best_exact_by_group"].values()
        ),
        "proposal_exact_spearman": correlation,
        "proposal_exact_mean_absolute_delta": float(np.mean(np.abs(proposal - exact))),
        "winner": {
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
            "balanced_proposal_cap800_loss": winner["balanced_proposal_objective"],
            "balanced_exact_cap800_loss": winner["balanced_exact_capped_loss"],
        },
        "winner_distance_from_seed_km": {
            name: distance_km(winner, seed) for name, seed in data["seeds"].items()
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration12-inference-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    with (args.output_dir / "iteration12-inference-finalists.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    figure, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    scatter = axes[0].scatter(
        [row["east_km_from_iteration10"] for row in rows],
        [row["north_km_from_iteration10"] for row in rows],
        c=exact,
        s=80,
        cmap="viridis",
    )
    axes[0].scatter(
        rows[0]["east_km_from_iteration10"],
        rows[0]["north_km_from_iteration10"],
        marker="*",
        c="crimson",
        s=220,
        label="exact winner",
    )
    axes[0].set(
        xlabel="east from iteration 10 (km)",
        ylabel="north from iteration 10 (km)",
        title="Exact finalist surface",
    )
    axes[0].legend()
    figure.colorbar(scatter, ax=axes[0], label="balanced exact cap-800 loss")
    axes[1].scatter(proposal, exact, c=np.arange(1, len(rows) + 1), cmap="plasma", s=70)
    low = min(float(np.min(proposal)), float(np.min(exact)))
    high = max(float(np.max(proposal)), float(np.max(exact)))
    axes[1].plot([low, high], [low, high], linestyle="--", color="0.4", label="identity")
    axes[1].set(
        xlabel="proposal cap-800 loss",
        ylabel="exact cap-800 loss",
        title=f"Matched objective; rank correlation {correlation:.2f}",
    )
    axes[1].legend()
    figure.suptitle("DS1 iteration 12 · consistent proposal/exact objective")
    figure.savefig(args.output_dir / "iteration12-consistent-objective.png", dpi=180)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
