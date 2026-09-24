#!/usr/bin/env python3
"""External post-seal comparison of iteration-7 likelihood rankings."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
I6 = HERE / "iteration6-postseal/iteration6-postseal.json"
REF = (37.84903264307456, -122.4856541910174)


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    la, lo, lb, loo = map(math.radians, (*a, *b))
    x = math.sin((lb - la) / 2) ** 2 + math.cos(la) * math.cos(lb) * math.sin((loo - lo) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(x))


def contains_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(
            {"reference", "reference_coordinate", "reference_error_km", "truth"} & value.keys()
        ) or any(contains_reference(v) for v in value.values())
    return any(contains_reference(v) for v in value) if isinstance(value, list) else False


def evaluate(inference: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    if inference.get("reference_used_for_fit") is not False or contains_reference(inference):
        raise ValueError("reference in inference")
    prior = {row["group_id"]: row["iteration6_error_km"] for row in baseline["rows"]}
    rows = []
    for result in inference["results"]:
        gaussian, robust = result["independent_gaussian_winner"], result["ar1_student_t_winner"]
        rows.append(
            {
                "group_id": result["group_id"],
                "iteration6_exact_error_km": prior[result["group_id"]],
                "gaussian_error_km": distance(
                    (gaussian["latitude_deg"], gaussian["longitude_deg"]), REF
                ),
                "ar1_student_t_error_km": distance(
                    (robust["latitude_deg"], robust["longitude_deg"]), REF
                ),
                "gaussian_tau_s": gaussian["tau_s"],
                "ar1_student_t_tau_s": robust["tau_s"],
                "same_gaussian_robust_winner": (
                    gaussian["latitude_deg"],
                    gaussian["longitude_deg"],
                    gaussian["tau_s"],
                )
                == (robust["latitude_deg"], robust["longitude_deg"], robust["tau_s"]),
            }
        )
    return sorted(rows, key=lambda row: row["group_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = evaluate(json.loads(args.inference.read_text()), json.loads(I6.read_text()))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration7-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration7-postseal/v1",
                "reference_role": "post-seal only",
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration7-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    x = np.arange(len(rows))
    width = 0.24
    ax.bar(
        x - width, [r["iteration6_exact_error_km"] for r in rows], width, label="iteration 6 exact"
    )
    ax.bar(x, [r["gaussian_error_km"] for r in rows], width, label="Gaussian")
    ax.bar(x + width, [r["ar1_student_t_error_km"] for r in rows], width, label="AR(1)+t")
    ax.set_xticks(x, [r["group_id"][-2:] for r in rows])
    ax.set_ylabel("post-seal error (km)")
    ax.legend()
    fig.savefig(args.output_dir / "iteration7-postseal.png", dpi=160)
    print(json.dumps({"rows": len(rows)}))


if __name__ == "__main__":
    main()
