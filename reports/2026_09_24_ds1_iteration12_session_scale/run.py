#!/usr/bin/env python3
"""DS1 iteration 12: converged exact common-plus-session Doppler-scale arm.

This is deliberately a bounded local ablation.  It starts only from the
sealed reference-free iteration-10 coordinate, its per-group tau, and its
hard associations.  At every one of nine symmetric local coordinates it
rebuilds the exact SGP4 support and profiles either:

* a rate-only baseline, or
* the same rates plus a common fractional Doppler scale and one shrinkage
  deviation per recording session.

The former failed iteration-6B used one large finite-difference L-BFGS-B
problem.  Here the rate parameters are conditionally independent after a
track CFO is profiled, so each is solved as a bounded scalar problem.  The
remaining six-session scale hierarchy is a seven-parameter analytic-gradient
problem.  Alternating these blocks gives a checkable convergence condition.

The reference coordinate is absent from this driver.  See evaluate_postseal.py
for the separate evaluation-only comparison.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize, minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER10 = ROOT / "reports/2026_09_24_ds1_iteration10_refinement/inference.json"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE_ROOT = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
GROUPS = ("20260921_00", "20260921_16")

# Fixed before looking at this arm's results.  The scale priors are the
# iteration-6B values.  A 2,000 ppm guard is intentionally much wider than
# either 500 ppm prior so a selected boundary solution is rejected.
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
COMMON_SCALE_SIGMA = 5e-4
SESSION_SCALE_SIGMA = 5e-4
SCALE_BOUND = 0.002
ROBUST_SCALE_HZ = 250.0
PRIOR_SELECTION_WEIGHT = 0.001
MAX_OUTER_ITERATIONS = 16
OUTER_OBJECTIVE_TOLERANCE = 1e-7
OUTER_PARAMETER_TOLERANCE = 2e-7
RATE_XATOL_S_H = 2e-7
LOCAL_SPACING_KM = 0.1953125


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def source_path(group: str) -> Path:
    return SOURCE_ROOT / f"one-hour--train-{group}--prefix-6--reno--global_time.json"


def source_task(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": "iteration12-" + str(source["task_id"]),
        "group_id": source["group_id"],
        "session_ids": source["session_ids"],
        "session_groups": source["session_groups"],
        "prior": source["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def load_iteration10(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("complete") is not True or value.get("reference_used_for_fit") is not False:
        raise ValueError("iteration-10 must be completed and reference-free")
    winner = value.get("winner", {})
    if set(winner.get("best_exact_by_group", {})) != set(GROUPS):
        raise ValueError("iteration-10 DS1 groups are incomplete")
    if not all(
        row["exact_comparison"]["exact_sgp4_gate"]["passed"]
        for row in winner["best_exact_by_group"].values()
    ):
        raise ValueError("iteration-10 exact gate failed")
    return value


def local_coordinate(origin: dict[str, float], east_km: float, north_km: float) -> dict[str, float]:
    latitude = float(origin["latitude_deg"]) + north_km / 111.32
    longitude = float(origin["longitude_deg"]) + east_km / (
        111.32 * math.cos(math.radians(float(origin["latitude_deg"])))
    )
    return {
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "east_km_from_iteration10": east_km,
        "north_km_from_iteration10": north_km,
    }


def lattice(origin: dict[str, float]) -> list[dict[str, float]]:
    return [
        local_coordinate(origin, east, north)
        for north in (-LOCAL_SPACING_KM, 0.0, LOCAL_SPACING_KM)
        for east in (-LOCAL_SPACING_KM, 0.0, LOCAL_SPACING_KM)
    ]


def _indices(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.unique(values.astype(str), return_inverse=True)


def _center(values: np.ndarray, track: np.ndarray, count: int) -> np.ndarray:
    means = np.bincount(track, weights=values, minlength=count) / np.bincount(
        track, minlength=count
    )
    return values - means[track]


def _capped_loss(
    error: np.ndarray, track: np.ndarray, names: np.ndarray, weights: dict[str, int]
) -> float:
    return float(
        sum(
            weights[str(name)]
            * min((float(np.sqrt(np.mean(error[track == index] ** 2))) / 800.0) ** 2, 1.0)
            for index, name in enumerate(names)
        )
        / sum(weights.values())
    )


def _smooth_loss(error: np.ndarray) -> float:
    z = error / ROBUST_SCALE_HZ
    return float(np.sum(np.sqrt(1.0 + z * z) - 1.0))


def _smooth_derivative(error: np.ndarray) -> np.ndarray:
    return error / (ROBUST_SCALE_HZ**2 * np.sqrt(1.0 + (error / ROBUST_SCALE_HZ) ** 2))


def _quartic_derivative(
    nodes: np.ndarray, phase_s: np.ndarray, knots: tuple[float, ...]
) -> np.ndarray:
    """Derivative of orbit.quartic's five-node Lagrange interpolation."""
    phase = np.asarray(phase_s, float)
    out = np.zeros((len(phase), 3), float)
    for index, knot in enumerate(knots):
        derivative = np.zeros(len(phase), float)
        others = [other for other in knots if other != knot]
        for omitted, _value in enumerate(others):
            term = np.ones(len(phase), float)
            for other_index, other in enumerate(others):
                if other_index != omitted:
                    term *= (phase - other) / (knot - other)
                else:
                    term /= knot - other
            derivative += term
        out += nodes[:, index] * derivative[:, None]
    return out


