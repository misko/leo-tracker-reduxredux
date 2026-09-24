#!/usr/bin/env python3
"""Post-seal-only evaluation for the reference-free iteration-6B artifact."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REF = (37.84903264307456, -122.4856541910174)


def hav(a, b):
    x1, y1, x2, y2 = map(math.radians, (*a, *b))
    z = math.sin((x2 - x1) / 2) ** 2 + math.cos(x1) * math.cos(x2) * math.sin((y2 - y1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(z))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    d = json.loads(a.results.read_text())
    if d.get("complete") is not True or d.get("reference_used_for_fit") is not False:
        raise ValueError("invalid inference contract")
    rows = []
    for g in d["groups"]:
        w = g["winner"]
        rows.append(
            {
                "group_id": g["group_id"],
                "provisional_exact_capped_loss": w["exact_capped_loss"],
                "input_rate_only_exact_capped_loss": w["input_rate_only_exact_capped_loss"],
                "provisional_loss_delta": w["exact_capped_loss"]
                - w["input_rate_only_exact_capped_loss"],
                "converged": w["converged"],
                "solver_message": w["solver_message"],
                "scale_reaches_guard": w["scale_reaches_guard"],
                "reference_error_km_descriptive_only": hav(
                    (w["latitude_deg"], w["longitude_deg"]), REF
                ),
                "latitude_deg": w["latitude_deg"],
                "longitude_deg": w["longitude_deg"],
                "tau_s": w["tau_s"],
            }
        )
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / "iteration6b-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration6b-postseal/v1",
                "reference_role": "introduced only after inference completion",
                "inference_portability_accepted": False,
                "status": "rejected_nonconverged_descriptive_only",
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (a.output_dir / "iteration6b-postseal.csv").open("w", newline="") as f:
        o = csv.DictWriter(f, fieldnames=list(rows[0]))
        o.writeheader()
        o.writerows(rows)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(
        [r["group_id"][-2:] for r in rows],
        [r["reference_error_km_descriptive_only"] for r in rows],
        color="#9ca3af",
    )
    ax.set_ylabel("post-seal error (km; rejected run)")
    ax.set_title("Iteration 6B provisional coordinates")
    fig.savefig(a.output_dir / "iteration6b-postseal.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
