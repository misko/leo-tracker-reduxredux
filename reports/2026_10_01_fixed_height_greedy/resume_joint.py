"""Deterministically continue unresolved frozen joint-mode fits."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.append(str(HERE.parent / "2026_09_30_broad_prior_acquisition"))
from acquire import FixedHeightTrackLikelihood  # noqa: E402
from common import digest, load_scan, seal, source_bindings  # noqa: E402
from geoid import load_height_model  # noqa: E402
from orbit_input import use_extended_orbits  # noqa: E402
from physics_fixed import build_fixed_height_factor  # noqa: E402

from leo.analysis.greedy_joint_location import fit_joint_greedy  # noqa: E402


def _load_verified_parent(path: Path) -> dict:
    parent = json.loads(path.read_text())
    seal_path = path.with_suffix(".seal.json")
    if json.loads(seal_path.read_text()).get("prediction_sha256") != digest(path):
        raise ValueError("parent seal mismatch")
    if parent.get("schema") != "fixed-height-joint-greedy/v1":
        raise ValueError("parent schema mismatch")
    for name in ("source_sha256", "inputs"):
        for source, expected in parent.get(name, {}).items():
            if digest(source) != expected:
                raise ValueError(f"parent {name} binding mismatch: {source}")
    if parent.get("student_degrees_of_freedom") != 4.0:
        raise ValueError("parent likelihood mismatch")
    return parent


def _best(fits: list[dict]) -> dict | None:
    scored = [fit for fit in fits if fit.get("objectives")]
    return min(scored, key=lambda fit: fit["objectives"][-1]) if scored else None


def _initial_objective_consistent(parent_final: float, resumed: tuple[float, ...]) -> bool:
    return bool(resumed and resumed[0] <= parent_final + 1e-6)


def main(parent_path: Path, output: Path) -> None:
    start = time.monotonic()
    parent_path = Path(parent_path)
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    parent = _load_verified_parent(parent_path)
    scan = use_extended_orbits(load_scan(parent["unit_id"]))
    if scan.inputs != parent["inputs"]:
        raise ValueError("rebuilt scan inputs differ from parent")
    height = load_height_model()
    factors = [build_fixed_height_factor(obs, scan.bank, scan.layout, scan.config, height).factor
               for _, obs in scan.tracks]
    ports = [FixedHeightTrackLikelihood(obs, scan.bank, scan.config, height,
                                        degrees_of_freedom=4.0)
             for _, obs in scan.tracks]
    factors = [replace(factor, background_log_likelihood=port.background_log_likelihood)
               for factor, port in zip(factors, ports, strict=True)]
    scores = [port.branch_loglik_at_state for port in ports]
    precision = np.r_[0.0, 0.0, 1.0, np.full(scan.layout.dimension - 4, 4.0)]
    sources = [HERE / name for name in (
        "resume_joint.py", "physics_fixed.py", "geoid.py", "orbit_input.py", "acquire.py",
        "PROTOCOL.md", "FREEZE.json", "CONTINUATION_PROTOCOL.md",
    )]
    sources += [ROOT / "src/leo/analysis/greedy_joint_location.py",
                ROOT / "src/leo/analysis/robust_likelihood.py",
                HERE.parent / "2026_09_30_broad_prior_acquisition/spatial/rf.py"]
    receipt = {
        "schema": "fixed-height-joint-greedy-resume/v1",
        "unit_id": parent["unit_id"],
        "status": "running",
        "source_sha256": source_bindings(sources),
        "inputs": scan.inputs,
        "height_input_bindings": height.input_bindings,
        "height_msl_m": 30.48,
        "planned_factors": len(scan.tracks),
        "qualification": "same objective continuation; no observation or posterior-prior reuse",
        "parent_binding": {"path": str(parent_path), "sha256": digest(parent_path)},
        "student_degrees_of_freedom": 4.0,
        "additional_iterations_per_seed": 24,
        "parent_fits": parent["fits"],
        "resumed_fits": [],
    }
    try:
        unresolved = sorted(
            (fit for fit in parent["fits"] if not fit["converged"] and fit["objectives"]),
            key=lambda fit: fit["objectives"][-1],
        )
        for parent_fit in unresolved:
            if time.monotonic() - start > 80.0:
                break
            initial = np.r_[parent_fit["mean"], parent_fit["satellite_epoch_s"]]
            result = fit_joint_greedy(
                initial, factors, scores, precision,
                lambda state: bool(np.linalg.norm(state[:2]) <= 250.0),
                max_iterations=24, deadline=start + 85.0, degrees_of_freedom=4.0,
            )
            if not _initial_objective_consistent(
                parent_fit["objectives"][-1], result.objectives
            ):
                raise ValueError("resumed initial objective exceeds parent endpoint")
            receipt["resumed_fits"].append({
                "mean": result.mean[:5].tolist(),
                "satellite_epoch_s": result.mean[5:].tolist(),
                "associations": [
                    str(scan.bank.norad_ids[index])
                    if index < len(scan.bank.norad_ids) else "background"
                    for index in result.associations
                ],
                "objectives": list(result.objectives),
                "converged": result.converged,
                "accepted_step_norms": list(result.accepted_step_norms),
                "iterations": result.iterations,
                "reason": result.reason,
                "parent_seed": parent_fit["seed"],
                "parent_final_objective": parent_fit["objectives"][-1],
                "initial_objective_not_above_parent": True,
                "seconds": time.monotonic() - start,
            })
        candidates = parent["fits"] + receipt["resumed_fits"]
        receipt["best"] = _best(candidates)
        receipt["status"] = (
            "converged_local_mode"
            if receipt["best"] is not None and receipt["best"]["converged"] else "unresolved"
        )
    except Exception as error:
        receipt.update(status="error", exception={
            "type": type(error).__name__, "message": str(error),
        })
    receipt["wall_seconds"] = time.monotonic() - start
    seal(output, receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("parent", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.parent, arguments.output)