@dataclass
class ExactModel:
    data: Any
    receiver: np.ndarray
    search: Any
    orbit: Any
    source_names: np.ndarray
    source_index: np.ndarray
    session_names: np.ndarray
    session_index: np.ndarray
    track_names: np.ndarray
    track_index: np.ndarray

    @classmethod
    def build(cls, data: Any, receiver: np.ndarray, search: Any, orbit: Any) -> ExactModel:
        source_names, source_index = _indices(data.source)
        session_names, session_index = _indices(data.session)
        track_names, track_index = _indices(data.track)
        return cls(
            data=data,
            receiver=receiver,
            search=search,
            orbit=orbit,
            source_names=source_names,
            source_index=source_index,
            session_names=session_names,
            session_index=session_index,
            track_names=track_names,
            track_index=track_index,
        )

    def base(self, rates: np.ndarray) -> np.ndarray:
        phase = self.data.age_h * rates[self.source_index]
        return self.orbit.doppler(
            self.receiver,
            self.orbit.quartic(self.data.p_nodes, phase),
            self.orbit.quartic(self.data.v_nodes, phase),
            self.search,
        )

    def residual(
        self, rates: np.ndarray, scale: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        base = self.base(rates)
        multiplier = 1.0 + scale[0] + scale[1:][self.session_index]
        raw = self.data.y - multiplier * base
        return _center(raw, self.track_index, len(self.track_names)), base, raw

    def selection_objective(self, rates: np.ndarray, scale: np.ndarray) -> float:
        error, _base, _raw = self.residual(rates, scale)
        rate_prior = 0.5 * float(np.sum((rates / RATE_SIGMA_S_H) ** 2))
        scale_prior = 0.5 * (scale[0] / COMMON_SCALE_SIGMA) ** 2 + 0.5 * float(
            np.sum((scale[1:] / SESSION_SCALE_SIGMA) ** 2)
        )
        return _capped_loss(error, self.track_index, self.track_names, self.data.weights) + (
            PRIOR_SELECTION_WEIGHT * (rate_prior + scale_prior)
        )

    def capped_loss(self, rates: np.ndarray, scale: np.ndarray) -> float:
        error, _base, _raw = self.residual(rates, scale)
        return _capped_loss(error, self.track_index, self.track_names, self.data.weights)


def _fit_scales(
    model: ExactModel, rates: np.ndarray, initial: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    """Analytic-gradient, bounded scale block after profiling all track CFOs."""
    error_zero, base, _raw = model.residual(rates, np.zeros(1 + len(model.session_names)))
    columns = [base]
    columns.extend(
        base * (model.session_index == index) for index in range(len(model.session_names))
    )
    design = np.column_stack(
        [_center(column, model.track_index, len(model.track_names)) for column in columns]
    )
    prior_sigma = np.r_[COMMON_SCALE_SIGMA, np.full(len(model.session_names), SESSION_SCALE_SIGMA)]

    def objective(scale: np.ndarray) -> float:
        error = error_zero - design @ scale
        return _smooth_loss(error) + 0.5 * float(np.sum((scale / prior_sigma) ** 2))

    def gradient(scale: np.ndarray) -> np.ndarray:
        error = error_zero - design @ scale
        return -design.T @ _smooth_derivative(error) + scale / prior_sigma**2

    outcome = minimize(
        objective,
        initial,
        jac=gradient,
        method="L-BFGS-B",
        bounds=[(-SCALE_BOUND, SCALE_BOUND)] * len(initial),
        options={"maxiter": 200, "ftol": 1e-13, "gtol": 1e-8, "maxls": 100},
    )
    return np.asarray(outcome.x, float), {
        "converged": bool(outcome.success),
        "iterations": int(outcome.nit),
        "message": str(outcome.message),
        "smooth_objective": float(outcome.fun),
    }


def _fit_rates(model: ExactModel, scale: np.ndarray, initial: np.ndarray) -> tuple[np.ndarray, int]:
    """Conditionally independent bounded scalar rate fits, one per NORAD."""
    fitted = initial.copy()
    all_success = 0
    multiplier = 1.0 + scale[0] + scale[1:][model.session_index]
    for index, _source in enumerate(model.source_names):
        source_rows = model.source_index == index
        local_track_names, local_track_index = _indices(model.data.track[source_rows])

        def objective(
            rate: float,
            rows: np.ndarray = source_rows,
            track_index: np.ndarray = local_track_index,
            track_names: np.ndarray = local_track_names,
        ) -> float:
            phase = model.data.age_h[rows] * rate
            prediction = model.orbit.doppler(
                model.receiver,
                model.orbit.quartic(model.data.p_nodes[rows], phase),
                model.orbit.quartic(model.data.v_nodes[rows], phase),
                model.search,
            )
            error = model.data.y[rows] - multiplier[rows] * prediction
            centered = _center(error, track_index, len(track_names))
            return _smooth_loss(centered) + 0.5 * (rate / RATE_SIGMA_S_H) ** 2

        outcome = minimize_scalar(
            objective,
            bounds=(-RATE_BOUND_S_H, RATE_BOUND_S_H),
            method="bounded",
            options={"xatol": RATE_XATOL_S_H, "maxiter": 100},
        )
        fitted[index] = float(outcome.x)
        all_success += int(bool(outcome.success))
    return fitted, all_success


def fit(
    model: ExactModel, *, scales_enabled: bool, initial_scale: np.ndarray | None = None
) -> dict[str, Any]:
    """Alternating exact rate and scale blocks with a predeclared stop rule."""
    rates = np.zeros(len(model.source_names), float)
    scale = np.zeros(1 + len(model.session_names), float)
    if initial_scale is not None:
        if initial_scale.shape != scale.shape:
            raise ValueError("scale initialization has the wrong shape")
        scale = np.clip(initial_scale, -SCALE_BOUND, SCALE_BOUND)
    trace: list[dict[str, float | int | bool]] = []
    converged = False
    scale_ok = True
    for iteration in range(1, MAX_OUTER_ITERATIONS + 1):
        before = float(model.selection_objective(rates, scale))
        old_rates, old_scale = rates.copy(), scale.copy()
        rates, rate_successes = _fit_rates(model, scale, rates)
        if scales_enabled:
            scale, scale_result = _fit_scales(model, rates, scale)
            scale_ok = scale_ok and bool(scale_result["converged"])
        else:
            scale_result = {
                "converged": True,
                "iterations": 0,
                "message": "fixed zero",
                "smooth_objective": 0.0,
            }
            scale[:] = 0.0
        after = float(model.selection_objective(rates, scale))
        rate_step = float(np.max(np.abs(rates - old_rates)))
        scale_step = float(np.max(np.abs(scale - old_scale)))
        trace.append(
            {
                "iteration": iteration,
                "selection_objective": after,
                "objective_improvement": before - after,
                "maximum_rate_step_s_h": rate_step,
                "maximum_scale_step": scale_step,
                "rate_scalar_success_count": rate_successes,
                "scale_block_converged": bool(scale_result["converged"]),
                "scale_block_iterations": int(scale_result["iterations"]),
            }
        )
        if (
            abs(before - after) <= OUTER_OBJECTIVE_TOLERANCE
            and max(rate_step, scale_step) <= OUTER_PARAMETER_TOLERANCE
        ):
            converged = True
            break
    error, _base, raw = model.residual(rates, scale)
    cfo = np.bincount(
        model.track_index, weights=raw, minlength=len(model.track_names)
    ) / np.bincount(model.track_index, minlength=len(model.track_names))
    rate_prior = 0.5 * float(np.sum((rates / RATE_SIGMA_S_H) ** 2))
    scale_prior = 0.5 * (scale[0] / COMMON_SCALE_SIGMA) ** 2 + 0.5 * float(
        np.sum((scale[1:] / SESSION_SCALE_SIGMA) ** 2)
    )
    return {
        "converged": bool(converged and scale_ok),
        "outer_iterations": len(trace),
        "trace": trace,
        "selection_objective": float(model.selection_objective(rates, scale)),
        "exact_full_observation_capped_loss": _capped_loss(
            error, model.track_index, model.track_names, model.data.weights
        ),
        "rate_prior": rate_prior,
        "scale_prior": scale_prior,
        "rates_s_h": {
            str(name): float(value) for name, value in zip(model.source_names, rates, strict=True)
        },
        "common_scale": float(scale[0]),
        "session_deviations": {
            str(name): float(value)
            for name, value in zip(model.session_names, scale[1:], strict=True)
        },
        "scale_reaches_guard": bool(np.any(np.abs(scale) >= SCALE_BOUND - 1e-8)),
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND_S_H - 1e-8)),
        "track_cfo_hz": {
            str(name): float(value) for name, value in zip(model.track_names, cfo, strict=True)
        },
    }


