"""Hard60 recovery with satellite timing shifts as directly bounded variables."""

import time

import numpy as np
from scipy.optimize import Bounds, minimize, nnls

from leo.analysis.regional_position_fit import PositionFit


class _Deadline(Exception):
    pass


class _Problem:
    """Physical constraints and the original scaled KKT audit, independent of solver."""

    def __init__(
        self,
        objective,
        start,
        *,
        rf_arm="fitted-c",
        fixed_position=False,
        local_center=None,
        local_radius_km=None,
        slope_half_width_hz_s=60,
    ):
        self.objective = objective
        self.start = np.asarray(start, float).copy()
        if self.start.shape != (objective.size,) or not np.isfinite(self.start).all():
            raise ValueError("invalid starting vector")
        if np.linalg.norm(self.start[:2]) > objective.prior.radius_km + 1e-9:
            raise ValueError("starting point is outside prior")
        if not np.isfinite(slope_half_width_hz_s) or slope_half_width_hz_s <= 0:
            raise ValueError("invalid slope bound")
        if (local_center is None) != (local_radius_km is None):
            raise ValueError("local center and radius must be supplied together")
        if local_center is not None and (
            np.asarray(local_center).shape != (2,)
            or not np.isfinite(local_center).all()
            or not np.isfinite(local_radius_km)
            or local_radius_km <= 0
        ):
            raise ValueError("invalid local search disk")
        self.scales = np.r_[1, 1, 200, 2, 200, 2, 200, np.ones(objective.size - 7)]
        self.lower = np.full(objective.size, -np.inf)
        self.upper = np.full(objective.size, np.inf)
        self.lower[:2], self.upper[:2] = -objective.prior.radius_km, objective.prior.radius_km
        self.lower[[3, 5]], self.upper[[3, 5]] = -slope_half_width_hz_s, slope_half_width_hz_s
        self.lower[6], self.upper[6] = -5000, 5000
        self.lower[7], self.upper[7] = -10, 10
        if fixed_position:
            self.lower[:2] = self.upper[:2] = self.start[:2]
        if rf_arm == "zero-c":
            self.lower[6] = self.upper[6] = self.start[6] = 0
        elif rf_arm != "fitted-c":
            raise ValueError("unknown RF arm")
        self.start = np.clip(self.start, self.lower, self.upper)
        self.matrix = np.zeros((len(objective.bank.numbers), objective.size))
        self.matrix[:, 7], self.matrix[:, 8:] = 1, objective.basis
        self.coverage_min = float(objective.bank.nodes_s[0] - objective.observations.times_s.min())
        self.coverage_max = float(objective.bank.nodes_s[-1] - objective.observations.times_s.max())
        self.minimum, self.maximum = max(-20.0, self.coverage_min), min(20.0, self.coverage_max)
        if not self.coverage_min < self.minimum < 0 < self.maximum < self.coverage_max:
            raise ValueError("bounded timing requires an orbit interpolation margin")
        shifts = self.matrix @ self.start
        self.start[7:] *= min(
            1.0,
            (self.maximum - 1e-9) / max(self.maximum - 1e-9, max(shifts)),
            (self.minimum + 1e-9) / min(self.minimum + 1e-9, min(shifts)),
        )
        self.free = np.flatnonzero(self.lower != self.upper)
        self.disks = [(np.zeros(2), objective.prior.radius_km)]
        if local_center is not None:
            self.disks.append((np.asarray(local_center), local_radius_km))
        if not self.feasible(self.start):
            raise ValueError("infeasible initial point")

    def constraints(self, v):
        shifts = self.matrix @ v
        return np.r_[
            shifts - self.minimum,
            self.maximum - shifts,
            [r * r - np.sum((v[:2] - c) ** 2) for c, r in self.disks],
        ]

    def jacobian(self, v):
        rows = []
        for center, _ in self.disks:
            row = np.zeros(len(v))
            row[:2] = -2 * (v[:2] - center)
            rows.append(row)
        return np.vstack([self.matrix, -self.matrix, *rows])

    def feasible(self, v):
        z, low, high = v / self.scales, self.lower / self.scales, self.upper / self.scales
        return bool(
            np.min(self.constraints(v)) >= -1e-7
            and np.all(z >= low - 1e-9)
            and np.all(z <= high + 1e-9)
        )

    def stationarity(self, v, gradient):
        free, scales = self.free, self.scales
        g = (gradient * scales)[free]
        jac = (self.jacobian(v) * scales)[:, free]
        normals = list(jac[self.constraints(v) <= 1e-6])
        z, low, high = (v / scales)[free], (self.lower / scales)[free], (self.upper / scales)[free]
        eye = np.eye(len(free))
        for i in range(len(free)):
            if z[i] <= low[i] + 1e-7:
                normals.append(eye[i])
            if z[i] >= high[i] - 1e-7:
                normals.append(-eye[i])
        if normals:
            active = np.asarray(normals).T
            multipliers, _ = nnls(active, g, maxiter=100 * active.shape[1])
            g = g - active @ multipliers
        return float(np.max(abs(g), initial=0))


