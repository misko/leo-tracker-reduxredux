#!/usr/bin/env python3
"""Constrain the frozen truth-free regional refiner to a declared circle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def constrained_refine_modes(training_score, seeds, region, *, radius_km, max_evaluations=140):
    """Nelder-Mead refinement; points outside the circle are never scored."""
    if not np.isfinite(radius_km) or radius_km <= 0 or max_evaluations < 4:
        raise ValueError("positive finite radius and at least four evaluations required")
    fits = []
    for supplied_seed in seeds:
        seed = np.asarray(supplied_seed, float)
        if seed.shape != (2,) or not np.all(np.isfinite(seed)) or np.linalg.norm(seed) > radius_km:
            raise ValueError("every seed must lie inside the declared circle")
        simplex = np.tile(seed, (3, 1))
        for axis in range(2):
            trial = seed.copy()
            trial[axis] += 10
            if np.linalg.norm(trial) > radius_km:
                trial[axis] -= 20
            if np.linalg.norm(trial) > radius_km:
                trial *= (radius_km - 1e-6) / np.linalg.norm(trial)
            simplex[axis + 1] = trial
        scored_points = []

        def objective(point, scored_points=scored_points):
            radius = float(np.linalg.norm(point))
            if radius > radius_km:
                return 1e100 + (radius - radius_km) ** 2
            scored_points.append(np.asarray(point, float).copy())
            return -float(training_score(point))

        fit = minimize(
            objective,
            seed,
            method="Nelder-Mead",
            bounds=[(-radius_km, radius_km)] * 2,
            options={
                "maxfev": max_evaluations,
                "xatol": 0.02,
                "fatol": 1e-5,
                "initial_simplex": simplex,
            },
        )
        if np.linalg.norm(fit.x) > radius_km + 1e-9 or any(
            np.linalg.norm(point) > radius_km + 1e-12 for point in scored_points
        ):
            raise RuntimeError("circular constraint was violated")
        fits.append(
            {
                "east_km": float(fit.x[0]),
                "north_km": float(fit.x[1]),
                "training_score": -float(fit.fun),
                "converged": bool(fit.success),
                "evaluations": int(fit.nfev),
                "message": str(fit.message),
                "seed_east_north_km": seed.tolist(),
                "radius_km": float(np.linalg.norm(fit.x)),
                "boundary_distance_km": float(radius_km - np.linalg.norm(fit.x)),
            }
        )
    return fits


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    source = Path(args.refiner)
    acquisition_receipt_path = args.run.parent / "receipt.json"
    acquisition_receipt = json.loads(acquisition_receipt_path.read_text())
    acquisition_result = json.loads((args.run / "result.json").read_text())
    region = acquisition_result["region"]
    if (
        acquisition_receipt.get("schema") != "circular-regional-acquisition/v1"
        or acquisition_receipt.get("complete") is not True
        or acquisition_receipt.get("position_truth_used") is not False
        or acquisition_receipt.get("radius_km") != args.radius_km
        or acquisition_receipt.get("scoring_result_digest") != digest(args.run / "result.json")
        or args.radius_km > min(region["width_km"], region["height_km"]) / 2
    ):
        raise ValueError("refinement circle differs from its sealed acquisition authority")
    spec = importlib.util.spec_from_file_location("frozen_circle_refiner", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scorer_spec = importlib.util.spec_from_file_location("frozen_circle_replay", args.scorer)
    scorer = importlib.util.module_from_spec(scorer_spec)
    scorer_spec.loader.exec_module(scorer)
    partition_receipt = None
    if args.five_block:
        adapter_path = Path(__file__).with_name("replay_five_block_regional.py")
        adapter_spec = importlib.util.spec_from_file_location("circle_five_block", adapter_path)
        adapter = importlib.util.module_from_spec(adapter_spec)
        adapter_spec.loader.exec_module(adapter)
        loader = adapter.FiveBlockLoader()
        scorer.load_observations = loader
        partition_receipt = json.loads((args.run / "partition-receipt.json").read_text())
        if partition_receipt.get("partition") != adapter.PARTITION:
            raise ValueError("five-block refinement requires its acquisition partition receipt")
    module.replay_module = lambda: scorer
    frozen_digest = module.digest

    def bound_digest(path):
        path = Path(path)
        if not path.exists() and path.name == "regional_doppler.py":
            path = Path(__file__).parents[2] / "src/leo/analysis/research/regional_doppler.py"
        return frozen_digest(path)

    module.digest = bound_digest
    module.refine_modes = lambda training_score, seeds, region, max_evaluations=140: (
        constrained_refine_modes(
            training_score,
            seeds,
            region,
            radius_km=args.radius_km,
            max_evaluations=max_evaluations,
        )
    )
    module.run(args)
    result_path = args.output / "result.json"
    result = json.loads(result_path.read_text())
    selected_radius = float(np.hypot(result["selected"]["east_km"], result["selected"]["north_km"]))
    if selected_radius > args.radius_km + 1e-9:
        raise RuntimeError("selected refinement lies outside the circle")
    receipt = {
        "schema": "circular-regional-refinement/v1",
        "complete": result.get("complete") is True,
        "position_truth_used": False,
        "radius_km": args.radius_km,
        "selected_radius_km": selected_radius,
        "boundary_distance_km": args.radius_km - selected_radius,
        "acquisition_result_digest": digest(args.run / "result.json"),
        "acquisition_receipt_digest": digest(acquisition_receipt_path),
        "frozen_refiner_digest": digest(source),
        "adapter_digest": digest(__file__),
        "result_digest": digest(result_path),
        "final_observation_policy": "all available RF rows; acquisition used capped rows",
        "partition_receipt_digest": (
            None if partition_receipt is None else partition_receipt["content_digest"]
        ),
    }
    (args.output / "circle-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refiner", type=Path, required=True)
    parser.add_argument("--scorer", type=Path, required=True)
    parser.add_argument("--radius-km", type=float, required=True)
    parser.add_argument("--single-session")
    parser.add_argument("--modes", type=int, default=3)
    parser.add_argument("--max-evaluations", type=int, default=140)
    parser.add_argument("--budget-seconds", type=float, default=900)
    parser.add_argument("--five-block", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