def _prepared_model(
    group: str, point: dict[str, float], sealed_group: dict[str, Any]
) -> ExactModel:
    existing = load(RUNNER, f"i12_runner_{group}_{os.getpid()}")
    orbit = load(ORBIT, f"i12_orbit_{group}_{os.getpid()}")
    source = json.loads(source_path(group).read_text())
    engine = existing.FullObservationEngine(existing.validate_task(source_task(source)))
    prepared = existing._make_exact_prepared(
        engine,
        orbit,
        point["latitude_deg"],
        point["longitude_deg"],
        sealed_group["tau_s"],
        sealed_group["track_associations"],
    )
    receiver, _up = engine.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    return ExactModel.build(prepared, receiver, engine.search, orbit)


def audit(task: tuple[str, dict[str, float], dict[str, Any]]) -> dict[str, Any]:
    group, point, sealed_group = task
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    begun = time.perf_counter()
    model = _prepared_model(group, point, sealed_group)
    baseline = fit(model, scales_enabled=False)
    hierarchy = fit(model, scales_enabled=True)
    return {
        **point,
        "group_id": group,
        "tau_s": float(sealed_group["tau_s"]),
        "fixed_association_count": len(sealed_group["track_associations"]),
        "sample_count": len(model.data.y),
        "session_count": len(model.session_names),
        "source_count": len(model.source_names),
        "baseline_rate_only": baseline,
        "common_plus_session_scale": hierarchy,
        "scale_loss_delta_vs_matched_baseline": float(
            hierarchy["exact_full_observation_capped_loss"]
            - baseline["exact_full_observation_capped_loss"]
        ),
        "elapsed_s": time.perf_counter() - begun,
    }


