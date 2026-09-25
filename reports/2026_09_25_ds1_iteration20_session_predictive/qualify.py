#!/usr/bin/env python3
"""Validate the iteration20 closure and effective rate-bound gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def effective_boundary_ok(row: dict) -> bool:
    margin = max(5.0 * float(row["scalar_optimizer_xatol_s_h"]), 1e-6)
    if abs(float(row["effective_boundary_margin_s_h"]) - margin) > 1e-15:
        return False
    bound = float(row["rate_bound_s_h"])
    values = [abs(float(value)) for value in row["rates_s_h"].values()]
    return row["effective_boundary_rate_count"] == 0 and all(
        value < bound - margin for value in values
    )


def qualified(inference: dict, fidelity: dict) -> bool:
    steps = inference.get("steps", [])
    return bool(
        inference.get("complete")
        and inference.get("reference_used_for_fit") is False
        and steps
        and not steps[-1].get("winner_on_edge")
        and fidelity.get("passed")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--fidelity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    inference = json.loads(args.inference.read_text())
    fidelity = json.loads(args.fidelity.read_text())
    if fidelity.get("inference", {}).get("sha256") != digest(args.inference):
        raise ValueError("fidelity check is not bound to inference")
    result = {
        "schema": "ds1-iteration20-session-balanced-profiled-qualification/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "geographic_interior": bool(
            inference.get("steps") and not inference["steps"][-1].get("winner_on_edge")
        ),
        "zero_rate_fidelity": {
            "path": str(args.fidelity),
            "sha256": digest(args.fidelity),
        },
        "zero_rate_direct_sgp4_passed": bool(fidelity.get("passed")),
        "widened_rate_audit": {
            "role": "diagnostic only; excluded from geographic selection and qualification",
            "rows": inference.get("final_widened_rate_audit", []),
        },
        "qualified": qualified(inference, fidelity),
    }
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"output": str(args.output), "qualified": result["qualified"]}))


if __name__ == "__main__":
    main()
