"""Prototype a regularized per-satellite frequency offset alongside orbit timing.

Offsets are hypotheses for unexplained satellite-specific frequency bias, not
claims that a particular satellite clock is wrong. No reference location is used.
"""

import time
from contextlib import suppress
from dataclasses import replace

import numpy as np
from scipy.optimize import Bounds, minimize

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem
from leo.analysis.hard60_score import Hard60Objective, likelihood, predict_orbits


class BiasObjective(Hard60Objective):
    def __init__(self, base, sigma_hz):
        super().__init__(
            base.observations,
            base.bank,
            base.prior,
            base.score,
            receiver_baseline_hz=base.baseline,
        )
        self.bias_sigma_hz = sigma_hz

    def evaluate_bias(self, vector, bias):
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline)[:, None] + bias[None, :]
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
        weight = terms.prediction_gradient
        shift_gradient = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift_gradient.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative / self.score.relative_sigma_s**2)
        bias_gradient = weight.sum(axis=0) + bias / self.bias_sigma_hz**2
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * np.sum((bias / self.bias_sigma_hz) ** 2)
        return terms.nll + float(penalty), gradient, bias_gradient, terms


VARIANTS = {
    "satellite-bias-50": {"bias_sigma_hz": 50.0, "relative_sigma_s": 2.0},
    "satellite-bias-150": {"bias_sigma_hz": 150.0, "relative_sigma_s": 2.0},
    "satellite-bias-150-tight-timing": {"bias_sigma_hz": 150.0, "relative_sigma_s": 0.25},
}


def fit(base, seed, *, variant, arm, maximum_seconds=20.0, maximum_iterations=600):
    spec = VARIANTS[variant]
    begun = time.monotonic()
    objective = BiasObjective(base, spec["bias_sigma_hz"])
    objective.score = replace(base.score, relative_sigma_s=spec["relative_sigma_s"])
    problem = _Problem(
        objective,
        seed,
        rf_arm=arm,
        slope_half_width_hz_s=60,
        local_center=np.asarray(seed[:2]),
        local_radius_km=25,
    )
    initial, lower, upper, matrix, constant = _parameterization(problem)
    dimension, count, scale = len(initial), len(base.bank.numbers), 100.0
    initial = np.r_[initial, np.zeros(count)]
    lower, upper = np.r_[lower, np.full(count, -20.0)], np.r_[upper, np.full(count, 20.0)]
    records = []

    class Deadline(Exception):
        pass

    def physical(z):
        return constant + matrix @ z[:dimension], z[dimension:] * scale

    def evaluate(z):
        if time.monotonic() - begun > maximum_seconds:
            raise Deadline()
        vector, bias = physical(z)
        value, gradient, bias_gradient, terms = objective.evaluate_bias(vector, bias)
        if problem.feasible(vector):
            records.append(
                (value, vector.copy(), bias.copy(), gradient.copy(), bias_gradient.copy())
            )
        return value, np.r_[matrix.T @ gradient, scale * bias_gradient]

    def constraints(z):
        v, _ = physical(z)
        return np.r_[v[7] + 10, 10 - v[7], problem.constraints(v)[2 * count :]]

    def constraint_jac(z):
        v, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(v)[2 * count :] @ matrix])
        return np.column_stack([core, np.zeros((len(core), count))])

    result = None
    with suppress(Deadline):
        result = minimize(
            evaluate,
            initial,
            jac=True,
            method="SLSQP",
            bounds=Bounds(lower, upper),
            constraints={"type": "ineq", "fun": constraints, "jac": constraint_jac},
            options={"maxiter": maximum_iterations, "ftol": 1e-11},
        )
    if not records:
        raise TimeoutError("no feasible evaluation")

    def stationarity(row):
        _, vector, bias, gradient, bias_gradient = row
        g = scale * bias_gradient.copy()
        g[(bias <= -2000 + 1e-7) & (g >= 0)] = 0
        g[(bias >= 2000 - 1e-7) & (g <= 0)] = 0
        return max(problem.stationarity(vector, gradient), float(np.max(abs(g))))

    # Audit candidates with small free-bias gradient first; the original physical
    # KKT constraints remain the independent authority for the position/timing fit.
    accepted = []
    for row in records:
        if np.max(abs(row[4] * scale)) <= 0.001 or np.max(abs(row[2])) >= 2000 - 1e-7:
            kkt = stationarity(row)
            if kkt <= 0.001:
                accepted.append((row, kkt))
    selected, kkt = (
        min(accepted, key=lambda pair: pair[0][0])
        if accepted
        else (min(records, key=lambda row: row[0]), None)
    )
    if kkt is None:
        kkt = stationarity(selected)
    value, vector, bias, _, _ = selected
    _, _, _, terms = objective.evaluate_bias(vector, bias)
    mass = terms.responsibilities.sum()
    return {
        "variant": variant,
        "arm": arm,
        "vector": vector,
        "bias_hz": bias,
        "objective": value,
        "stationarity": kkt,
        "converged": kkt <= 0.001,
        "posterior_rms_hz": float(
            np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass)
        ),
        "signal_windows": float(mass),
        "elapsed_s": time.monotonic() - begun,
        "evaluations": len(records),
        "solver_success": bool(result is not None and result.success),
        "solver_status": int(result.status) if result is not None else "time-budget",
        "physical_constraints_minimum": float(problem.constraints(vector).min()),
    }
