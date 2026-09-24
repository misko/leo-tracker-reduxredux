#!/usr/bin/env python3
"""Export reference-free iteration-11 finalist artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main() -> None:
    parser = argparse.ArgumentParser()
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
                "balanced_proposal_objective": candidate["balanced_proposal_objective"],
                "balanced_exact_capped_loss": candidate["balanced_exact_capped_loss"],
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
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "iteration11-inference-finalists.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    figure, axis = plt.subplots(figsize=(5, 4), constrained_layout=True)
    scatter = axis.scatter(
        [row["east_km_from_iteration10"] for row in rows],
        [row["north_km_from_iteration10"] for row in rows],
        c=[row["balanced_exact_capped_loss"] for row in rows],
        s=75,
        cmap="viridis",
    )
    axis.scatter(
        rows[0]["east_km_from_iteration10"],
        rows[0]["north_km_from_iteration10"],
        marker="*",
        s=210,
        c="crimson",
    )
    axis.set(xlabel="east from iteration 10 (km)", ylabel="north from iteration 10 (km)")
    figure.colorbar(scatter, ax=axis, label="balanced exact capped loss")
    figure.savefig(args.output_dir / "iteration11-inference-finalists.png", dpi=160)


if __name__ == "__main__":
    main()
