#!/usr/bin/env python3
"""Seal a DS3-local execution plan for one omitted historical method arm.

This intentionally has no inference mode.  It turns a reviewed coverage row
into a reproducible DS3 job contract only after its required DS3 parents are
sealed.  A numerical runner must be added per scientifically distinct arm;
this utility prevents a plan from silently falling back to DS1 coordinates,
identities, or timing values while that work is pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(path: Path) -> dict[str, Any]:
    words = path.with_suffix(path.suffix + ".sha256").read_text().strip().split(maxsplit=1)
    if not words or words[0].removeprefix("sha256:") != digest(path).removeprefix("sha256:"):
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def write(path: Path, value: dict[str, Any]) -> None:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def build_plan(coverage: dict[str, Any], coverage_sha256: str, method_id: str) -> dict[str, Any]:
    row = next((item for item in coverage["arms"] if item["method_id"] == method_id), None)
    if row is None:
        raise ValueError(f"unknown method arm: {method_id}")
    if row["execution_state"] not in {"planned", "blocked_on_live_parent"}:
        raise ValueError(f"method arm is not executable: {row['execution_state']}")
    if row["adapter_state"] != "implemented":
        raise ValueError("no DS3-native numerical adapter is implemented for this arm")
    return {
        "schema": "ds3-method-arm-plan/v1",
        "method_id": method_id,
        "coverage_plan_sha256": coverage_sha256,
        "ds3_input_policy": "fresh DS3 all56 only; no DS1 data-bearing state",
        "dependencies": row["dependencies"],
        "command": row["command"],
        "expected_output_schema": row["expected_output_schema"],
        "terminal_gate": row["terminal_gate"],
        "runtime_estimate": row["runtime_estimate"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--method-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    coverage = sealed(args.coverage)
    if coverage.get("schema") != "ds3-method-execution-coverage-plan/v1":
        raise ValueError("invalid coverage plan")
    plan = build_plan(coverage, digest(args.coverage), args.method_id)
    write(args.output, plan)


if __name__ == "__main__":
    main()
