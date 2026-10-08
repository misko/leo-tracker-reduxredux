"""Development prototype: shrink RX-specific RF slope differences toward zero."""

import time
from contextlib import suppress

import numpy as np
from scipy.optimize import Bounds, minimize

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem
from leo.analysis.hard60_score import Hard60Objective, likelihood, predict_orbits

VARIANTS = {"rx-rf-50": 50.0, "rx-rf-150": 150.0, "rx-rf-500": 500.0}


class ReceiverRFObjective(Hard60Objective):
    def __init__(self, base, sigma):
        super().__init__(
            base.observations, base.bank, base.prior, base.score, receiver_baseline_hz=base.baseline
        )
        self.sigma = sigma
        # c0 = c - d/2, c1 = c + d/2, both in Hz/GHz.
        self.differential = self.design[:, 4] * (self.observations.receiver - 0.5)

    def evaluate_extended(self, vector, difference):
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline + self.differential * difference)[
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
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * (difference / self.sigma) ** 2
        derivative = self.differential @ weight.sum(axis=1) + difference / self.sigma**2
        return terms.nll + penalty, gradient, derivative, terms


def fit(base, seed, *, sigma, arm, maximum_seconds=20, maximum_iterations=600):
    begun = time.monotonic()
    objective = ReceiverRFObjective(base, sigma)
    problem = _Problem(
        objective,
        seed,
        rf_arm=arm,
        slope_half_width_hz_s=60,
        local_center=np.asarray(seed[:2]),
        local_radius_km=25,
    )
    initial, lower, upper, matrix, constant = _parameterization(problem)
    dimension, count, scale = len(initial), len(base.bank.numbers), 200.0
    initial = np.r_[initial, 0.0]
    # The matched zero-c arm disables BOTH shared and differential RF terms.
    bound = 0.0 if arm == "zero-c" else 25.0
    lower, upper = np.r_[lower, -bound], np.r_[upper, bound]
    records = []

    class Deadline(Exception):
        pass

    def physical(z):
        return constant + matrix @ z[:dimension], z[-1] * scale

    def evaluate(z):
        if time.monotonic() - begun > maximum_seconds:
            raise Deadline()
        vector, difference = physical(z)
        value, gradient, derivative, _ = objective.evaluate_extended(vector, difference)
        if problem.feasible(vector):
            records.append((value, vector.copy(), difference, gradient.copy(), derivative))
        return value, np.r_[matrix.T @ gradient, scale * derivative]

    def constraints(z):
        v, _ = physical(z)
        return np.r_[v[7] + 10, 10 - v[7], problem.constraints(v)[2 * count :]]

    def jac(z):
        v, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(v)[2 * count :] @ matrix])
        return np.column_stack([core, np.zeros(len(core))])

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
        _, vector, difference, gradient, derivative = row
        extra = scale * derivative
        if (
            arm == "zero-c"
            or (difference <= -5000 + 1e-7 and extra >= 0)
            or (difference >= 5000 - 1e-7 and extra <= 0)
        ):
            extra = 0.0
        return max(problem.stationarity(vector, gradient), abs(extra))

    accepted = []
    for row in records:
        if arm == "zero-c" or abs(scale * row[4]) <= 0.001 or abs(row[2]) >= 5000 - 1e-7:
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
    value, vector, difference, _, _ = row
    _, _, _, terms = objective.evaluate_extended(vector, difference)
    mass = terms.responsibilities.sum()
    return dict(
        vector=vector,
        difference_hz_per_ghz=difference,
        objective=float(value),
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
