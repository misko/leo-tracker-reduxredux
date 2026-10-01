"""Seal-first evaluation for localization approaches; truth is loaded last."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"
EVALUATOR_BINDINGS = ROOT / "plans/localization-approaches-2026-10-01/evaluator-bindings.json"
REFERENCE_HELPER = ROOT / "reports/2026_10_01_fixed_height_greedy/evaluate.py"
REFERENCE_HELPER_SHA256 = "sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def audit_module():
    return load_module("localization_fit_audit", HERE / "audit_receipts.py")


def discover_arm_folders(run_root: Path) -> dict[str, Path]:
    launches = sorted(run_root.rglob("DS*.launch.json"))
    arms = {str(json.loads(path.read_text()).get("arm")) for path in launches}
    if not arms:
        raise ValueError(f"no arm launch receipts found beneath {run_root}")
    return {arm: run_root for arm in sorted(arms)}


def _attempts(
    folder: Path, audit, plan: dict[str, Any], expected_arm: str
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for launch_path in sorted(folder.rglob("DS*.launch.json")):
        launch = json.loads(launch_path.read_text())
        if launch.get("arm") != expected_arm:
            continue
        unit = launch.get("unit_id")
        if unit in result:
            raise ValueError(f"duplicate attempt for {unit} in {folder}")
        prediction_path = launch_path.with_name(launch_path.name.replace(".launch.json", ".json"))
        receipt_audit = audit.audit_receipt(prediction_path, plan)
        launch_audit = audit.audit_launch(launch_path, prediction_path)
        receipt = None
        if prediction_path.is_file():
            with suppress(json.JSONDecodeError):
                receipt = json.loads(prediction_path.read_text())
        result[unit] = {
            "receipt": receipt,
            "receipt_path": prediction_path,
            "launch": launch,
            "launch_path": launch_path,
            "receipt_audit": receipt_audit,
            "launch_audit": launch_audit,
        }
    return result


def _merge_continuation(
    primary: dict[str, dict[str, Any]],
    continuation: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    extra = set(continuation) - set(primary)
    if extra:
        raise ValueError(f"continuations without primaries: {sorted(extra)}")
    merged = dict(primary)
    for unit, child in continuation.items():
        parent = primary[unit]
        child_receipt = child.get("receipt") or {}
        parent_receipt = parent.get("receipt") or {}
        expected_parent = child_receipt.get("parent", {})
        if Path(expected_parent.get("path", "")) != parent["receipt_path"].resolve():
            raise ValueError(f"continuation parent path mismatch: {unit}")
        if expected_parent.get("sha256") != digest(parent["receipt_path"]):
            raise ValueError(f"continuation parent digest mismatch: {unit}")
        if parent_receipt.get("status") != "unresolved":
            raise ValueError(f"continuation of non-unresolved primary: {unit}")
        child = dict(child)
        child["primary"] = parent
        merged[unit] = child
    return merged


def _verify_evaluator_authority() -> tuple[Any, dict[str, dict[str, Any]]]:
    """Called only after fit-side audits have completed."""
    bindings = json.loads(EVALUATOR_BINDINGS.read_text())
    baseline_documents = {}
    for binding in bindings["controls"]:
        path = ROOT / binding["path"]
        if digest(path) != binding["sha256"]:
            raise ValueError(f"evaluator control hash mismatch: {path}")
        baseline_documents[binding["path"]] = json.loads(path.read_text())
    if digest(REFERENCE_HELPER) != REFERENCE_HELPER_SHA256:
        raise ValueError("reference-coordinate helper hash mismatch")
    helper = load_module("localization_reference_helper", REFERENCE_HELPER)
    return helper, baseline_documents


def _acceptance(attempt: dict[str, Any], arm: str) -> tuple[bool, list[str], dict[str, Any]]:
    failures = []
    if not attempt["receipt_audit"]["passed"]:
        failures.append("receipt_audit_failed")
    if not attempt["launch_audit"]["passed"]:
        failures.append("launch_audit_failed")
    primary = attempt.get("primary")
    if primary and not primary["receipt_audit"]["passed"]:
        failures.append("primary_receipt_audit_failed")
    if primary and not primary["launch_audit"]["passed"]:
        failures.append("primary_launch_audit_failed")
    receipt = attempt.get("receipt") or {}
    launch = attempt.get("launch") or {}
    best = receipt.get("best") or {}
    if receipt.get("status") != "converged_local_mode" or not best.get("converged"):
        failures.append("native_winner_not_converged")
    if launch.get("status") != "complete" or launch.get("returncode") != 0:
        failures.append("launcher_not_successful")
    if not launch.get("within_budget", launch.get("wall_seconds", math.inf) <= 90):
        failures.append("primary_or_continuation_budget_failed")
    if launch.get("cumulative_seconds", math.inf) > 180:
        failures.append("cumulative_budget_failed")
    planned = receipt.get("planned_factors")
    associations = best.get("associations", [])
    if not isinstance(planned, int) or len(associations) != planned:
        failures.append("factor_result_incomplete")
    if arm == "B1":
        soft = best.get("soft_diagnostics", {})
        if not soft.get("responsibilities_at_mean"):
            failures.append("converged_responsibilities_missing")
    return not failures, failures, best


def _percentile(values: list[float], q: float) -> float | None:
    return None if not values else float(np.percentile(np.asarray(values), q))


def _baseline_rows(documents: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    primary = next(
        document for path, document in documents.items() if path.endswith("primary-evaluation.json")
    )
    return {row["unit_id"]: row for row in primary["rows"]}


def evaluate(
    run_root: Path,
    continuation_root: Path | None = None,
) -> dict[str, Any]:
    plan = json.loads(PLAN.read_text())
    units = [row["unit_id"] for row in plan["ordered_units"]]
    audit = audit_module()
    arm_folders = discover_arm_folders(run_root)
    continuation_folders = (
        discover_arm_folders(continuation_root) if continuation_root is not None else {}
    )
    attempts_by_arm = {}
    for arm, folder in arm_folders.items():
        attempts = _attempts(folder, audit, plan, arm)
        if arm in continuation_folders:
            attempts = _merge_continuation(
                attempts, _attempts(continuation_folders[arm], audit, plan, arm)
            )
        attempts_by_arm[arm] = attempts

    # Fit-side seals and audits are complete before this call reveals reference information.
    reference, controls = _verify_evaluator_authority()
    baseline = _baseline_rows(controls)
    rows = []
    for arm, attempts in sorted(attempts_by_arm.items()):
        for unit in units:
            attempt = attempts.get(unit)
            if attempt is None:
                rows.append(
                    {
                        "arm": arm,
                        "unit_id": unit,
                        "dataset": unit.split("-")[0],
                        "attempted": False,
                        "status": "not_run",
                        "accepted": False,
                        "acceptance_failures": ["not_run"],
                        "error_m": None,
                        "runtime_s": None,
                    }
                )
                continue
            accepted, acceptance_failures, best = _acceptance(attempt, arm)
            mean = best.get("mean")
            primary = attempt.get("primary")
            audit_valid = bool(
                attempt["receipt_audit"]["passed"]
                and attempt["launch_audit"]["passed"]
                and (not primary or primary["receipt_audit"]["passed"])
                and (not primary or primary["launch_audit"]["passed"])
            )
            point = reference.latlon_from_enu(*mean[:2]) if mean and audit_valid else None
            error = reference.distance_m(point, reference.REFERENCE) if point else None
            receipt = attempt.get("receipt") or {}
            launch = attempt["launch"]
            base = baseline.get(unit, {})
            rows.append(
                {
                    "arm": arm,
                    "unit_id": unit,
                    "dataset": unit.split("-")[0],
                    "attempted": True,
                    "status": receipt.get("status", launch.get("status", "unknown")),
                    "accepted": accepted,
                    "acceptance_failures": acceptance_failures,
                    "native_converged": bool(best.get("converged")),
                    "error_m": error if accepted else None,
                    "failed_point_error_m_diagnostic": error
                    if error is not None and not accepted
                    else None,
                    "east_km": None if not mean else mean[0],
                    "north_km": None if not mean else mean[1],
                    "runtime_s": launch.get("cumulative_seconds", launch.get("wall_seconds")),
                    "planned_factors": receipt.get("planned_factors"),
                    "reported_factors": len(best.get("associations", [])),
                    "baseline_error_m": base.get("error_m"),
                    "paired_error_delta_m": (
                        error - base["error_m"]
                        if accepted and base.get("error_m") is not None
                        else None
                    ),
                    "receipt_path": str(attempt["receipt_path"]),
                    "receipt_sha256": (
                        digest(attempt["receipt_path"])
                        if attempt["receipt_path"].is_file()
                        else None
                    ),
                    "launch_path": str(attempt["launch_path"]),
                    "receipt_audit_passed": attempt["receipt_audit"]["passed"],
                    "launch_audit_passed": attempt["launch_audit"]["passed"],
                }
            )

    summaries = {}
    for arm in sorted(attempts_by_arm):
        arm_rows = [row for row in rows if row["arm"] == arm]
        errors = [row["error_m"] for row in arm_rows if row["error_m"] is not None]
        runtimes = [row["runtime_s"] for row in arm_rows if row["runtime_s"] is not None]
        deltas = [
            row["paired_error_delta_m"]
            for row in arm_rows
            if row.get("paired_error_delta_m") is not None
        ]
        sorted_errors = sorted(errors)
        summaries[arm] = {
            "planned_count": 64,
            "attempted_count": sum(row["attempted"] for row in arm_rows),
            "accepted_count": len(errors),
            "status_counts": dict(sorted(Counter(row["status"] for row in arm_rows).items())),
            "conditional_error_median_m": _percentile(errors, 50),
            "conditional_error_p90_m": _percentile(errors, 90),
            "attempted_runtime_median_s": _percentile(runtimes, 50),
            "attempted_runtime_p90_s": _percentile(runtimes, 90),
            "paired_baseline_count": len(deltas),
            "paired_error_delta_median_m": _percentile(deltas, 50),
            "paired_error_improved_count": sum(delta < 0 for delta in deltas),
            "failure_inclusive_ecdf_denominator": 64,
            "failure_inclusive_ecdf": [
                {"error_m": value, "fraction_of_64": (index + 1) / 64}
                for index, value in enumerate(sorted_errors)
            ],
        }
    return {
        "schema": "localization-approaches-evaluation/v1",
        "reference_read_after_fit_audit": True,
        "planned_units_per_arm": 64,
        "arms": sorted(attempts_by_arm),
        "summaries": summaries,
        "rows": rows,
    }


def write_outputs(document: dict[str, Any], prefix: Path, plot: bool) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")
    fields = sorted({key for row in document["rows"] for key in row})
    with prefix.with_suffix(".csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in document["rows"]:
            writer.writerow(
                {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )
    if not plot:
        return
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(7, 4.5))
    for arm, summary in document["summaries"].items():
        points = summary["failure_inclusive_ecdf"]
        if points:
            axis.step(
                [point["error_m"] for point in points],
                [point["fraction_of_64"] for point in points],
                where="post",
                label=f"{arm} ({summary['accepted_count']}/64 accepted)",
            )
    axis.set(xlabel="Accepted horizontal error (m)", ylabel="Fraction of planned 64 scans")
    axis.set_ylim(0, 1)
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    figure.savefig(prefix.with_name(prefix.name + "-error-ecdf.png"), dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7, 4.5))
    arms = document["arms"]
    values = [
        [row["runtime_s"] for row in document["rows"] if row["arm"] == arm and row["runtime_s"]]
        for arm in arms
    ]
    if any(values):
        axis.boxplot(values, tick_labels=arms, showfliers=True)
    axis.set(xlabel="Approach", ylabel="Attempt wall time (s)")
    axis.axhline(90, color="tab:red", linestyle="--", linewidth=1)
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(prefix.with_name(prefix.name + "-timing.png"), dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--continuation-root", type=Path)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    document = evaluate(args.run_root, args.continuation_root)
    write_outputs(document, args.output_prefix, args.plot)
    print(json.dumps({"arms": document["arms"], "output": str(args.output_prefix)}))


if __name__ == "__main__":
    main()
