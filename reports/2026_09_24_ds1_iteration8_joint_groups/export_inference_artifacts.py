#!/usr/bin/env python3
"""Export reference-free CSV and PNG summaries from sealed iteration-8 inference."""

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
    source = json.loads(args.inference.read_text())
    if source.get("reference_used_for_fit") is not False:
        raise ValueError("only reference-free inference may be exported")
    rows = []
    for rank, finalist in enumerate(source["exact_finalists"], start=1):
        first, second = (
            finalist["best_exact_by_group"][group] for group in ("20260921_00", "20260921_16")
        )
        rows.append(
            {
                "exact_rank": rank,
                "latitude_deg": finalist["latitude_deg"],
                "longitude_deg": finalist["longitude_deg"],
                "balanced_proposal_objective": finalist["balanced_proposal_objective"],
                "balanced_exact_capped_loss": finalist["balanced_exact_capped_loss"],
                "group_00_tau_s": first["tau_s"],
                "group_00_exact_capped_loss": first["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "group_16_tau_s": second["tau_s"],
                "group_16_exact_capped_loss": second["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "iteration8-inference-finalists.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, axis = plt.subplots(figsize=(6, 4), constrained_layout=True)
    scatter = axis.scatter(
        [row["longitude_deg"] for row in rows],
        [row["latitude_deg"] for row in rows],
        c=[row["balanced_exact_capped_loss"] for row in rows],
        s=80,
        cmap="viridis",
    )
    axis.scatter(
        [rows[0]["longitude_deg"]],
        [rows[0]["latitude_deg"]],
        marker="*",
        s=220,
        color="crimson",
        label="sealed joint winner",
    )
    axis.set_xlabel("longitude (deg)")
    axis.set_ylabel("latitude (deg)")
    axis.legend(loc="best")
    fig.colorbar(scatter, ax=axis, label="balanced exact capped loss")
    fig.savefig(args.output_dir / "iteration8-inference-finalists.png", dpi=160)
    print(json.dumps({"finalists": len(rows), "output_dir": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
