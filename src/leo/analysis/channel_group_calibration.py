"""Research receiver/group calibration with explicit training-frame transport.

Position vectors retain their published dimensions. Group contrasts are
separate private nuisance fields, and groups describe recorded hypotheses,
not an inferred hardware switch. No reference location enters this module.
"""

import time
from contextlib import suppress
from copy import copy
from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear, minimize

from leo.analysis.hard60_bounded_fit import _parameterization, _Problem
from leo.analysis.regional_position_score import ALIAS_HZ


@dataclass(frozen=True)
class GroupCalibrationFrame:
    """Training-defined centering retained when predicting another view."""

    receivers: tuple[int, ...]
    high_fractions: tuple[float, ...]

    def __post_init__(self):
        if (
            len(self.receivers) != len(self.high_fractions)
            or tuple(sorted(set(self.receivers))) != self.receivers
            or not set(self.receivers) <= {0, 1}
            or any(not np.isfinite(p) or not 0 < p < 1 for p in self.high_fractions)
        ):
            raise ValueError("invalid identifiable receiver/group calibration frame")

    def design(self, receiver, high_group):
        rx, high = np.asarray(receiver), np.asarray(high_group)
        if rx.ndim != 1 or high.shape != rx.shape or high.dtype != bool or not set(rx) <= {0, 1}:
            raise ValueError("aligned native receiver IDs and boolean group labels required")
        return (
            np.column_stack(
                [
                    (rx == r) * (high - fraction)
                    for r, fraction in zip(self.receivers, self.high_fractions, strict=True)
                ]
            )
            if self.receivers
            else np.empty((len(rx), 0))
        )


def group_frame(receiver, high_group):
    """Create only identifiable contrasts; retain sparse and single-group cases."""
    rx, high = np.asarray(receiver), np.asarray(high_group)
    if rx.ndim != 1 or high.shape != rx.shape or high.dtype != bool or not set(rx) <= {0, 1}:
        raise ValueError("aligned native receiver IDs and boolean group labels required")
    receivers, fractions = [], []
    for r in (0, 1):
        values = high[rx == r]
        if len(values) and values.any() and not values.all():
            receivers.append(r)
            fractions.append(float(values.mean()))
    return GroupCalibrationFrame(tuple(receivers), tuple(fractions))


def project_calibration_seed(model, target_hz):
    """Preserve a carried correction subject to the actual optimizer's bounds.

    An unconstrained projection can move a valid clock in one centering/basis
    outside another basis's coefficient bounds. Record the projection loss
    rather than dropping that channel-view comparison or silently clipping it.
    """
    target = np.asarray(target_hz, float)
    if target.shape != model.observations.times_s.shape or not np.isfinite(target).all():
        raise ValueError("one finite carried frequency correction per window required")
    clock = model.base.clock_design if model.clock_count else np.empty((len(target), 0))
    columns = np.column_stack([model.design, clock, model.group_design])
    scales = np.r_[
        200.0, 2.0, 200.0, 2.0, 200.0, np.full(model.clock_count, 50.0), model.group_scales
    ]
    limits = np.r_[np.full(model.clock_count, 2000.0), model.group_limits]
    lower = np.r_[-np.inf, -60.0, -np.inf, -60.0, -5000.0, -limits]
    upper = np.r_[np.inf, 60.0, np.inf, 60.0, 5000.0, limits]
    fit = lsq_linear(
        columns * scales,
        target,
        bounds=(lower / scales, upper / scales),
        lsq_solver="exact",
        tol=1e-11,
        max_iter=200,
    )
    if not fit.success:
        raise ValueError("bounded carried-calibration projection did not converge")
    coefficients = fit.x * scales
    residual = target - columns @ coefficients
    return dict(
        coefficients=coefficients,
        rms_hz=float(np.sqrt(np.mean(residual**2))),
        maximum_abs_hz=float(np.max(abs(residual))),
        active_bounds=np.flatnonzero(fit.active_mask).tolist(),
    )


