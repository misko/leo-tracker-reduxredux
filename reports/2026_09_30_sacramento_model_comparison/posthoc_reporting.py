"""Create failure-inclusive posthoc summaries from sealed evaluator outputs only.

This module does not read model inputs, predictions, reference coordinates, or
radio evidence. It may run only after the integrity audit and evaluator finish.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
BOUNDARY_KM = 250.0
BOUNDARY_TOLERANCE_KM = 0.001


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"invalid CSV boolean {value!r}")


def optional_float(value: str) -> float | None:
    if value.strip() == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite evaluator value")
    return result


def load_inputs() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    audit_path = HERE / "final-integrity-audit.json"
    summary_path = HERE / "summary.json"
    scan_path = HERE / "per-scan.csv"
    missing = [str(path) for path in (audit_path, summary_path, scan_path) if not path.exists()]
    if missing:
        raise FileNotFoundError("posthoc inputs do not exist: " + ", ".join(missing))
    audit = json.loads(audit_path.read_text())
    if audit.get("passed") is not True or audit.get("planned_cells") != 480:
        raise ValueError("final integrity audit has not passed the complete panel")
    summary = json.loads(summary_path.read_text())
    with scan_path.open(newline="") as stream:
        raw_rows = list(csv.DictReader(stream))
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        rows.append(
            {
                "unit": raw["unit"],
                "dataset": raw["dataset"],
                "arm": raw["arm"],
                "status": raw["status"],
                "qualified": parse_bool(raw["qualified"]),
                "error_m": optional_float(raw["error_m"]),
                "east_km": optional_float(raw["east_km"]),
                "north_km": optional_float(raw["north_km"]),
            }
        )
    keys = [(row["unit"], row["arm"]) for row in rows]
    if len(rows) != 480 or len(set(keys)) != 480:
        raise ValueError("per-scan matrix is not exactly 480 unique cells")
    expected_arms = set(summary["overall"])
    if {row["arm"] for row in rows} != expected_arms:
        raise ValueError("CSV and summary arm sets disagree")
    if "C1" not in expected_arms:
        raise ValueError("C1 baseline is absent")
    planned_units = {row["unit"] for row in rows if row["arm"] == "C1"}
    for arm in expected_arms:
        arm_rows = [row for row in rows if row["arm"] == arm]
        planned = len(arm_rows)
        if planned != summary["overall"][arm]["planned"]:
            raise ValueError(f"planned denominator disagrees for {arm}")
        if {row["unit"] for row in arm_rows} != planned_units:
            raise ValueError(f"planned scan membership disagrees for {arm}")
    return summary, rows, audit


def is_boundary_point(row: dict[str, Any]) -> bool:
    east, north = row["east_km"], row["north_km"]
    return (
        east is not None
        and north is not None
        and math.hypot(east, north) >= BOUNDARY_KM - BOUNDARY_TOLERANCE_KM
    )


def paired_report(rows: list[dict[str, Any]], arms: list[str]) -> dict[str, Any]:
    by_key = {(row["unit"], row["arm"]): row for row in rows}
    datasets = sorted({row["dataset"] for row in rows})
    result: dict[str, Any] = {}
    for arm in arms:
        result[arm] = {}
        for dataset in datasets:
            arm_rows = [r for r in rows if r["arm"] == arm and r["dataset"] == dataset]
            deltas = []
            for row in arm_rows:
                baseline = by_key[(row["unit"], "C1")]
                if (
                    row["qualified"]
                    and baseline["qualified"]
                    and row["error_m"] is not None
                    and baseline["error_m"] is not None
                ):
                    deltas.append(row["error_m"] - baseline["error_m"])
            ordered = sorted(deltas)
            median = None
            if ordered:
                middle = len(ordered) // 2
                median = (
                    ordered[middle]
                    if len(ordered) % 2
                    else (ordered[middle - 1] + ordered[middle]) / 2.0
                )
            result[arm][dataset] = {
                "planned_denominator": len(arm_rows),
                "common_qualified": len(deltas),
                "wins_vs_C1": sum(delta < 0 for delta in deltas),
                "ties_vs_C1": sum(delta == 0 for delta in deltas),
                "losses_vs_C1": sum(delta > 0 for delta in deltas),
                "median_delta_m": median,
                "deltas_m": deltas,
                "qualified_boundary_hits": sum(
                    row["qualified"] and is_boundary_point(row) for row in arm_rows
                ),
                "all_returned_point_boundary_hits": sum(is_boundary_point(row) for row in arm_rows),
            }
    return result


def plot_failure_inclusive_cdf(rows: list[dict[str, Any]], arms: list[str], output: Path) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(9.0, 5.5))
    qualified_errors = [
        row["error_m"]
        for row in rows
        if row["qualified"] and row["error_m"] is not None
    ]
    x_max = max(qualified_errors, default=1.0)
    for arm in arms:
        arm_rows = [row for row in rows if row["arm"] == arm]
        errors = sorted(
            row["error_m"]
            for row in arm_rows
            if row["qualified"] and row["error_m"] is not None
        )
        x = [0.0, *errors, x_max]
        y = [0.0, *[(index + 1) / len(arm_rows) for index in range(len(errors))]]
        y.append(y[-1])
        axis.step(x, y, where="post", label=f"{arm} ({len(errors)}/{len(arm_rows)})")
    axis.set_xlabel("Horizontal distance to unsurveyed reference (m)")
    axis.set_ylabel("Fraction of all planned scans")
    axis.set_ylim(0.0, 1.0)
    axis.grid(True, alpha=0.25)
    axis.legend(ncol=3, fontsize=8)
    figure.tight_layout()
    figure.savefig(output, format="svg")
    plt.close(figure)


def main() -> None:
    summary, rows, audit = load_inputs()
    arms = list(summary["overall"])
    result = {
        "schema": "sacramento-posthoc-report/v1",
        "inputs": {
            "summary.json": digest(HERE / "summary.json"),
            "per-scan.csv": digest(HERE / "per-scan.csv"),
            "final-integrity-audit.json": digest(HERE / "final-integrity-audit.json"),
        },
        "execution_freeze_sha256": audit["execution_freeze_sha256"],
        "cdf_denominator": "all planned scans per arm; failures and abstentions retain denominator mass and curves need not reach one",
        "boundary_definition": {
            "radius_km": BOUNDARY_KM,
            "tolerance_km": BOUNDARY_TOLERANCE_KM,
        },
        "paired_common_qualified_vs_C1": paired_report(rows, arms),
        "unavailable_diagnostics": [
            "common-observation predictive score",
            "association entropy",
            "leave-one-source-out displacement",
            "profiled information spectrum",
            "peak memory",
        ],
        "limitations": [
            "reference is operator supplied, unsurveyed, and rounded to whole arcseconds",
            "paired deltas include only scans where both the arm and C1 qualified",
            "unqualified diagnostic points are excluded from the primary CDF",
        ],
    }
    json_path = HERE / "posthoc-paired.json"
    svg_path = HERE / "failure-inclusive-cdf.svg"
    if json_path.exists() or svg_path.exists():
        raise FileExistsError("refusing to overwrite posthoc outputs")
    plot_failure_inclusive_cdf(rows, arms, svg_path)
    with json_path.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
