#!/usr/bin/env python3
"""Reference-free exact replay gate for iteration 15."""

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
GROUPS = ("20260921_00", "20260921_16")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False or not inference.get("steps"):
        raise ValueError("inference must be sealed and reference-free")
    driver = load_module(DRIVER, "i15_qualify_driver")
    orbit = load_module(ORBIT, "i15_qualify_orbit")
    iteration10 = driver.load_iteration10(ITERATION10)
    sealed_groups = iteration10["winner"]["best_exact_by_group"]
    winner = inference["winner"]
    gates = []
    for group in GROUPS:
        model = driver._prepared_model(group, winner, sealed_groups[group])
        fit = driver.fit(model, scales_enabled=False)
        gate = orbit.exact_replay_gate(
            model.data,
            model.receiver,
            model.search,
            float(sealed_groups[group]["tau_s"]),
            fit["rates_s_h"],
            tolerance_hz=0.2,
        )
        gates.append(
            {
                "group_id": group,
                "fit_converged": fit["converged"],
                "rate_boundary_count": fit["rate_boundary_count"],
                "selection_objective": fit["selection_objective"],
                "exact_full_observation_capped_loss": fit[
                    "exact_full_observation_capped_loss"
                ],
                "exact_sgp4_gate": gate,
            }
        )
    qualified = bool(
        inference.get("qualified")
        and all(row["fit_converged"] for row in gates)
        and all(row["exact_sgp4_gate"]["passed"] for row in gates)
    )
    output = {
        "schema": "ds1-iteration15-information-weighted-qualification/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "exact_replay_gates": gates,
        "qualified": qualified,
    }
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"output": str(args.output), "qualified": qualified}))


if __name__ == "__main__":
    main()