def _parameterization(problem):
    n = problem.objective.size
    transform = np.zeros((n, n))
    transform[:7, :7] = np.diag(problem.scales[:7])
    count = len(problem.matrix)
    transform[7, 7:] = 1 / count
    transform[8:, 7:] = problem.objective.basis.T
    initial = np.r_[problem.start[:7] / problem.scales[:7], problem.matrix @ problem.start]
    lower = np.r_[problem.lower[:7] / problem.scales[:7], np.full(count, problem.minimum)]
    upper = np.r_[problem.upper[:7] / problem.scales[:7], np.full(count, problem.maximum)]
    free = np.flatnonzero(lower != upper)
    fixed = transform @ initial
    matrix = transform[:, free]
    constant = fixed - matrix @ initial[free]
    return initial[free], lower[free], upper[free], matrix, constant


def fit_bounded_position(
    objective, start, *, maximum_seconds=5.0, maximum_iterations=200, **options
):
    """Return an independently audited fit and separately identified optimizer states."""
    if (
        not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= 1800
        or maximum_iterations < 1
    ):
        raise ValueError("invalid bounded fit budget")
    begun = time.monotonic()
    p = _Problem(objective, start, **options)
    initial, lower, upper, matrix, constant = _parameterization(p)
    records, accepted = [], []
    best = None

    def evaluate(z):
        nonlocal best
        if time.monotonic() - begun >= maximum_seconds:
            raise _Deadline()
        v = constant + matrix @ z
        value, gradient, _ = objective.evaluate(v)
        if p.feasible(v):
            row = (float(value), v.copy(), gradient.copy())
            if best is None or value < best[0]:
                best = row
            # Retain candidate states; audit only after optimization for speed.
            records.append(row)
        return value, matrix.T @ gradient

    def inequalities(z):
        v = constant + matrix @ z
        return np.r_[v[7] + 10, 10 - v[7], p.constraints(v)[2 * len(p.matrix) :]]

    def inequality_jac(z):
        v = constant + matrix @ z
        return np.vstack([matrix[7], -matrix[7], p.jacobian(v)[2 * len(p.matrix) :] @ matrix])

    def callback(z, state=None):
        if time.monotonic() - begun >= maximum_seconds:
            raise _Deadline()
        accepted.append((constant + matrix @ z).copy())

    solver_result, reason = None, "time-budget"
    try:
        solver_result = minimize(
            evaluate,
            initial,
            jac=True,
            method="SLSQP",
            bounds=Bounds(lower, upper),
            constraints={"type": "ineq", "fun": inequalities, "jac": inequality_jac},
            callback=callback,
            options={"maxiter": maximum_iterations, "ftol": 1e-11},
        )
        reason = f"solver-status-{solver_result.status}"
    except _Deadline:
        pass
    if best is None:
        raise TimeoutError("no feasible objective evaluation")
    # Audit seed, endpoint, best, and all candidate evaluations with a small
    # unconstrained gradient first. Active-face candidates are audited too.
    stationary = []
    for row in records:
        v, gradient = row[1:3]
        audit_candidate = (
            np.max(abs((gradient * p.scales)[p.free])) <= 0.001
            or np.min(p.constraints(v)) <= 1e-6
            or np.any((v / p.scales)[p.free] <= (p.lower / p.scales)[p.free] + 1e-7)
            or np.any((v / p.scales)[p.free] >= (p.upper / p.scales)[p.free] - 1e-7)
        )
        if audit_candidate and p.stationarity(v, gradient) <= 0.001:
            stationary.append(row)
    selected = min(stationary, key=lambda r: r[0]) if stationary else best

    def summarize(row):
        value, vector, gradient = row
        _, _, terms = objective.evaluate(vector)
        stationarity = p.stationarity(vector, gradient)
        mass = float(terms.responsibilities.sum())
        rms = (
            float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
            if mass
            else None
        )
        return PositionFit(
            vector,
            value,
            rms,
            mass,
            stationarity,
            stationarity <= 0.001,
            any(np.linalg.norm(vector[:2] - c) >= r - 1e-4 for c, r in p.disks),
            "independent-converged" if stationarity <= 0.001 else "nonstationary-" + reason,
            len(records),
            time.monotonic() - begun,
        )

    terminal = None
    if solver_result is not None:
        v = constant + matrix @ solver_result.x
        if p.feasible(v):
            value, gradient, terms = objective.evaluate(v)
            terminal = summarize((float(value), v, gradient))
    diagnostics = {
        "variant": "box",
        "solver_reason": reason,
        "solver_success": bool(solver_result.success) if solver_result is not None else False,
        "iterations": int(solver_result.nit) if solver_result is not None else len(accepted),
        "feasible_evaluations": len(records),
        "terminal": terminal,
        "best_feasible": summarize(best),
        "stationary_candidates": len(stationary),
        "timing_coverage_s": [p.coverage_min, p.coverage_max],
    }
    return summarize(selected), diagnostics