class GroupCalibrationObjective:
    """Add receiver/group contrasts and remove their carried values exactly once."""

    def __init__(
        self,
        base,
        high_group,
        *,
        frame=None,
        carried_group_hz=None,
        sigma_hz=50_000.0,
        enabled=True,
        group_drift_sigma_hz_s=None,
        group_clock=False,
    ):
        if not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("positive finite group prior sigma required")
        rx = base.observations.receiver
        selected = group_frame(rx, high_group) if frame is None else frame
        self.frame = selected if enabled else GroupCalibrationFrame((), ())
        self.group_design = self.frame.design(rx, high_group)
        self.offset_count = len(self.frame.receivers)
        self.group_time_center_s = base.observations.time_center_s
        self.group_count = self.offset_count
        self.drift_count = 0
        self.group_clock_count = 0
        self.group_scales = np.full(self.offset_count, 5000.0)
        self.group_limits = np.full(self.offset_count, ALIAS_HZ / 2)
        variances = np.full(self.offset_count, sigma_hz**2)
        if group_drift_sigma_hz_s is not None:
            if not np.isfinite(group_drift_sigma_hz_s) or group_drift_sigma_hz_s <= 0:
                raise ValueError("positive finite group drift prior sigma required")
            time = base.observations.times_s - self.group_time_center_s
            self.group_design = np.column_stack(
                [self.group_design, self.group_design * time[:, None]]
            )
            self.group_count *= 2
            self.drift_count = self.offset_count
            self.group_scales = np.r_[self.group_scales, np.full(self.offset_count, 2.0)]
            self.group_limits = np.r_[self.group_limits, np.full(self.offset_count, 60.0)]
            variances = np.r_[variances, np.full(self.offset_count, group_drift_sigma_hz_s**2)]
        self.group_precision = np.diag(1 / variances)
        if group_clock and self.offset_count:
            if not hasattr(base, "null") or len(base.initial_clock) != 2 * base.null.shape[1]:
                raise ValueError("group clock needs the explicit two-receiver smooth-clock layout")
            width = base.null.shape[1]
            indices = []
            columns = []
            high = np.asarray(high_group)
            for rx, fraction in zip(self.frame.receivers, self.frame.high_fractions, strict=True):
                lane = list(range(rx * width, (rx + 1) * width))
                indices.extend(lane)
                columns.append(base.clock_design[:, lane] * (high - fraction)[:, None])
            self.group_clock_count = len(indices)
            previous = self.group_count
            self.group_count += self.group_clock_count
            self.group_design = np.column_stack([self.group_design, *columns])
            precision = np.zeros((self.group_count, self.group_count))
            precision[:previous, :previous] = self.group_precision
            precision[previous:, previous:] = base.precision[np.ix_(indices, indices)]
            self.group_precision = precision
            self.group_scales = np.r_[self.group_scales, np.full(self.group_clock_count, 50.0)]
            self.group_limits = np.r_[self.group_limits, np.full(self.group_clock_count, 2000.0)]
        self.clock_count = len(getattr(base, "initial_clock", ()))
        carried = (
            np.zeros(self.group_count)
            if carried_group_hz is None
            else np.asarray(carried_group_hz, float)
        )
        if carried.shape != (self.group_count,) or not np.isfinite(carried).all():
            raise ValueError("invalid carried receiver/group offsets")
        self.base = copy(base)
        self.base.baseline = np.asarray(base.baseline) - self.group_design @ carried
        self.initial_nuisance = np.r_[getattr(base, "initial_clock", ()), carried]
        self.sigma_hz = float(sigma_hz)
        self.precision = np.zeros((self.clock_count + self.group_count,) * 2)
        if self.clock_count:
            self.precision[: self.clock_count, : self.clock_count] = base.precision
        self.precision[self.clock_count :, self.clock_count :] = self.group_precision

    def __getattr__(self, name):
        return getattr(self.base, name)

    def split(self, nuisance):
        value = np.asarray(nuisance, float)
        if value.shape != self.initial_nuisance.shape or not np.isfinite(value).all():
            raise ValueError("invalid private calibration nuisance dimensions")
        return value[: self.clock_count], value[self.clock_count :]

    def correction(self, vector, nuisance):
        clock, group = self.split(nuisance)
        correction = self.base.baseline + self.design @ np.asarray(vector)[2:7]
        correction = correction + self.group_design @ group
        if self.clock_count:
            correction = correction + self.base.clock_design @ clock
        return correction

    def evaluate_joint(self, vector, nuisance):
        clock, group = self.split(nuisance)
        current = copy(self.base)
        current.baseline = self.base.baseline + self.group_design @ group
        if self.clock_count:
            value, gradient, clock_gradient, terms = current.evaluate_joint(vector, clock)
        else:
            value, gradient, terms = current.evaluate(vector)
            clock_gradient = np.empty(0)
        value += 0.5 * float(group @ self.group_precision @ group)
        group_gradient = (
            self.group_design.T @ terms.prediction_gradient.sum(axis=1)
            + self.group_precision @ group
        )
        return value, gradient, np.r_[clock_gradient, group_gradient], terms


