#!/usr/bin/env python3
"""Reference-free contract and exact-replay qualification for DS1 iteration 18."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUN = HERE / "run.py"
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


def timing_interior(timing: dict[str, Any]) -> bool:
    return bool(
        timing.get("qualified")
        and timing.get("selected_taus_s")
        and all(
            timing["groups"][group]["qualified"]
            and not timing["groups"][group]["steps"][-1]["winner_on_edge"]
            for group in GROUPS
        )
    )


def geographic_interior(inference: dict[str, Any]) -> bool:
    geographic = inference.get("geographic")
    return bool(
        geographic
        and geographic.get("qualified")
        and geographic.get("steps")
        and not geographic["steps"][-1]["winner_on_edge"]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output already exists")
    inference = json.loads(args.inference.read_text())
    runner = load_module(RUN, "i18_qualify_runner")
    if inference.get("schema") != runner.INFERENCE_SCHEMA:
        raise ValueError("unexpected inference schema")
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference is not reference-free")
    timing_path = Path(inference["timing_refresh"]["path"])
    if digest(timing_path) != inference["timing_refresh"]["sha256"]:
        raise ValueError("timing seal digest does not match inference")
    timing_payload = json.loads(timing_path.read_text())
    timing = runner.load_timing_seal(timing_path, context=timing_payload["context"])
    if timing.get("selected_taus_s") != inference["timing_refresh"].get("selected_taus_s"):
        raise ValueError("selected taus differ between timing seal and inference")

    gates: list[dict[str, Any]] = []
    timing_ok = timing_interior(timing)
    geographic_ok = geographic_interior(inference)
    if timing_ok and geographic_ok:
        driver = load_module(DRIVER, "i18_qualify_driver")
        orbit = load_module(ORBIT, "i18_qualify_orbit")
        iteration10 = driver.load_iteration10(ITERATION10)
        sealed_groups = iteration10["winner"]["best_exact_by_group"]
        winner = inference["geographic"]["winner"]
        for group in GROUPS:
            refreshed = copy.deepcopy(sealed_groups[group])
            refreshed["tau_s"] = float(timing["selected_taus_s"][group])
            model = driver._prepared_model(group, winner, refreshed)
            fit = driver.fit(model, scales_enabled=False)
            gate = orbit.exact_replay_gate(
                model.data,
                model.receiver,
                model.search,
                float(refreshed["tau_s"]),
                fit["rates_s_h"],
                tolerance_hz=0.2,
            )
            gates.append(
                {
                    "group_id": group,
                    "tau_s": refreshed["tau_s"],
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
        and timing_ok
        and geographic_ok
        and len(gates) == len(GROUPS)
        and all(row["fit_converged"] for row in gates)
        and all(row["rate_boundary_count"] == 0 for row in gates)
        and all(row["exact_sgp4_gate"]["passed"] for row in gates)
    )
    output = {
        "schema": "ds1-iteration18-timing-refresh-qualification/v1",
        "reference_used": False,
        "inference": {"path": str(args.inference), "sha256": digest(args.inference)},
        "timing_refresh": {"path": str(timing_path), "sha256": digest(timing_path)},
        "timing_interior": timing_ok,
        "geographic_interior": geographic_ok,
        "exact_replay_gates": gates,
        "qualified": qualified,
    }
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"output": str(args.output), "qualified": qualified}))


if __name__ == "__main__":
    main()
