"""Bounded constrained optimization of the truth-free C0/V16 position score."""

import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize, nnls

from leo.analysis.regional_position_score import PositionObjective


@dataclass(frozen=True)
class PositionFit:
    vector: np.ndarray
    objective: float
    posterior_rms_hz: float | None
    signal_windows: float
    stationarity: float
    converged: bool
    boundary: bool
    stop_reason: str
    evaluations: int
    elapsed_s: float


class _Deadline(Exception):
    pass


def fit_position(
    objective: PositionObjective,
    start,
    *,
    rf_arm="fitted-c",
    fixed_position=False,
    maximum_seconds=5.0,
    maximum_iterations=100,
    local_center=None,
    local_radius_km=None,
    slope_half_width_hz_s=None,
) -> PositionFit:
    """Hold position fixed for cell scoring, or release it within the prior disk.

    The RF ablation fixes c to exactly zero. It does not change observation rows,
    satellite bank, receiver baseline, other priors, or optimizer configuration.
    """
    if (
        rf_arm not in ("fitted-c", "zero-c")
        or not np.isfinite(maximum_seconds)
        or not 0 < maximum_seconds <= 1800
        or maximum_iterations < 1
    ):
        raise ValueError("invalid bounded fit configuration")
    start = np.asarray(start, float).copy()
    if start.shape != (objective.size,) or not np.isfinite(start).all():
        raise ValueError("invalid starting vector")
    radius = objective.prior.radius_km
    if np.linalg.norm(start[:2]) > radius + 1e-9:
        raise ValueError("starting point is outside prior")
    if (local_center is None) != (local_radius_km is None):
        raise ValueError("local center and radius must be supplied together")
    if local_radius_km is not None and (
        not np.isfinite(local_radius_km)
        or local_radius_km <= 0
        or np.asarray(local_center).shape != (2,)
        or not np.isfinite(local_center).all()
        or np.linalg.norm(start[:2] - local_center) > local_radius_km + 1e-9
    ):
        raise ValueError("invalid local search disk")
    scales = np.r_[1.0, 1.0, 200.0, 2.0, 200.0, 2.0, 200.0, np.ones(objective.size - 7)]
    lower, upper = np.full(objective.size, -np.inf), np.full(objective.size, np.inf)
    lower[:2], upper[:2] = -radius, radius
    if slope_half_width_hz_s is not None:
        if not np.isfinite(slope_half_width_hz_s) or slope_half_width_hz_s <= 0:
            raise ValueError("slope half width must be finite and positive")
        lower[[3, 5]], upper[[3, 5]] = -slope_half_width_hz_s, slope_half_width_hz_s
        start[[3, 5]] = np.clip(start[[3, 5]], -slope_half_width_hz_s, slope_half_width_hz_s)
    lower[6], upper[6] = -5000, 5000
    lower[7], upper[7] = -10, 10
    if fixed_position:
        lower[:2] = upper[:2] = start[:2]
    if rf_arm == "zero-c":
        lower[6] = upper[6] = start[6] = 0
    start[6] = np.clip(start[6], lower[6], upper[6])
    matrix = np.zeros((len(objective.bank.numbers), objective.size))
    matrix[:, 7], matrix[:, 8:] = 1, objective.basis
    minimum = max(-20.0, objective.bank.nodes_s[0] - objective.observations.times_s.min())
    maximum = min(20.0, objective.bank.nodes_s[-1] - objective.observations.times_s.max())
    if minimum >= 0 or maximum <= 0:
        raise ValueError("ephemeris bank must cover both timing bounds")
    start[7] = np.clip(start[7], -10, 10)
    shifts = matrix @ start
    # The zero-sum basis and projection can round an exact +/-20 s seed a few
    # ulps outside its bound. Start strictly inside, so the feasibility penalty
    # cannot hide every objective evaluation from an otherwise valid seed.
    timing_margin = min(1e-9, -minimum * 1e-6, maximum * 1e-6)
    initial_minimum, initial_maximum = minimum + timing_margin, maximum - timing_margin
    factor = min(
        1.0,
        initial_maximum / max(initial_maximum, float(shifts.max())),
        initial_minimum / min(initial_minimum, float(shifts.min())),
    )
    start[7:] *= factor
    free = np.flatnonzero(lower != upper)
    fixed = start / scales
    low, high = (lower / scales)[free], (upper / scales)[free]
    timing_jac = (matrix * scales)[..., free]

    def expand(z):
        result = fixed.copy()
        result[free] = z
        return result * scales

    disks = [(np.zeros(2), radius)]
    if local_center is not None:
        disks.append((np.asarray(local_center, float), float(local_radius_km)))

    def constraints(z):
        vector = expand(z)
        shifts = matrix @ vector
        return np.r_[
            shifts - minimum,
            maximum - shifts,
            [r**2 - np.sum((vector[:2] - center) ** 2) for center, r in disks],
        ]

    def constraint_jac(z):
        vector = expand(z)
        spatial = []
        for center, _ in disks:
            row = np.zeros(objective.size)
            row[:2] = -2 * (vector[:2] - center)
            spatial.append((row * scales)[free])
        return np.vstack([timing_jac, -timing_jac, *spatial])

    begun, evaluations, best = time.monotonic(), 0, None

    def evaluate(z):
        nonlocal evaluations, best
        if time.monotonic() - begun >= maximum_seconds:
            raise _Deadline()
        vector = expand(z)
        # SLSQP can query an infeasible timing point during its line search.
        # Return a smooth feasibility penalty without extrapolating ephemerides.
        shifts = matrix @ vector
        violation = np.minimum(shifts - minimum, 0) + np.maximum(shifts - maximum, 0)
        if np.any(violation):
            return 1e12 + 1e8 * float(violation @ violation), 2e8 * timing_jac.T @ violation
        value, gradient, terms = objective.evaluate(vector)
        evaluations += 1
        gradient = (gradient * scales)[free]
        if (
            np.min(constraints(z)) >= -1e-7
            and np.all(z >= low - 1e-9)
            and np.all(z <= high + 1e-9)
            and (
                best is None
                or value < best[0] - 1e-9
                or (
                    abs(value - best[0]) <= 1e-9
                    and np.linalg.norm(gradient) < np.linalg.norm(best[2])
                )
            )
        ):
            best = value, vector.copy(), gradient.copy(), terms, z.copy()
        return value, gradient

    reason = "iteration-limit"
    try:
        result = minimize(
            evaluate,
            fixed[free],
            method="SLSQP",
            jac=True,
            bounds=list(zip(low, high, strict=True)),
            constraints={"type": "ineq", "fun": constraints, "jac": constraint_jac},
            options={"maxiter": maximum_iterations, "ftol": 1e-11},
        )
        reason = "optimizer-success" if result.success else f"optimizer-status-{result.status}"
    except _Deadline:
        reason = "time-budget"
    if best is None:
        raise TimeoutError("fit ended before a feasible objective evaluation")
    value, vector, gradient, terms, z = best
    # Independent first-order KKT audit, including active disk/timing constraints.
    normals = list(constraint_jac(z)[constraints(z) <= 1e-6])
    for i in range(len(free)):
        if z[i] <= low[i] + 1e-7:
            normals.append(np.eye(len(free))[i])
        if z[i] >= high[i] - 1e-7:
            normals.append(-np.eye(len(free))[i])
    if normals:
        active = np.asarray(normals).T
        multipliers, _ = nnls(active, gradient, maxiter=100 * max(1, active.shape[1]))
        residual = gradient - active @ multipliers
    else:
        residual = gradient
    stationarity = float(np.max(abs(residual), initial=0))
    mass = float(terms.responsibilities.sum())
    rms = (
        float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
        if mass > 1e-12
        else None
    )
    boundary = any(np.linalg.norm(vector[:2] - center) >= r - 1e-4 for center, r in disks)
    return PositionFit(
        vector,
        float(value),
        rms,
        mass,
        stationarity,
        stationarity <= 0.001,
        boundary,
        reason,
        evaluations,
        time.monotonic() - begun,
    )
