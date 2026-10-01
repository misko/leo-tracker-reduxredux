"""Post-freeze acceptance audit for the official localization campaign."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FREEZE = HERE / "FREEZE.json"
FREEZE_DIGEST = HERE / "FREEZE.sha256"
PLAN = ROOT / "plans/localization-approaches-2026-10-01/benchmark.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _failure(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def audit_freeze(
    freeze_path: Path = FREEZE,
    digest_path: Path = FREEZE_DIGEST,
    repository_root: Path = ROOT,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    failures = []
    freeze = json.loads(freeze_path.read_text())
    expected = digest_path.read_text().strip()
    if expected != digest(freeze_path):
        failures.append(_failure("freeze_digest", str(freeze_path)))
    if freeze.get("schema") != "localization-approach-freeze/v1":
        failures.append(_failure("freeze_schema", repr(freeze.get("schema"))))
    plan_path = repository_root / freeze.get("plan_path", "")
    if not plan_path.is_file() or digest(plan_path) != freeze.get("plan_sha256"):
        failures.append(_failure("freeze_plan", str(plan_path)))
    for source, expected_hash in freeze.get("source_sha256", {}).items():
        path = Path(source)
        if not path.is_file():
            failures.append(_failure("frozen_source_missing", source))
        elif digest(path) != expected_hash:
            failures.append(_failure("frozen_source_hash", source))
    config = freeze.get("config", {})
    required = {
        "predictor": "selected",
        "seed_source": "fresh",
        "degrees_of_freedom": 4.0,
        "seed_limit": 3,
        "max_iterations": 24,
        "primary_external_s": 90,
        "continuation_external_s": 90,
        "acquisition_budget_seconds": 50.0,
    }
    if config != required:
        failures.append(_failure("freeze_config", repr(config)))
    if not freeze.get("admitted_arms") or len(set(freeze["admitted_arms"])) != len(
        freeze["admitted_arms"]
    ):
        failures.append(_failure("freeze_admitted_arms", repr(freeze.get("admitted_arms"))))
    return freeze, failures


def _proposal_identity(proposal: dict[str, Any]) -> dict[str, Any]:
    """Remove timing only; retain every scientific proposal field and seed order."""
    return {key: value for key, value in proposal.items() if key != "wall_seconds"}


def audit_attempt_config(
    receipt: dict[str, Any],
    launch: dict[str, Any],
    freeze: dict[str, Any],
) -> list[dict[str, str]]:
    failures = []
    arm = receipt.get("config", {}).get("arm")
    if arm not in freeze["admitted_arms"]:
        failures.append(_failure("arm_not_admitted", repr(arm)))
    expected_config = {"arm": arm, **freeze["config"]}
    if receipt.get("config") != expected_config:
        failures.append(_failure("official_config", repr(receipt.get("config"))))
    if launch.get("arm") != arm:
        failures.append(_failure("launch_arm", repr(launch.get("arm"))))
    command = launch.get("command", [])
    required_arguments = {
        "--seed-source": "fresh",
        "--predictor": "selected",
        "--acquisition-budget": "50.0",
        "--arm": arm,
    }
    for option, value in required_arguments.items():
        try:
            actual = command[command.index(option) + 1]
        except (ValueError, IndexError):
            actual = None
        if actual != value:
            failures.append(_failure("launch_config", f"{option}={actual!r}"))
    frozen_sources = freeze["source_sha256"]
    receipt_sources = receipt.get("source_sha256", {})
    for source, source_hash in receipt_sources.items():
        if frozen_sources.get(source) != source_hash:
            failures.append(_failure("source_outside_freeze", source))
    required_names = {
        "PROTOCOL.md",
        "adapter.py",
        "batch.py",
        "replay_approach.py",
    }
    if arm == "A1":
        required_names.update({"localization_evaluation.py", "localization_fast.py"})
    elif arm == "B1":
        required_names.update({"localization_soft.py", "batch_physics.py"})
    present_names = {Path(source).name for source in receipt_sources}
    missing = sorted(required_names - present_names)
    if missing:
        failures.append(_failure("required_frozen_sources", repr(missing)))
    return failures


def audit_campaign(run_root: Path, *, require_complete: bool = False) -> dict[str, Any]:
    freeze, freeze_failures = audit_freeze()
    plan = json.loads(PLAN.read_text())
    fit_audit = _module("official_fit_audit", HERE / "audit_receipts.py")
    authority_failures = fit_audit.audit_authorities(plan, ROOT)
    expected_units = [row["unit_id"] for row in plan["ordered_units"]]
    rows = []
    proposals: dict[str, dict[str, dict[str, Any]]] = {}
    seen: set[tuple[str, str, bool]] = set()
    for launch_path in sorted(run_root.rglob("DS*.launch.json")):
        launch = json.loads(launch_path.read_text())
        receipt_path = launch_path.with_name(launch_path.name.replace(".launch.json", ".json"))
        receipt_audit = fit_audit.audit_receipt(receipt_path, plan)
        launch_audit = fit_audit.audit_launch(launch_path, receipt_path)
        receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        arm = receipt.get("config", {}).get("arm", launch.get("arm"))
        unit = launch.get("unit_id")
        continuation = bool(receipt.get("parent"))
        identity = (str(arm), str(unit), continuation)
        failures = []
        if identity in seen:
            failures.append(_failure("duplicate_stage_attempt", repr(identity)))
        seen.add(identity)
        if not receipt_audit["passed"]:
            failures.append(_failure("receipt_audit", repr(receipt_audit["failures"])))
        if not launch_audit["passed"]:
            failures.append(_failure("launch_audit", repr(launch_audit["failures"])))
        if receipt:
            failures.extend(audit_attempt_config(receipt, launch, freeze))
            if not continuation and receipt.get("proposal"):
                proposals.setdefault(str(unit), {})[str(arm)] = _proposal_identity(
                    receipt["proposal"]
                )
        rows.append(
            {
                "arm": arm,
                "unit_id": unit,
                "continuation": continuation,
                "receipt_path": str(receipt_path),
                "launch_path": str(launch_path),
                "passed": not failures,
                "failures": failures,
            }
        )

    proposal_failures = []
    for unit, by_arm in sorted(proposals.items()):
        identities = list(by_arm.values())
        if len(identities) > 1 and any(value != identities[0] for value in identities[1:]):
            proposal_failures.append(_failure("common_proposal_mismatch", unit))

    completeness_failures = []
    if require_complete:
        primaries = {(row["arm"], row["unit_id"]) for row in rows if not row["continuation"]}
        expected = {(arm, unit) for arm in freeze["admitted_arms"] for unit in expected_units}
        missing = sorted(expected - primaries)
        extra = sorted(primaries - expected)
        if missing:
            completeness_failures.append(_failure("official_attempts_missing", str(len(missing))))
        if extra:
            completeness_failures.append(_failure("official_attempts_extra", repr(extra)))

    all_failures = (
        freeze_failures
        + authority_failures
        + proposal_failures
        + completeness_failures
        + [failure for row in rows for failure in row["failures"]]
    )
    return {
        "schema": "localization-official-audit/v1",
        "freeze_sha256": digest(FREEZE),
        "generic_evaluator_enforces_freeze": False,
        "this_companion_is_required_for_final_acceptance": True,
        "require_complete": require_complete,
        "attempt_count": len(rows),
        "status_counts": dict(
            sorted(Counter("passed" if row["passed"] else "failed" for row in rows).items())
        ),
        "freeze_failures": freeze_failures,
        "authority_failures": authority_failures,
        "proposal_failures": proposal_failures,
        "completeness_failures": completeness_failures,
        "rows": rows,
        "passed": not all_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    result = audit_campaign(args.run_root, require_complete=args.require_complete)
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
