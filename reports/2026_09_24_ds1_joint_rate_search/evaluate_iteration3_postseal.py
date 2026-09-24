#!/usr/bin/env python3
"""Post-seal-only comparison of iteration-3 joint rate search with iteration 2."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER2_CSV = (
    ROOT
    / "reports/2026_09_24_ds1_iteration2/post-seal-evaluation/iteration2-post-seal-evaluation.csv"
)
REFERENCE = (37.84903264307456, -122.4856541910174)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*left, *right))
    haversine = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


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


def load_iteration2() -> dict[str, float]:
    output = {}
    with ITER2_CSV.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if (
                row["status"] != "completed"
                or row["method"] != "global_time"
                or row["scan_count"] != "6"
            ):
                continue
            value = row["reference_error_km"]
            if not value:
                continue
            output[row["case_id"] + "--" + row["prior_name"]] = float(value)
    return output


def evaluate(results: dict[str, Any]) -> list[dict[str, Any]]:
    if results.get("complete") is not True or results.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-3 result does not attest complete reference-free inference")
    if has_reference_key(results):
        raise ValueError("reference data appeared in inference artifact")
    iteration2 = load_iteration2()
    rows = []
    for item in results["results"]:
        if item.get("complete") is not True or item.get("reference_used_for_fit") is not False:
            raise ValueError("invalid iteration-3 seed result")
        gate = item["winner"]["exact_comparison"]["exact_sgp4_gate"]
        if not gate["passed"]:
            raise ValueError("exact SGP4 finalist gate failed")
        winner = item["winner"]
        case_seed = item["task_id"].split("--train-", 1)[1]
        # task id is iteration3--train-{group}--prefix-6--{seed}; this keeps
        # the external comparator keyed to iteration2's case/prior fields.
        group, _prefix_six, seed = case_seed.split("--")
        comparison_key = f"train-{group}--prefix-6--{seed}"
        if comparison_key not in iteration2:
            raise ValueError(f"missing iteration-2 comparison: {comparison_key}")
        error = haversine_km((winner["latitude_deg"], winner["longitude_deg"]), REFERENCE)
        rows.append(
            {
                "group_id": group,
                "prior_name": seed,
                "iteration2_global_time_error_km": iteration2[comparison_key],
                "iteration3_joint_rate_error_km": error,
                "error_delta_km": error - iteration2[comparison_key],
                "joint_selection_objective": winner["selection_objective"],
                "exact_capped_loss": winner["exact_comparison"][
                    "exact_full_observation_capped_loss"
                ],
                "surrogate_exact_loss_error": winner["exact_comparison"][
                    "absolute_capped_loss_error"
                ],
                "screened_point_count": item["screened_point_count"],
                "screen_elapsed_s": item["screen_elapsed_s"],
                "exact_elapsed_s": winner["exact_comparison"]["exact_elapsed_s"],
                "exact_gate_maximum_absolute_hz": gate["maximum_absolute_hz"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "tau_s": winner["tau_s"],
            }
        )
    return sorted(rows, key=lambda row: (row["group_id"], row["prior_name"]))


def render(rows: list[dict[str, Any]], output: Path) -> None:
    labels = [f"{row['group_id'][-2:]} {row['prior_name']}" for row in rows]
    x = list(range(len(rows)))
    fig, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    axis.bar(
        [value - 0.18 for value in x],
        [row["iteration2_global_time_error_km"] for row in rows],
        width=0.36,
        label="iteration 2 global time",
        color="#6b7280",
    )
    axis.bar(
        [value + 0.18 for value in x],
        [row["iteration3_joint_rate_error_km"] for row in rows],
        width=0.36,
        label="iteration 3 joint rate",
        color="#0f766e",
    )
    axis.set_xticks(x, labels)
    axis.set_ylabel("post-seal error (km)")
    axis.set_title("DS1 prefix-6 post-seal comparison")
    axis.legend()
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    rows = evaluate(results)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "iteration3-postseal.json"
    csv_path = args.output_dir / "iteration3-postseal.csv"
    plot_path = args.output_dir / "iteration3-postseal.png"
    json_path.write_text(
        json.dumps(
            {
                "schema": "ds1-iteration3-postseal-evaluation/v1",
                "reference_role": "introduced only after iteration-3 inference completion",
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    render(rows, plot_path)
    print(json.dumps({"rows": len(rows), "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
