"""Reference-free B7 stages, with independently qualified per-arm fallbacks."""

import time
from dataclasses import replace

import numpy as np

from leo.analysis.hard60_dynamic_rf import DynamicRFObjective
from leo.analysis.hard60_dynamic_rf import fit as rf_fit
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_joint_clock import fit as timing_fit
from leo.analysis.hard60_joint_initial import JointClockObjective as InitialClockObjective
from leo.analysis.hard60_joint_initial import fit as initial_fit
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.hard60_slope_prior import SlopePrior
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration, run_hard60
from leo.application.regional_position_runner import RegionalSliceExpired, json_value
from leo.contracts.digests import canonical_digest

ARMS = ("fitted-c", "zero-c")
B7_POLICY = dict(
    policy="hard60-b7-v1",
    regional_separations_km=[12.5, 25.0, 50.0],
    relative_timing_prune_s=5.0,
    minimum_satellites=4,
    clock_prior_scales=[2.0, 4.0],
    rf_time_sigma=50.0,
    satellite_slope_sigma_hz_s=0.5,
    maximum_seconds=90.0,
    maximum_iterations=600,
    stationarity_threshold=0.001,
    local_radius_km=25.0,
    stages=["B3", "B4", "B4W", "B5", "C6", "B7"],
)


def regional_winners(regions):
    """Strict improvement preserves original winners on score ties."""
    winners = {}
    for arm in ARMS:
        for source, result in regions.items():
            eligible = [
                r
                for r in result["finals"]
                if r["arm"] == arm and r["fit"] and r["fit"]["converged"]
            ]
            if not eligible:
                continue
            best = min(
                eligible,
                key=lambda r: (
                    r["fit"]["objective"] + r["calibration_penalty"],
                    r["basin"],
                    r["start"],
                ),
            )
            if arm not in winners or (
                best["fit"]["objective"] + best["calibration_penalty"]
                < winners[arm]["fit"]["objective"] + winners[arm]["calibration_penalty"]
            ):
                winners[arm] = dict(best, region_source=source, accepted_stage="B1")
    return winners


def reduce_bank(base, seed):
    relative = base.basis @ seed[8:]
    keep = np.flatnonzero(abs(relative) <= 5)
    if len(keep) < 4:
        raise ValueError("insufficient candidates after timing gate")
    subset = Hard60Objective(
        base.observations,
        base.bank.select(keep),
        base.prior,
        base.score,
        receiver_baseline_hz=base.baseline,
    )
    shifts = (seed[7] + relative)[keep]
    projected = np.r_[seed[:7], shifts.mean(), subset.basis.T @ (shifts - shifts.mean())]
    return subset, projected, base.bank.numbers[abs(relative) > 5].tolist()


