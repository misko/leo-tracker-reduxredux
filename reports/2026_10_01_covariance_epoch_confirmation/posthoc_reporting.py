"""Failure-inclusive matched reporting from evaluator outputs only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ("C1", "M2", "M4", "M24")
EXPECTED_CELLS = 128


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def parse_bool(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    raise ValueError(f"invalid boolean {value!r}")


def optional_float(value: str) -> float | None:
    if value == "":
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite evaluator value")
    return result


def load_inputs() -> tuple[dict, list[dict], dict]:
    paths = [HERE / name for name in ("final-integrity-audit.json", "summary.json", "per-scan.csv")]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("posthoc inputs absent: " + ", ".join(missing))
    audit = json.loads(paths[0].read_text())
    summary = json.loads(paths[1].read_text())
    if audit.get("passed") is not True or audit.get("planned_cells") != EXPECTED_CELLS:
        raise ValueError("complete integrity audit has not passed")
    if summary.get("final_integrity_audit_sha256") != digest(paths[0]):
        raise ValueError("summary is not bound to the passed audit")
    with paths[2].open(newline="") as stream:
        raw_rows = list(csv.DictReader(stream))
    rows = [
        {
            "unit": row["unit"],
            "dataset": row["dataset"],
            "arm": row["arm"],
            "status": row["status"],
            "qualified": parse_bool(row["qualified"]),
            "error_m": optional_float(row["error_m"]),
            "east_km": optional_float(row["east_km"]),
            "north_km": optional_float(row["north_km"]),
        }
        for row in raw_rows
    ]
    keys = {(row["unit"], row["arm"]) for row in rows}
    if len(rows) != EXPECTED_CELLS or len(keys) != EXPECTED_CELLS:
        raise ValueError("posthoc input is not 128 unique cells")
    if {row["arm"] for row in rows} != set(ARMS) or set(summary["overall"]) != set(ARMS):
        raise ValueError("posthoc arm set differs")
    return summary, rows, audit


def paired_report(rows: list[dict], comparator: str) -> dict:
    by_key = {(row["unit"], row["arm"]): row for row in rows}
    result = {}
    for arm in ARMS:
        result[arm] = {}
        for dataset in ("DS9", "DS10", "DS11"):
            arm_rows = [row for row in rows if row["arm"] == arm and row["dataset"] == dataset]
            deltas = []
            for row in arm_rows:
                baseline = by_key[(row["unit"], comparator)]
                if row["qualified"] and baseline["qualified"] and row["error_m"] is not None and baseline["error_m"] is not None:
                    deltas.append(row["error_m"] - baseline["error_m"])
            ordered = sorted(deltas)
            median = None
            if ordered:
                middle = len(ordered) // 2
                median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
            result[arm][dataset] = {
                "planned_denominator": len(arm_rows),
                "common_qualified": len(deltas),
                "wins": sum(delta < 0 for delta in deltas),
                "ties": sum(delta == 0 for delta in deltas),
                "losses": sum(delta > 0 for delta in deltas),
                "median_delta_m": median,
                "deltas_m": deltas,
            }
        arm_rows = [row for row in rows if row["arm"] == arm]
        deltas = []
        for row in arm_rows:
            baseline = by_key[(row["unit"], comparator)]
            if row["qualified"] and baseline["qualified"] and row["error_m"] is not None and baseline["error_m"] is not None:
                deltas.append(row["error_m"] - baseline["error_m"])
        result[arm]["overall"] = {
            "planned_denominator": len(arm_rows),
            "common_qualified": len(deltas),
            "wins": sum(delta < 0 for delta in deltas),
            "ties": sum(delta == 0 for delta in deltas),
            "losses": sum(delta > 0 for delta in deltas),
            "median_delta_m": median_value(deltas),
            "deltas_m": deltas,
        }
    return result


def median_value(values: list[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def main() -> None:
    summary, rows, audit = load_inputs()
    result = {
        "schema": "covariance-epoch-posthoc-report/v1",
        "inputs": {
            name: digest(HERE / name)
            for name in ("summary.json", "per-scan.csv", "final-integrity-audit.json")
        },
        "execution_freeze_sha256": audit["execution_freeze_sha256"],
        "cdf_denominator": "all 32 planned scans per arm; failures retain denominator mass",
        "paired_comparison_scope": "only cells where both compared arms qualified on the same scan",
        "paired_common_qualified_vs_C1": paired_report(rows, "C1"),
        "M24_matched_ablations": {
            comparator: paired_report(rows, comparator)["M24"]
            for comparator in ("C1", "M2", "M4")
        },
        "predictive_claim": "No held predictive claim: the recorded diagnostic refits nuisance parameters and associations.",
        "limitations": [
            "reference is operator supplied, unsurveyed, and rounded to whole arcseconds",
            "qualified-only summaries exclude unqualified diagnostic points but keep the planned denominator for availability",
            "this confirmation reuses the retrospective same-site DS9/DS10/DS11 panel",
        ],
        "summary_schema": summary["schema"],
    }
    output = HERE / "posthoc-paired.json"
    if output.exists():
        raise FileExistsError("refusing to overwrite posthoc output")
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
