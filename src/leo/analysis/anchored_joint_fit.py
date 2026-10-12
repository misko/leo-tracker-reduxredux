"""Joint fitting with a fixed geographic domain independent of initialization.

This preserves the existing RF/clock solver, priors, physical constraints and
stationarity audit while permitting a feasible state from another mark model
to initialize the same original local disk. Published fitter sources remain
unchanged so prior scientific protocols continue to bind their exact bytes.
"""

import time
from contextlib import suppress

import numpy as np
from scipy.optimize import Bounds, minimize

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem


def fit_anchored_joint(
    objective,
    seed,
    *,
    arm,
    local_center,
    local_radius_km=25.0,
    maximum_seconds=20,
    maximum_iterations=600,
    timing_half_width_s=20,
    fixed_position=False,
    clock_seed=None,
):
    """Refine in the declared original disk; do not recenter around the seed."""
    if (
        not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= 1800
        or maximum_iterations < 1
    ):
        raise ValueError("invalid anchored fit budget")
    begun = time.monotonic()
    problem = _Problem(
        objective,
        seed,
        rf_arm=arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=60,
        local_center=local_center,
        local_radius_km=local_radius_km,
    )
    if not np.isfinite(timing_half_width_s) or not 0 < timing_half_width_s <= 20:
        raise ValueError("invalid timing bound")
    problem.minimum = max(problem.minimum, -timing_half_width_s)
    problem.maximum = min(problem.maximum, timing_half_width_s)
    shifts = np.clip(problem.matrix @ problem.start, problem.minimum + 1e-9, problem.maximum - 1e-9)
    problem.start[7] = shifts.mean()
    problem.start[8:] = objective.basis.T @ (shifts - shifts.mean())
    initial, lower, upper, matrix, constant = _parameterization(problem)
    dimension, count, extra, scale = (
        len(initial),
        len(objective.bank.numbers),
        len(objective.initial_clock),
        50.0,
    )
    clock_start = objective.initial_clock if clock_seed is None else np.asarray(clock_seed, float)
    if (
        clock_start.shape != objective.initial_clock.shape
        or not np.isfinite(clock_start).all()
        or np.max(abs(clock_start)) > 2000
    ):
        raise ValueError("invalid clock seed")
    initial = np.r_[initial, clock_start / scale]
    lower, upper = np.r_[lower, np.full(extra, -40.0)], np.r_[upper, np.full(extra, 40.0)]
    locked_rf = arm == "zero-c" or objective.fixed_rf_drift
    lower[-2:], upper[-2:] = (0.0, 0.0) if locked_rf else (-20.0, 20.0)
    if locked_rf:
        initial[-2:] = 0.0
    else:
        initial[-2:] = np.clip(initial[-2:], -20, 20)
    records = []

    class Deadline(Exception):
        pass

    def physical(z):
        return constant + matrix @ z[:dimension], z[dimension:] * scale

    def evaluate(z):
        if time.monotonic() - begun > maximum_seconds:
            raise Deadline()
        vector, clock = physical(z)
        value, gradient, clock_gradient, _ = objective.evaluate_joint(vector, clock)
        if locked_rf:
            clock_gradient[-2:] = 0.0
        if problem.feasible(vector):
            records.append(
                (value, vector.copy(), clock.copy(), gradient.copy(), clock_gradient.copy())
            )
        return value, np.r_[matrix.T @ gradient, scale * clock_gradient]

    def constraints(z):
        vector, _ = physical(z)
        return np.r_[vector[7] + 10, 10 - vector[7], problem.constraints(vector)[2 * count :]]

    def jac(z):
        vector, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(vector)[2 * count :] @ matrix])
        return np.column_stack([core, np.zeros((len(core), extra))])

    result = None
    with suppress(Deadline):
        result = minimize(
            evaluate,
            initial,
            jac=True,
            method="SLSQP",
            bounds=Bounds(lower, upper),
            constraints={"type": "ineq", "fun": constraints, "jac": jac},
            options={"maxiter": maximum_iterations, "ftol": 1e-11},
        )
    if not records:
        raise TimeoutError("no feasible evaluation")

    def stationarity(row):
        _, vector, clock, gradient, clock_gradient = row
        gradient_clock = scale * clock_gradient.copy()
        gradient_clock[(clock <= scale * lower[dimension:] + 1e-7) & (gradient_clock >= 0)] = 0
        gradient_clock[(clock >= scale * upper[dimension:] - 1e-7) & (gradient_clock <= 0)] = 0
        return max(problem.stationarity(vector, gradient), float(np.max(abs(gradient_clock))))

    accepted = []
    for row in records:
        if np.max(abs(scale * row[4])) <= 0.001 or np.any(
            (row[2] <= scale * lower[dimension:] + 1e-7)
            | (row[2] >= scale * upper[dimension:] - 1e-7)
        ):
            kkt = stationarity(row)
            if kkt <= 0.001:
                accepted.append((row, kkt))
    row, kkt = (
        min(accepted, key=lambda pair: pair[0][0])
        if accepted
        else (min(records, key=lambda row: row[0]), None)
    )
    if kkt is None:
        kkt = stationarity(row)
    value, vector, clock, _, _ = row
    _, _, _, terms = objective.evaluate_joint(vector, clock)
    mass = terms.responsibilities.sum()
    knots = clock[: objective.smooth_clock_count].reshape(2, -1) @ objective.null.T
    return dict(
        vector=vector,
        clock_coefficients=clock,
        smooth_clock_coefficients=clock[: objective.smooth_clock_count],
        rf_drift_coefficients=clock[-2:],
        rf_drift_penalty=float(0.5 * clock[-2:] @ objective.precision[-2:, -2:] @ clock[-2:]),
        knots_hz=knots,
        objective=float(value),
        calibration_penalty=float(0.5 * clock @ objective.precision @ clock),
        stationarity=kkt,
        converged=kkt <= 0.001,
        posterior_rms_hz=float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        ),
        signal_windows=float(mass),
        elapsed_s=time.monotonic() - begun,
        evaluations=len(records),
        solver_success=bool(result is not None and result.success),
        physical_constraints_minimum=float(problem.constraints(vector).min()),
        local_center_km=np.asarray(local_center, float).copy(),
        local_radius_km=float(local_radius_km),
        initial_objective=float(records[0][0]),
        best_feasible_objective=float(min(row[0] for row in records)),
    )
