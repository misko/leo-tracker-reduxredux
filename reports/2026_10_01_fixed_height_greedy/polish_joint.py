"""Use remaining 180-second budget to polish one unresolved continuation mode."""
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


def _verified_document(path: Path, *, seal_key: str = "prediction_sha256") -> dict:
    document = json.loads(path.read_text())
    seal_path = path.with_suffix(".seal.json")
    if json.loads(seal_path.read_text()).get(seal_key) != digest(path):
        raise ValueError(f"seal mismatch: {path}")
    return document


def _verify_bindings(document: dict) -> None:
    for group in ("source_sha256", "inputs"):
        for path, expected in document.get(group, {}).items():
            if digest(path) != expected:
                raise ValueError(f"{group} binding mismatch: {path}")


def _eligible(continuation: dict, launch: dict) -> bool:
    best = continuation.get("best") or {}
    return bool(
        continuation.get("status") == "unresolved"
        and not best.get("converged", False)
        and best.get("objectives")
        and launch.get("status") == "complete"
        and launch.get("returncode") == 0
    )


def _prior_precision(full_layout_dimension: int) -> np.ndarray:
    return np.r_[0.0, 0.0, 1.0, np.full(full_layout_dimension - 4, 4.0)]


def _best(fits: list[dict]) -> dict | None:
    scored = [fit for fit in fits if fit.get("objectives")]
    return min(scored, key=lambda fit: fit["objectives"][-1]) if scored else None


def _remaining_budget(primary_launch: dict, continuation_launch: dict) -> tuple[float, float]:
    spent = float(primary_launch["wall_seconds"]) + float(continuation_launch["wall_seconds"])
    external = 180.0 - spent
    return external, min(85.0, external - 5.0)


def main(continuation_path: Path, output: Path, internal_budget: float) -> None:
    start = time.monotonic()
    continuation_path = Path(continuation_path)
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    continuation = _verified_document(continuation_path)
    continuation_launch_path = continuation_path.with_suffix(".launch.json")
    continuation_launch = json.loads(continuation_launch_path.read_text())
    parent_path = Path(continuation["parent_binding"]["path"])
    parent = _verified_document(parent_path)
    _verify_bindings(parent)
    _verify_bindings(continuation)
    primary_launch_path = parent_path.with_suffix(".launch.json")
    primary_launch = json.loads(primary_launch_path.read_text())
    external_remaining, expected_internal = _remaining_budget(primary_launch, continuation_launch)
    if not _eligible(continuation, continuation_launch):
        raise ValueError("continuation is not eligible for polish")
    if external_remaining <= 0 or expected_internal <= 0:
        raise ValueError("no cumulative budget remains")
    if abs(internal_budget - expected_internal) > 1e-6:
        raise ValueError("internal budget disagrees with bound launcher receipts")
    if continuation["parent_binding"]["sha256"] != digest(parent_path):
        raise ValueError("primary binding mismatch")
    scan = use_extended_orbits(load_scan(continuation["unit_id"]))
    if scan.inputs != continuation["inputs"] or scan.inputs != parent["inputs"]:
        raise ValueError("rebuilt scan inputs differ from parent chain")
    height = load_height_model()
    factors = [build_fixed_height_factor(obs, scan.bank, scan.layout, scan.config, height).factor
               for _, obs in scan.tracks]
    ports = [FixedHeightTrackLikelihood(obs, scan.bank, scan.config, height,
                                        degrees_of_freedom=4.0)
             for _, obs in scan.tracks]
    factors = [replace(factor, background_log_likelihood=port.background_log_likelihood)
               for factor, port in zip(factors, ports, strict=True)]
    sources = [HERE / name for name in (
        "polish_joint.py", "POLISH_PROTOCOL.md", "physics_fixed.py", "geoid.py",
        "orbit_input.py", "acquire.py", "PROTOCOL.md", "FREEZE.json",
    )]
    sources += [ROOT / "src/leo/analysis/greedy_joint_location.py",
                ROOT / "src/leo/analysis/robust_likelihood.py",
                HERE.parent / "2026_09_30_broad_prior_acquisition/spatial/rf.py"]
    receipt = {
        "schema": "fixed-height-joint-greedy-polish/v1",
        "unit_id": continuation["unit_id"],
        "status": "running",
        "qualification": "budget-adaptive third-stage diagnostic; prior results immutable",
        "source_sha256": source_bindings(sources),
        "inputs": scan.inputs,
        "height_input_bindings": height.input_bindings,
        "planned_factors": len(scan.tracks),
        "student_degrees_of_freedom": 4.0,
        "primary_binding": {"path": str(parent_path), "sha256": digest(parent_path),
                            "seal_sha256": digest(parent_path.with_suffix(".seal.json"))},
        "continuation_binding": {
            "path": str(continuation_path), "sha256": digest(continuation_path),
            "seal_sha256": digest(continuation_path.with_suffix(".seal.json")),
        },
        "primary_wall_seconds": primary_launch["wall_seconds"],
        "continuation_wall_seconds": continuation_launch["wall_seconds"],
        "external_remaining_seconds": external_remaining,
        "internal_budget_seconds": internal_budget,
        "maximum_additional_iterations": 24,
    }
    try:
        prior_modes = parent["fits"] + continuation["resumed_fits"]
        starting = continuation["best"]
        initial = np.r_[starting["mean"], starting["satellite_epoch_s"]]
        result = fit_joint_greedy(
            initial, factors, [port.branch_loglik_at_state for port in ports],
            _prior_precision(scan.layout.dimension),
            lambda state: bool(np.linalg.norm(state[:2]) <= 250.0),
            max_iterations=24, deadline=start + internal_budget, degrees_of_freedom=4.0,
        )
        polish = {
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
            "starting_objective": starting["objectives"][-1],
        }
        if (not polish["objectives"]
                or polish["objectives"][0] > polish["starting_objective"] + 1e-6):
            raise ValueError("polish initial objective exceeds continuation endpoint")
        receipt["polish_fit"] = polish
        receipt["best"] = _best(prior_modes + [polish])
        receipt["status"] = (
            "converged_local_mode" if receipt["best"]["converged"] else "unresolved"
        )
    except Exception as error:
        receipt.update(status="error", exception={
            "type": type(error).__name__, "message": str(error),
        })
    receipt["wall_seconds"] = time.monotonic() - start
    seal(output, receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("continuation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--internal-budget", type=float, required=True)
    arguments = parser.parse_args()
    main(arguments.continuation, arguments.output, arguments.internal_budget)
