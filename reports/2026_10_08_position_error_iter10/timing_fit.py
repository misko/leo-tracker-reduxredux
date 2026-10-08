"""Research joint fitter with an optional total satellite-timing bound."""

import time
from contextlib import suppress

import numpy as np
from scipy.optimize import Bounds, minimize

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem
from leo.analysis.hard60_score import Hard60Objective, likelihood, predict_orbits

VARIANTS = {"joint-tight": 0.5, "joint-original": 1.0, "joint-wide": 2.0}


class JointClockObjective(Hard60Objective):
    def __init__(self, base, nodes, knots, prior_scale=1):
        nodes, knots = np.asarray(nodes), np.asarray(knots)
        centered = nodes - nodes.mean()
        null = np.linalg.svd(
            np.stack([np.ones(len(nodes)), centered / max(abs(centered))]), full_matrices=True
        )[2][2:].T
        interpolation = np.column_stack(
            [np.interp(base.observations.times_s, nodes, row) for row in np.eye(len(nodes))]
        )
        core = interpolation @ null
        rx = base.observations.receiver
        old_values = np.sum(interpolation * knots[rx], axis=1)
        super().__init__(
            base.observations,
            base.bank,
            base.prior,
            base.score,
            receiver_baseline_hz=base.baseline - old_values,
        )
        self.clock_design = np.column_stack([core * (rx == r)[:, None] for r in (0, 1)])
        self.null, self.nodes = null, nodes
        self.initial_clock = (knots @ null).ravel()
        second = np.diff(np.eye(len(nodes)), n=2, axis=0) @ null
        precision = (np.eye(null.shape[1]) / 50**2 + second.T @ second / 25**2) / prior_scale**2
        self.precision = np.kron(np.eye(2), precision)
        np.testing.assert_allclose(self.clock_design @ self.initial_clock, old_values, atol=1e-7)

    def evaluate_joint(self, vector, clock):
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.clock_design @ clock)[
            :, None
        ]
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
        weight = terms.prediction_gradient
        shift = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        clock_gradient = self.clock_design.T @ weight.sum(axis=1) + self.precision @ clock
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * clock @ self.precision @ clock
        return terms.nll + penalty, gradient, clock_gradient, terms


def fit(
    objective,
    seed,
    *,
    arm,
    maximum_seconds=20,
    maximum_iterations=600,
    timing_half_width_s=20,
    fixed_position=False,
    clock_seed=None,
):
    begun = time.monotonic()
    problem = _Problem(
        objective,
        seed,
        rf_arm=arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=60,
        local_center=np.asarray(seed[:2]),
        local_radius_km=25,
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
        if problem.feasible(vector):
            records.append(
                (value, vector.copy(), clock.copy(), gradient.copy(), clock_gradient.copy())
            )
        return value, np.r_[matrix.T @ gradient, scale * clock_gradient]

    def constraints(z):
        v, _ = physical(z)
        return np.r_[v[7] + 10, 10 - v[7], problem.constraints(v)[2 * count :]]

    def jac(z):
        v, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(v)[2 * count :] @ matrix])
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
        g = scale * clock_gradient.copy()
        g[(clock <= -2000 + 1e-7) & (g >= 0)] = 0
        g[(clock >= 2000 - 1e-7) & (g <= 0)] = 0
        return max(problem.stationarity(vector, gradient), float(np.max(abs(g))))

    accepted = []
    for row in records:
        if np.max(abs(scale * row[4])) <= 0.001 or np.max(abs(row[2])) >= 2000 - 1e-7:
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
    knots = clock.reshape(2, -1) @ objective.null.T
    return dict(
        vector=vector,
        clock_coefficients=clock,
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
    )