def run_joint_stages(observations, bank, prior, regions, stage):
    """Accept by convergence within a stage, never compare different model scores."""
    operational = regional_winners(regions)
    attempts, reasons = {}, []
    if "fitted-c" not in operational:
        return operational, attempts, ["no-qualified-fitted-regional-start"]
    original = operational["fitted-c"]
    calibration = regions[original["region_source"]]["calibrations"][original["basin"]]
    lookup = {int(n): i for i, n in enumerate(bank.numbers)}
    base = Hard60Objective(
        observations,
        bank.select([lookup[n] for n in original["satellites"]]),
        prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    seed = np.asarray(original["fit"]["vector"])
    if not np.isclose(base.evaluate(seed)[0], original["fit"]["objective"], atol=1e-6, rtol=0):
        raise ValueError("regional start objective differs from its physical model")
    correction = calibration["correction"]
    nodes, knots = correction["nodes_s"], correction["knots_hz"]

    def run(name, model, seed, clock, fitter):
        rows = {}
        for arm in ARMS:

            def compute(arm=arm):
                options = dict(arm=arm, maximum_seconds=90, maximum_iterations=600)
                if clock is not None:
                    options["clock_seed"] = np.asarray(clock).copy()
                fit = json_value(fitter(model, np.asarray(seed).copy(), **options))
                vector, coefficients = (
                    np.asarray(fit["vector"]),
                    np.asarray(fit["clock_coefficients"]),
                )
                total, _, _, terms = model.evaluate_joint(vector, coefficients)
                relative = model.basis @ vector[8:]
                timing = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
                timing += 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
                nuisance = 0.5 * coefficients @ model.precision @ coefficients
                offsets, slopes = (
                    model.physical_corrections(coefficients)
                    if isinstance(model, SlopePrior)
                    else ([], [])
                )
                fit["joint_state"] = json_value(
                    dict(
                        stage=name,
                        vector=vector,
                        clock_coefficients=coefficients,
                        clock_nodes_s=nodes,
                        clock_knots_hz=fit["knots_hz"],
                        receiver_baseline_hz=model.baseline,
                        rf_time_coefficients=fit.get("rf_drift_coefficients", [0.0, 0.0]),
                        satellite_centers_s=getattr(model, "centers_s", []),
                        satellite_offsets_hz=offsets,
                        satellite_slopes_hz_s=slopes,
                        likelihood_nll=terms.nll,
                        timing_penalty=timing,
                        nuisance_penalty=nuisance,
                        total_objective=total,
                    )
                )
                fit["boundary"] = fit["physical_constraints_minimum"] < 1e-5
                fit["stop_reason"] = (
                    "joint-stationary" if fit["converged"] else "joint-nonstationary"
                )
                return fit

            receipt = stage(f"b7:{name}:{arm}", 90, compute)
            fit = receipt["result"]
            rows[arm] = fit
            if fit is not None and fit["converged"]:
                operational[arm] = dict(
                    original,
                    arm=arm,
                    fit=fit,
                    start=name,
                    accepted_stage=name,
                    calibration_penalty=0.0,
                    satellites=model.bank.numbers.tolist(),
                )
            else:
                reasons.append(f"{name}:{arm}:" + (receipt["reason"] or "nonstationary"))
        attempts[name] = rows
        return rows

    joint = run("B3", InitialClockObjective(base, nodes, knots, 2), seed, None, initial_fit)
    if not joint["fitted-c"] or not joint["fitted-c"]["converged"]:
        return operational, attempts, reasons
    chosen = joint["fitted-c"]
    try:
        subset, seed, removed = reduce_bank(base, np.asarray(chosen["vector"]))
    except ValueError as error:
        return operational, attempts, reasons + [str(error)]
    pruned = run(
        "B4",
        JointClockObjective(subset, nodes, knots, 2),
        seed,
        chosen["clock_coefficients"],
        timing_fit,
    )
    if not pruned["fitted-c"] or not pruned["fitted-c"]["converged"]:
        return operational, attempts, reasons
    chosen = pruned["fitted-c"]
    wide = run(
        "B4W",
        JointClockObjective(subset, nodes, knots, 4),
        np.asarray(chosen["vector"]),
        chosen["clock_coefficients"],
        timing_fit,
    )
    if wide["fitted-c"] and wide["fitted-c"]["converged"]:
        chosen = wide["fitted-c"]
    seed, clock = np.asarray(chosen["vector"]), np.r_[chosen["clock_coefficients"], 0.0, 0.0]
    dynamic = run("B5", DynamicRFObjective(subset, nodes, knots, 50), seed, clock, rf_fit)
    if dynamic["fitted-c"] and dynamic["fitted-c"]["converged"]:
        seed, clock = (
            np.asarray(dynamic["fitted-c"]["vector"]),
            np.asarray(dynamic["fitted-c"]["clock_coefficients"]),
        )
    control = DynamicRFObjective(subset, nodes, knots, 50)
    _, _, _, terms = control.evaluate_joint(seed, clock)
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ observations.times_s,
        mass,
        out=np.full(len(mass), observations.time_center_s),
        where=mass > 1e-12,
    )
    # C6 is retained because it is the frozen B7 fallback, not an optional study row.
    run("C6", control, seed, clock, rf_fit)
    model = SlopePrior(subset, nodes, knots, centers, 0.5)
    run("B7", model, seed, model.expand_clock(clock), rf_fit)
    attempts["removed_satellites"] = removed
    return operational, attempts, reasons


class SharedPoints:
    """Only basin-independent coarse point receipts are shared across region passes."""

    def __init__(self, checkpoints):
        self.checkpoints = checkpoints

    def key(self, key):
        # Digest contains a colon; suffix after the digest is the stage name.
        suffix = key.split(":", 2)[2]
        return (
            "b7-shared:" + suffix if suffix.startswith("point:") and suffix.count(":") == 2 else key
        )

    def get(self, key):
        return self.checkpoints.get(self.key(key))

    def put(self, key, value):
        self.checkpoints.put(self.key(key), value)


def run_b7(observations, bank, prior, tracks, checkpoints, *, maximum_seconds=500):
    deadline = time.monotonic() + maximum_seconds
    binding = canonical_digest(B7_POLICY)

    def stage(key, budget, operation):
        key = binding + ":" + key
        cached = checkpoints.get(key)
        if cached is not None:
            return cached
        if time.monotonic() + budget >= deadline:
            raise RegionalSliceExpired(key)
        try:
            receipt = dict(result=json_value(operation()), reason=None)
        except (ValueError, TimeoutError) as error:
            receipt = dict(result=None, reason=f"{type(error).__name__}: {error}")
        checkpoints.put(key, receipt)
        return receipt

    regions = {}
    for name, separation in zip(("baseline", "sep25", "sep50"), (12.5, 25.0, 50.0), strict=True):
        config = replace(Hard60Configuration(), basin_separation_km=separation)
        regions[name] = run_hard60(
            observations,
            bank,
            prior,
            tracks,
            SharedPoints(checkpoints),
            configuration=config,
            maximum_seconds=max(0.001, deadline - time.monotonic()),
        )
    operational, attempts, reasons = run_joint_stages(observations, bank, prior, regions, stage)
    result = dict(regions["baseline"])
    result["finals"] = list(operational.values())
    result["failures"] = [dict(reason=r) for r in reasons]
    result["b7"] = dict(
        policy=B7_POLICY,
        attempts=attempts,
        regional_sources={a: r["region_source"] for a, r in operational.items()},
        accepted_stages={a: r["accepted_stage"] for a, r in operational.items()},
        regional_failures={k: r["failures"] for k, r in regions.items()},
    )
    return result
