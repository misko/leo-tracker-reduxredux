"""Fit-side receipt audit which never opens evaluator/truth artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"
ALLOWED_STATUSES = {"converged_local_mode", "unresolved", "error", "timeout", "not_run"}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _check(condition: bool, code: str, detail: str, failures: list[dict[str, str]]) -> None:
    if not condition:
        failures.append({"code": code, "detail": detail})


def _finite_nonnegative(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def load_plan(path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    return json.loads(path.read_text())


def audit_authorities(plan: dict[str, Any], root: Path = ROOT) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for binding in plan.get("authority_bindings", []):
        path = root / binding["path"]
        _check(path.is_file(), "authority_missing", str(path), failures)
        if path.is_file():
            _check(digest(path) == binding["sha256"], "authority_hash", str(path), failures)
    return failures


def read_sealed(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    seal = path.with_suffix(".seal.json")
    _check(path.is_file(), "receipt_missing", str(path), failures)
    _check(seal.is_file(), "seal_missing", str(seal), failures)
    if failures:
        return None, failures
    try:
        seal_document = json.loads(seal.read_text())
        receipt = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        failures.append({"code": "invalid_json", "detail": f"{path}: {error}"})
        return None, failures
    _check(
        seal_document.get("prediction_sha256") == digest(path),
        "seal_hash",
        str(path),
        failures,
    )
    return receipt, failures


def audit_receipt(path: Path, plan: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    receipt, failures = read_sealed(path)
    warnings: list[dict[str, str]] = []
    result: dict[str, Any] = {
        "path": str(path),
        "failures": failures,
        "warnings": warnings,
    }
    if receipt is None:
        result["passed"] = False
        return result

    units = {row["unit_id"]: row["session_id"] for row in plan["ordered_units"]}
    unit = receipt.get("unit_id")
    _check(
        receipt.get("schema") == "localization-approach-attempt/v1", "schema", str(path), failures
    )
    _check(unit in units, "unit_not_planned", repr(unit), failures)
    if unit in units:
        _check(receipt.get("session_id") == units[unit], "session_binding", str(unit), failures)
    _check(
        receipt.get("status") in ALLOWED_STATUSES, "status", repr(receipt.get("status")), failures
    )
    supervisor_generated = bool(receipt.get("supervisor_generated"))
    if not supervisor_generated:
        _check(
            receipt.get("prior_manifest_sha256") == digest(DEFAULT_PLAN),
            "plan_hash",
            str(path),
            failures,
        )

    config = receipt.get("config", {})
    if not supervisor_generated:
        _check(config.get("degrees_of_freedom") == 4.0, "degrees_of_freedom", str(path), failures)
        _check(config.get("seed_limit") == 3, "seed_limit", str(path), failures)
        _check(config.get("max_iterations") == 24, "iteration_limit", str(path), failures)
        _check(config.get("primary_external_s") == 90, "primary_budget", str(path), failures)
        _check(
            config.get("continuation_external_s") == 90, "continuation_budget", str(path), failures
        )

    observation_groups = receipt.get("physical_observation_ids", [])
    observations = [value for group in observation_groups for value in group]
    _check(len(observations) == len(set(observations)), "observation_reuse", str(unit), failures)
    if not supervisor_generated:
        _check(
            receipt.get("planned_factors") == len(observation_groups),
            "factor_count",
            str(unit),
            failures,
        )

    candidates = receipt.get("candidate_ids", [])
    fits = receipt.get("fits", [])
    proposal_seeds = receipt.get("proposal", {}).get("seeds", [])[: config.get("seed_limit", 0)]
    if not supervisor_generated:
        _check(
            len(fits) == len(proposal_seeds),
            "seed_outcome_completeness",
            f"{unit}: {len(fits)} outcomes for {len(proposal_seeds)} seeds",
            failures,
        )
        _check(
            [fit.get("seed_index") for fit in fits] == list(range(len(proposal_seeds))),
            "seed_indices",
            str(unit),
            failures,
        )
    for index, fit in enumerate(fits):
        fit_status = (
            "not_run" if fit.get("reason") == "not_started" else fit.get("status", "complete")
        )
        _check(
            fit_status in {"complete", "not_run", "error"},
            "fit_status",
            f"{unit}:{index}",
            failures,
        )
        if fit_status != "complete":
            continue
        mean = fit.get("mean", [])
        epochs = fit.get("satellite_epoch_s", [])
        values = mean + epochs + fit.get("objectives", []) + fit.get("accepted_step_norms", [])
        _check(len(mean) == 5, "mean_dimension", f"{unit}:{index}", failures)
        _check(len(epochs) == len(candidates), "epoch_dimension", f"{unit}:{index}", failures)
        _check(
            all(isinstance(v, (int, float)) and math.isfinite(v) for v in values),
            "nonfinite_fit",
            f"{unit}:{index}",
            failures,
        )
        _check(bool(fit.get("objectives")), "empty_objectives", f"{unit}:{index}", failures)
        _check(
            _finite_nonnegative(fit.get("fit_seconds")), "fit_seconds", f"{unit}:{index}", failures
        )

    source_hashes = receipt.get("source_sha256", {})
    _check(
        bool(source_hashes) or supervisor_generated, "source_hashes_missing", str(unit), failures
    )
    snapshots = receipt.get("source_snapshots", {})
    for source, expected in source_hashes.items():
        source_path = Path(source)
        _check(source_path.is_file(), "source_missing", source, failures)
        if source_path.is_file() and digest(source_path) != expected:
            warnings.append({"code": "working_source_changed", "detail": source})
        snapshot = Path(snapshots.get(source, ""))
        _check(snapshot.is_file(), "source_snapshot_missing", source, failures)
        if snapshot.is_file():
            _check(digest(snapshot) == expected, "source_snapshot_hash", str(snapshot), failures)

    wall = receipt.get("wall_seconds_before_sealing")
    if not supervisor_generated:
        _check(
            _finite_nonnegative(wall) and wall <= 90.0,
            "external_budget",
            f"{unit}: {wall}",
            failures,
        )
    parent = receipt.get("parent")
    if parent:
        parent_path = Path(parent.get("path", ""))
        _check(parent_path.is_file(), "parent_missing", str(parent_path), failures)
        if parent_path.is_file():
            _check(
                digest(parent_path) == parent.get("sha256"),
                "parent_hash",
                str(parent_path),
                failures,
            )
            parent_receipt, parent_failures = read_sealed(parent_path)
            failures.extend(
                {"code": "parent_" + f["code"], "detail": f["detail"]} for f in parent_failures
            )
            if parent_receipt:
                _check(
                    parent_receipt.get("status") == "unresolved",
                    "parent_status",
                    str(unit),
                    failures,
                )
                _check(parent_receipt.get("unit_id") == unit, "parent_unit", str(unit), failures)
                _check(parent_receipt.get("config") == config, "parent_config", str(unit), failures)
                total = wall + parent_receipt.get("wall_seconds_before_sealing", math.inf)
                _check(
                    math.isfinite(total) and total <= 180.0,
                    "cumulative_budget",
                    f"{unit}: {total}",
                    failures,
                )

    result.update(unit_id=unit, status=receipt.get("status"), passed=not failures)
    return result


def audit_launch(path: Path, prediction_path: Path) -> dict[str, Any]:
    launch, failures = read_sealed(path)
    result: dict[str, Any] = {"path": str(path), "failures": failures}
    if launch is None:
        result["passed"] = False
        return result
    _check(launch.get("timeout_seconds") == 90, "launch_timeout", str(path), failures)
    _check(launch.get("workers") in (1, 2), "worker_count", str(path), failures)
    _check(launch.get("numerical_threads") == 1, "numerical_threads", str(path), failures)
    _check(
        set(launch.get("numerical_environment", {}).values()) == {"1"},
        "numerical_environment",
        str(path),
        failures,
    )
    _check(prediction_path.is_file(), "prediction_missing", str(prediction_path), failures)
    if prediction_path.is_file():
        _check(
            launch.get("prediction_sha256") == digest(prediction_path),
            "launch_prediction_binding",
            str(prediction_path),
            failures,
        )
    wall = launch.get("wall_seconds")
    _check(_finite_nonnegative(wall) and wall <= 90.0, "launch_budget", f"{path}: {wall}", failures)
    cumulative = launch.get("cumulative_seconds")
    _check(
        _finite_nonnegative(cumulative) and cumulative <= 180.0,
        "launch_cumulative_budget",
        f"{path}: {cumulative}",
        failures,
    )
    native, native_failures = read_sealed(prediction_path)
    failures.extend(
        {"code": "prediction_" + row["code"], "detail": row["detail"]} for row in native_failures
    )
    if native:
        _check(
            launch.get("native_status") == native.get("status"),
            "native_status_binding",
            str(path),
            failures,
        )
        expected_launch = "error" if native.get("status") == "error" else launch.get("status")
        _check(
            launch.get("status") == expected_launch, "native_error_propagation", str(path), failures
        )
    result.update(passed=not failures, unit_id=launch.get("unit_id"), status=launch.get("status"))
    return result


def audit(paths: list[Path], plan_path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    plan = load_plan(plan_path)
    rows = [audit_receipt(path, plan) for path in paths]
    authority_failures = audit_authorities(plan)
    observed = [row.get("unit_id") for row in rows if row.get("unit_id")]
    duplicates = sorted({unit for unit in observed if observed.count(unit) > 1})
    return {
        "schema": "localization-approaches-fit-audit/v1",
        "truth_or_evaluator_read": False,
        "authority_failures": authority_failures,
        "duplicate_units": duplicates,
        "receipts": rows,
        "passed": not authority_failures and not duplicates and all(row["passed"] for row in rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = audit(args.receipts, args.plan)
    text = json.dumps(document, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    raise SystemExit(0 if document["passed"] else 1)


if __name__ == "__main__":
    main()
