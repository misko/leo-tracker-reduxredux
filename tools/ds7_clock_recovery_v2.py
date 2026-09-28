#!/usr/bin/env python3
"""Audit sealed DS7 clock-recovery qualification with the missing gate checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declared_condition_limit(gate: dict) -> float:
    """Read the numeric ceiling from the immutable gate declaration."""
    text = gate["admission_gates"]["identifiability"]
    match = re.search(r"condition number\s*<=\s*([0-9]+(?:\.[0-9]+)?)", text)
    if match is None:
        raise ValueError("gate does not declare a condition-number ceiling")
    limit = float(match.group(1))
    if not math.isfinite(limit) or limit <= 0.0:
        raise ValueError("condition-number ceiling must be positive and finite")
    return limit


def corrected_qualification(result: dict, maximum_condition_number: float) -> dict:
    """Add boundary and condition checks without changing scientific thresholds."""
    rank = result["projected_rank"]
    condition = float(rank["condition_number"])
    rank_ok = int(rank["rank"]) == int(rank["columns"])
    condition_ok = math.isfinite(condition) and condition <= maximum_condition_number
    cases = []
    for index, case in enumerate(result["cases"]):
        boundary_free = case.get("boundary_hit") is False
        prior_qualified = case.get("qualified") is True
        cases.append(
            {
                "case_index": index,
                "injected_native_hz_s": case.get("injected_native_hz_s"),
                "prior_qualified": prior_qualified,
                "boundary_free": boundary_free,
                "corrected_qualified": prior_qualified and boundary_free,
            }
        )
    qualified = (
        result.get("status") == "qualified"
        and rank_ok
        and condition_ok
        and bool(cases)
        and all(case["corrected_qualified"] for case in cases)
    )
    return {
        "corrected_status": "qualified" if qualified else "unqualified",
        "rank_full": rank_ok,
        "condition_number": condition,
        "maximum_condition_number": maximum_condition_number,
        "condition_within_limit": condition_ok,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--gate-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text())
    result = json.loads(args.result.read_text())
    gate = json.loads(args.gate_config.read_text())
    limit = declared_condition_limit(gate)
    audit = corrected_qualification(result, limit)
    tool = Path(__file__)
    receipt = {
        "schema": "ds7-clock-recovery-qualification-audit/v2",
        "scope": "qualification repair only; sealed recovery was not rerun",
        "reference_audit": "reference_excluded",
        "bindings": {
            "spec": {"path": str(args.spec), "sha256": sha256(args.spec)},
            "result": {"path": str(args.result), "sha256": sha256(args.result)},
            "gate_config": {
                "path": str(args.gate_config),
                "sha256": sha256(args.gate_config),
            },
            "tool": {"path": str(tool), "sha256": sha256(tool)},
        },
        "prior_status": result.get("status"),
        "declared_cases": spec.get("cases_native_hz_s"),
        **audit,
        "interpretation": (
            "This repairs two qualification checks only. It supplies no hardware calibration, "
            "physical drift bound, real-data clock fit, or geographic evidence."
        ),
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
