#!/usr/bin/env python3
"""Direct-SGP4 fidelity gate for the iteration21 zero-rate model."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
I20_FIDELITY = ROOT / "reports/2026_09_25_ds1_iteration20_session_predictive/zero_rate_fidelity.py"


def load(path: Path, name: str) -> Any:
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
    helper = load(I20_FIDELITY, "i21_fidelity_helper")
    # The helper implements the exact same frozen ID/tau zero-rate gate.  Its
    # isolated main is not used because iteration21 needs its own schema.
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    driver = helper.load_module(helper.DRIVER, "i21_zero_rate_driver")
    orbit = helper.load_module(helper.ORBIT, "i21_zero_rate_orbit")
    sealed = driver.load_iteration10(helper.ITERATION10)["winner"]["best_exact_by_group"]
    gates = []
    for group, tau in helper.TAUS.items():
        selected = dict(sealed[group])
        selected["tau_s"] = tau
        model = driver._prepared_model(group, inference["winner"], selected)
        zero = {str(name): 0.0 for name in model.source_names}
        gates.append(
            {
                "group_id": group,
                "tau_s": tau,
                "exact_sgp4_gate": orbit.exact_replay_gate(
                    model.data, model.receiver, model.search, tau, zero, tolerance_hz=0.2
                ),
            }
        )
    content = (
        json.dumps(
            {
                "schema": "ds1-iteration21-zero-rate-fidelity/v1",
                "reference_used": False,
                "inference_sha256": "sha256:"
                + hashlib.sha256(args.inference.read_bytes()).hexdigest(),
                "gates": gates,
                "passed": all(row["exact_sgp4_gate"]["passed"] for row in gates),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