def _joint_rows(audits: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    rows = []
    for north in (-LOCAL_SPACING_KM, 0.0, LOCAL_SPACING_KM):
        for east in (-LOCAL_SPACING_KM, 0.0, LOCAL_SPACING_KM):
            group_rows = [
                row
                for row in audits
                if row["east_km_from_iteration10"] == east
                and row["north_km_from_iteration10"] == north
            ]
            if len(group_rows) != len(GROUPS):
                raise ValueError("incomplete group coordinate")
            fits = [row[method] for row in sorted(group_rows, key=lambda row: row["group_id"])]
            rows.append(
                {
                    "east_km_from_iteration10": east,
                    "north_km_from_iteration10": north,
                    "latitude_deg": group_rows[0]["latitude_deg"],
                    "longitude_deg": group_rows[0]["longitude_deg"],
                    "balanced_selection_objective": 0.5
                    * sum(float(fit["selection_objective"]) for fit in fits),
                    "balanced_exact_capped_loss": 0.5
                    * sum(float(fit["exact_full_observation_capped_loss"]) for fit in fits),
                    "all_converged": bool(all(fit["converged"] for fit in fits)),
                    "all_scale_guards_clear": bool(
                        all(not fit["scale_reaches_guard"] for fit in fits)
                    ),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            row["balanced_selection_objective"],
            row["north_km_from_iteration10"],
            row["east_km_from_iteration10"],
        ),
    )


def initialization_sensitivity(
    group: str, point: dict[str, float], sealed_group: dict[str, Any]
) -> dict[str, Any]:
    """Two opposite 400-ppm starts verify the selected fit's scale basin."""
    model = _prepared_model(group, point, sealed_group)
    initial = np.full(1 + len(model.session_names), 4e-4)
    negative = fit(model, scales_enabled=True, initial_scale=-initial)
    positive = fit(model, scales_enabled=True, initial_scale=initial)
    return {
        "group_id": group,
        "negative_start": negative,
        "positive_start": positive,
        "selection_objective_difference": abs(
            negative["selection_objective"] - positive["selection_objective"]
        ),
        "capped_loss_difference": abs(
            negative["exact_full_observation_capped_loss"]
            - positive["exact_full_observation_capped_loss"]
        ),
        "common_scale_difference": abs(negative["common_scale"] - positive["common_scale"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration10", type=Path, default=ITER10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise ValueError("output exists or workers must be 1..4")
    sealed = load_iteration10(args.iteration10)
    origin = {name: float(sealed["winner"][name]) for name in ("latitude_deg", "longitude_deg")}
    points = lattice(origin)
    sealed_groups = sealed["winner"]["best_exact_by_group"]
    begun = time.perf_counter()
    tasks = [(group, point, sealed_groups[group]) for point in points for group in GROUPS]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=args.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        audits = list(pool.map(audit, tasks, chunksize=1))
    baseline_rows = _joint_rows(audits, "baseline_rate_only")
    hierarchy_rows = _joint_rows(audits, "common_plus_session_scale")
    winner = hierarchy_rows[0]
    selected_audits = [
        row
        for row in audits
        if row["east_km_from_iteration10"] == winner["east_km_from_iteration10"]
        and row["north_km_from_iteration10"] == winner["north_km_from_iteration10"]
    ]
    sensitivity = [
        initialization_sensitivity(row["group_id"], winner, sealed_groups[row["group_id"]])
        for row in selected_audits
    ]
    portability = bool(
        winner["all_converged"]
        and winner["all_scale_guards_clear"]
        and all(
            row["common_plus_session_scale"]["exact_full_observation_capped_loss"]
            <= row["baseline_rate_only"]["exact_full_observation_capped_loss"] + 1e-12
            for row in selected_audits
        )
        and all(item["selection_objective_difference"] <= 1e-6 for item in sensitivity)
    )
    result = {
        "schema": "ds1-iteration12-converged-session-scale/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "observation_policy": "all_qualified_observations in frozen iteration-10 supports",
        "iteration10_input": {"path": str(args.iteration10), "sha256": digest(args.iteration10)},
        "origin": origin,
        "coordinate_policy": "symmetric 3x3 exact lattice around sealed iteration-10 winner",
        "fixed_group_taus_s": {group: sealed_groups[group]["tau_s"] for group in GROUPS},
        "association_policy": (
            "iteration-10 selected hard associations fixed for matched local ablation"
        ),
        "model": {
            "rate_sigma_s_h": RATE_SIGMA_S_H,
            "rate_bound_s_h": RATE_BOUND_S_H,
            "common_scale_sigma": COMMON_SCALE_SIGMA,
            "session_scale_sigma": SESSION_SCALE_SIGMA,
            "scale_guard": SCALE_BOUND,
            "robust_scale_hz": ROBUST_SCALE_HZ,
            "prior_selection_weight": PRIOR_SELECTION_WEIGHT,
            "max_outer_iterations": MAX_OUTER_ITERATIONS,
            "outer_objective_tolerance": OUTER_OBJECTIVE_TOLERANCE,
            "outer_parameter_tolerance": OUTER_PARAMETER_TOLERANCE,
        },
        "baseline_rate_only_rows": baseline_rows,
        "common_plus_session_scale_rows": hierarchy_rows,
        "winner": winner,
        "selected_group_audits": selected_audits,
        "initialization_sensitivity": sensitivity,
        "portability_accepted": portability,
        "portability_rule": (
            "selected hierarchy coordinate converges for both groups, clears every scale guard, "
            "does not worsen either matched baseline capped loss, and opposite 400-ppm starts "
            "agree within 1e-6 on selection objective"
        ),
        "workers": args.workers,
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {
            "driver": digest(Path(__file__)),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "elapsed_s": result["elapsed_s"],
                "portable": portability,
                "winner": winner,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
