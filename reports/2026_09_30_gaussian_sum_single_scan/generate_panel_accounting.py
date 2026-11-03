#!/usr/bin/env python3
"""Account for the stopped 48-scan panel without launching more work."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ARMS = ("gaussian_sum", "greedy", "prior_only")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def verify_attempt(path: Path, *, revision: str) -> dict[str, Any]:
    receipt = read(path)
    errors = []
    seal_path = path.with_suffix(".seal.json")
    launch_path = path.with_suffix(".launch.json")
    state = receipt.get("state_artifact", {})
    checks = {"seal": False, "inputs": True, "state": False, "source_snapshots": True}
    if seal_path.exists():
        seal = read(seal_path)
        checks["seal"] = seal.get("prediction_sha256") == digest(path)
    if not checks["seal"]:
        errors.append("seal_missing_or_prediction_digest_mismatch")
    for named, expected in receipt.get("inputs", {}).items():
        source = Path(named)
        if not source.exists() or digest(source) != expected:
            checks["inputs"] = False
            errors.append(f"input_missing_or_digest_mismatch:{named}")
    state_path = Path(state.get("path", ""))
    checks["state"] = bool(state_path.is_file() and state.get("sha256") == digest(state_path))
    if not checks["state"]:
        errors.append("state_missing_or_digest_mismatch")
    source_checks = []
    for named, expected in receipt.get("source_sha256", {}).items():
        original = Path(named)
        candidate = original
        source_kind = "live"
        if revision == "v1" and original.name in {"run.py", "physics.py", "gaussian_sum_location.py", "PROTOCOL.md"}:
            candidate = HERE / "source_snapshots" / "v1" / original.name
            source_kind = "frozen_v1_snapshot"
        ok = candidate.is_file() and digest(candidate) == expected
        source_checks.append({"recorded_path": named, "verified_path": str(candidate), "kind": source_kind, "verified": ok})
        if not ok:
            checks["source_snapshots"] = False
            errors.append(f"source_missing_or_digest_mismatch:{named}")
    launch = read(launch_path) if launch_path.exists() else None
    if launch is None:
        errors.append("launcher_receipt_missing")
    return {
        "revision": revision, "receipt_path": str(path), "receipt_sha256": digest(path),
        "unit_id": receipt.get("unit_id"), "prior_name": receipt.get("prior_name"),
        "arm": receipt.get("arm"), "native_status": receipt.get("status"),
        "factors_completed": len(receipt.get("checkpoints", [])),
        "gate_failures": receipt.get("gate_failures", []),
        "exception": receipt.get("exception"), "wall_seconds": receipt.get("wall_seconds"),
        "launcher": None if launch is None else {
            "path": str(launch_path), "sha256": digest(launch_path), "status": launch.get("status"),
            "native_status": launch.get("native_status"), "returncode": launch.get("returncode"),
        },
        "verification": checks | {"sources": source_checks, "errors": errors},
    }


def build_accounting() -> dict[str, Any]:
    selection = read(HERE / "selection.json")
    units = [row["unit_id"] for dataset in ("DS9", "DS10", "DS11") for row in selection["selected"][dataset]]
    attempts = [verify_attempt(path, revision=path.parent.name) for path in sorted((HERE / "runs").glob("*/*.json"))
                if not any(tag in path.name for tag in (".progress.json", ".seal.json", ".launch.json"))]
    v2_regional = {(row["unit_id"], row["arm"]): row for row in attempts
                   if row["revision"] == "v2" and row["prior_name"] == "regional"}
    panel = []
    for unit in units:
        for arm in ARMS:
            attempted = v2_regional.get((unit, arm))
            panel.append({
                "unit_id": unit, "dataset": unit.split("-")[0], "arm": arm, "prior_name": "regional",
                "accounting_status": "attempted" if attempted else "pending_not_started_gate",
                "attempt_receipt": None if attempted is None else attempted["receipt_path"],
                "native_status": None if attempted is None else attempted["native_status"],
            })
    stress = [row for row in attempts if row["revision"] == "v2" and row["prior_name"] == "stress"]
    superseded = [row for row in attempts if row["revision"] == "v1"]
    return {
        "schema": "gaussian-sum-panel-accounting/v1",
        "decision": "scientific_stop",
        "stop_reasons": [
            "regional_v2_gaussian_sum_discarded_13.01_percent_pre_normalization_mass_at_factor_18",
            "stress_v2_gaussian_sum_orbit_time_support_error_after_4_factors",
            "regional_v2_greedy_completed_50_factors_without_rescuing_gaussian_sum_gate",
        ],
        "selection_sha256": digest(HERE / "selection.json"),
        "planned_panel": {"units": 48, "arms_per_unit": 3, "attempts": 144,
                          "attempted": sum(row["accounting_status"] == "attempted" for row in panel),
                          "pending_not_started_gate": sum(row["accounting_status"] == "pending_not_started_gate" for row in panel),
                          "rows": panel},
        "stress_attempts_outside_primary_panel": stress,
        "superseded_v1_engineering_attempts": superseded,
        "attempt_verification_errors": [
            {"receipt_path": row["receipt_path"], "errors": row["verification"]["errors"]}
            for row in attempts if row["verification"]["errors"]
        ],
        "independence_note": "v1, v2, and stress retries of DS9-F001 are attempts on one scan, not independent scans",
        "no_further_work": "No further exports or fits authorized after the scientific stop.",
    }


def main() -> None:
    output = HERE / "panel-accounting.json"
    output.write_text(json.dumps(build_accounting(), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"path": str(output), "sha256": digest(output)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
