#!/usr/bin/env python3
"""Direct SGP4 fidelity check for iteration20's zero-rate geographic model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "reports/2026_09_24_ds1_iteration12_session_scale/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
ITERATION10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
TAUS = {"20260921_00": -0.75, "20260921_16": -0.50}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    driver = load_module(DRIVER, "i20_zero_rate_driver")
    orbit = load_module(ORBIT, "i20_zero_rate_orbit")
    sealed = driver.load_iteration10(ITERATION10)["winner"]["best_exact_by_group"]
    gates = []
    for group, tau in TAUS.items():
        selected = dict(sealed[group])
        selected["tau_s"] = tau
        model = driver._prepared_model(group, inference["winner"], selected)
        zero_rates = {str(name): 0.0 for name in model.source_names}
        gates.append(
            {
                "group_id": group,
                "tau_s": tau,
                "rate_definition": "all causal per-NORAD rates fixed exactly to zero",
                "exact_sgp4_gate": orbit.exact_replay_gate(
                    model.data,
                    model.receiver,
                    model.search,
                    tau,
                    zero_rates,
                    tolerance_hz=0.2,
                ),
            }
        )
    result = {
        "schema": "ds1-iteration20-zero-rate-fidelity/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "gates": gates,
        "passed": all(row["exact_sgp4_gate"]["passed"] for row in gates),
    }
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"output": str(args.output), "passed": result["passed"]}))


if __name__ == "__main__":
    main()
