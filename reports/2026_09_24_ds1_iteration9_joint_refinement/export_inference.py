#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inference", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    d = json.loads(a.inference.read_text())
    if d.get("reference_used_for_fit") is not False:
        raise ValueError("truth-contaminated inference")
    rows = []
    for rank, x in enumerate(d["exact_finalists"], 1):
        a00 = x["best_exact_by_group"]["20260921_00"]
        a16 = x["best_exact_by_group"]["20260921_16"]
        rows.append(
            {
                "exact_rank": rank,
                "east_km_from_iteration8": x["east_km_from_iteration8"],
                "north_km_from_iteration8": x["north_km_from_iteration8"],
                "latitude_deg": x["latitude_deg"],
                "longitude_deg": x["longitude_deg"],
                "balanced_proposal_objective": x["balanced_proposal_objective"],
                "balanced_exact_capped_loss": x["balanced_exact_capped_loss"],
                "group_00_tau_s": a00["tau_s"],
                "group_00_exact_loss": a00["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "group_16_tau_s": a16["tau_s"],
                "group_16_exact_loss": a16["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
            }
        )
    a.output_dir.mkdir(parents=True, exist_ok=True)
    with (a.output_dir / "iteration9-inference-finalists.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    fig, ax = plt.subplots(figsize=(5, 4), constrained_layout=True)
    s = ax.scatter(
        [r["east_km_from_iteration8"] for r in rows],
        [r["north_km_from_iteration8"] for r in rows],
        c=[r["balanced_exact_capped_loss"] for r in rows],
        s=75,
        cmap="viridis",
    )
    ax.scatter(
        rows[0]["east_km_from_iteration8"],
        rows[0]["north_km_from_iteration8"],
        marker="*",
        s=210,
        c="crimson",
    )
    ax.set(xlabel="east from iteration 8 (km)", ylabel="north from iteration 8 (km)")
    fig.colorbar(s, ax=ax, label="balanced exact capped loss")
    fig.savefig(a.output_dir / "iteration9-inference-finalists.png", dpi=160)


if __name__ == "__main__":
    main()
