#!/usr/bin/env python3
"""Post-seal-only evaluation for iteration-4 seed-union exact results."""

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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER3_POSTSEAL = HERE / "iteration3-postseal/iteration3-postseal.json"
REFERENCE = (37.84903264307456, -122.4856541910174)


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*left, *right))
    value = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def has_reference_key(value: Any) -> bool:
    forbidden = {
        "reference",
        "reference_coordinate",
        "reference_error_km",
        "truth",
        "truth_coordinate",
    }
    if isinstance(value, dict):
        return bool(forbidden & value.keys()) or any(
            has_reference_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(has_reference_key(item) for item in value)
    return False


def evaluate(
    inference: dict[str, Any], iteration3_postseal: dict[str, Any]
) -> list[dict[str, Any]]:
    if (
        inference.get("complete") is not True
        or inference.get("reference_used_for_fit") is not False
        or has_reference_key(inference)
    ):
        raise ValueError("iteration-4 inference is not a complete reference-free artifact")
    previous: dict[str, list[float]] = {}
    for row in iteration3_postseal["rows"]:
        previous.setdefault(row["group_id"], []).append(
            float(row["iteration3_joint_rate_error_km"])
        )
    rows = []
    for result in inference["results"]:
        winner = result["winner"]
        gate = winner["exact_comparison"]["exact_sgp4_gate"]
        if not gate["passed"]:
            raise ValueError("unqualified exact candidate")
        group = result["group_id"]
        if group not in previous or len(previous[group]) != 2:
            raise ValueError("iteration-3 paired post-seal rows absent")
        error = haversine_km((winner["latitude_deg"], winner["longitude_deg"]), REFERENCE)
        rows.append(
            {
                "group_id": group,
                "iteration4_exact_selected_error_km": error,
                "iteration3_seed_min_error_km": min(previous[group]),
                "iteration3_seed_max_error_km": max(previous[group]),
                "iteration4_minus_iteration3_seed_min_km": error - min(previous[group]),
                "exact_capped_loss": winner["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "surrogate_exact_loss_error": winner["exact_comparison"][
                    "absolute_capped_loss_error"
                ],
                "candidate_count": result["candidate_count"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "tau_s": winner["tau_s"],
            }
        )
    return sorted(rows, key=lambda row: row["group_id"])


def render(rows: list[dict[str, Any]], output: Path) -> None:
    labels = [row["group_id"][-2:] for row in rows]
    x = list(range(len(rows)))
    fig, axis = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    axis.bar(
        [v - 0.24 for v in x],
        [row["iteration3_seed_min_error_km"] for row in rows],
        width=0.24,
        label="iteration 3 seed minimum",
        color="#6b7280",
    )
    axis.bar(
        x,
        [row["iteration3_seed_max_error_km"] for row in rows],
        width=0.24,
        label="iteration 3 seed maximum",
        color="#a1a1aa",
    )
    axis.bar(
        [v + 0.24 for v in x],
        [row["iteration4_exact_selected_error_km"] for row in rows],
        width=0.24,
        label="iteration 4 exact selection",
        color="#0f766e",
    )
    axis.set_xticks(x, labels)
    axis.set_ylabel("post-seal error (km)")
    axis.set_title("Prefix-6 seed-union exact selection")
    axis.legend()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    iteration3 = json.loads(ITER3_POSTSEAL.read_text())
    rows = evaluate(inference, iteration3)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "iteration4-postseal.json").write_text(
        json.dumps(
            {
                "schema": "ds1-iteration4-postseal-evaluation/v1",
                "reference_role": "introduced after complete iteration-4 inference",
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with (args.output_dir / "iteration4-postseal.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render(rows, args.output_dir / "iteration4-postseal.png")
    print(json.dumps({"rows": len(rows), "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