def fit_group_calibration(
    model,
    vector,
    nuisance=None,
    *,
    arm="fitted-c",
    fixed_position=False,
    seconds=90.0,
    iterations=600,
    local_center=None,
    local_radius_km=None,
):
    """Fit a fixed private layout, audit stationarity, and preserve physical priors."""
    if not np.isfinite(seconds) or not 0 < seconds <= 1800 or iterations < 1:
        raise ValueError("invalid bounded research fit")
    problem = _Problem(
        model,
        vector,
        rf_arm=arm,
        fixed_position=fixed_position,
        local_center=local_center,
        local_radius_km=local_radius_km,
        slope_half_width_hz_s=60,
    )
    initial, lower, upper, matrix, constant = _parameterization(problem)
    dimension = len(initial)
    scales = np.r_[np.full(model.clock_count, 50.0), model.group_scales]
    limits = np.r_[np.full(model.clock_count, 2000.0), model.group_limits]
    n0 = model.initial_nuisance if nuisance is None else np.asarray(nuisance, float)
    model.split(n0)
    if np.any(abs(n0) > limits):
        raise ValueError("calibration seed outside declared alias branch")
    initial = np.r_[initial, n0 / scales]
    lower, upper = np.r_[lower, -limits / scales], np.r_[upper, limits / scales]
    begun, records = time.monotonic(), []

    class Deadline(Exception):
        pass

    def physical(z):
        return constant + matrix @ z[:dimension], z[dimension:] * scales

    def evaluate(z):
        if time.monotonic() - begun >= seconds:
            raise Deadline()
        v, n = physical(z)
        value, gradient, extra, _ = model.evaluate_joint(v, n)
        if problem.feasible(v):
            records.append((float(value), v.copy(), n.copy(), gradient.copy(), extra.copy()))
        return value, np.r_[matrix.T @ gradient, scales * extra]

    def constraints(z):
        v, _ = physical(z)
        return np.r_[v[7] + 10, 10 - v[7], problem.constraints(v)]

    def jacobian(z):
        v, _ = physical(z)
        core = np.vstack([matrix[7], -matrix[7], problem.jacobian(v) @ matrix])
        return np.column_stack([core, np.zeros((len(core), len(scales)))])

    solver = None
    with suppress(Deadline):
        solver = minimize(
            evaluate,
            initial,
            jac=True,
            method="SLSQP",
            bounds=list(zip(lower, upper, strict=True)),
            constraints={"type": "ineq", "fun": constraints, "jac": jacobian},
            options={"maxiter": iterations, "ftol": 1e-11},
        )
    if not records:
        raise TimeoutError("no feasible calibration evaluation")

    def audit(row):
        _, v, n, g, extra = row
        derivative = scales * extra.copy()
        derivative[(n <= -limits + 1e-7) & (derivative >= 0)] = 0
        derivative[(n >= limits - 1e-7) & (derivative <= 0)] = 0
        return max(problem.stationarity(v, g), float(np.max(abs(derivative), initial=0)))

    stationary = [
        (row, audit(row))
        for row in records
        if np.max(abs(scales * row[4]), initial=0) <= 0.001 or np.any(abs(row[2]) >= limits - 1e-7)
    ]
    accepted = [(row, kkt) for row, kkt in stationary if kkt <= 0.001]
    chosen, kkt = (
        min(accepted, key=lambda x: x[0][0])
        if accepted
        else (min(records, key=lambda x: x[0]), None)
    )
    if kkt is None:
        kkt = audit(chosen)
    value, v, n, _, _ = chosen
    _, _, _, terms = model.evaluate_joint(v, n)
    mass = float(terms.responsibilities.sum())
    clock, group = model.split(n)
    return dict(
        vector=v,
        nuisance=n,
        group_receivers=list(model.frame.receivers),
        training_high_fractions=list(model.frame.high_fractions),
        group_offsets_hz=group[: model.offset_count],
        group_drifts_hz_s=group[model.offset_count : model.offset_count + model.drift_count],
        group_clock_coefficients=group[model.offset_count + model.drift_count :],
        training_time_center_s=model.group_time_center_s,
        training_rf_center_hz=model.observations.rf_center_hz,
        clock_coefficients=clock,
        objective=value,
        likelihood_nll=float(terms.nll),
        posterior_rms_hz=(
            float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2) / mass))
            if mass > 0
            else None
        ),
        signal_windows=mass,
        stationarity=kkt,
        converged=kkt <= 0.001,
        boundary=float(problem.constraints(v).min()) < 1e-6,
        elapsed_s=time.monotonic() - begun,
        evaluations=len(records),
        solver_success=bool(solver is not None and solver.success),
        physical_constraints_minimum=float(problem.constraints(v).min()),
        group_prior_penalty=0.5 * float(group @ model.group_precision @ group),
    )
