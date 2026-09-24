#!/usr/bin/env python3
"""External post-seal evaluator for iteration-6 exact-rank ablation."""

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

HERE = Path(__file__).resolve().parent
I5 = HERE / "iteration5-postseal/iteration5-postseal.json"
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
    if isinstance(value, list):
        return any(contains_reference(v) for v in value)
    return False


def evaluate(inference: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    if inference.get("reference_used_for_fit") is not False or contains_reference(inference):
        raise ValueError("reference present in inference")
    prior = {row["group_id"]: row["iteration5_error_km"] for row in previous["rows"]}
    rows = []
    for result in inference["results"]:
        winner = result["winner"]
        gate = winner["exact_comparison"]["exact_sgp4_gate"]
        if not gate["passed"]:
            raise ValueError("failed exact gate")
        error = distance((winner["latitude_deg"], winner["longitude_deg"]), REF)
        rows.append(
            {
                "group_id": result["group_id"],
                "iteration5_error_km": prior[result["group_id"]],
                "iteration6_error_km": error,
                "delta_km": error - prior[result["group_id"]],
                "exact_capped_loss": winner["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "tau_s": winner["tau_s"],
                "exact_candidate_count": result["exact_candidate_count"],
            }
        )
    return sorted(rows, key=lambda row: row["group_id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    rows = evaluate(json.loads(args.inference.read_text()), json.loads(I5.read_text()))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration6-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration6-postseal/v1",
                "reference_role": "post-seal only",
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    with (args.output_dir / "iteration6-postseal.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(6, 4), constrained_layout=True)
    x = range(len(rows))
    ax.bar(
        [value - 0.18 for value in x],
        [row["iteration5_error_km"] for row in rows],
        0.36,
        label="iteration 5",
    )
    ax.bar(
        [value + 0.18 for value in x],
        [row["iteration6_error_km"] for row in rows],
        0.36,
        label="iteration 6",
    )
    ax.set_xticks(list(x), [row["group_id"][-2:] for row in rows])
    ax.set_ylabel("post-seal error (km)")
    ax.legend()
    fig.savefig(args.output_dir / "iteration6-postseal.png", dpi=160)
    print(json.dumps({"rows": len(rows)}))


if __name__ == "__main__":
    main()
