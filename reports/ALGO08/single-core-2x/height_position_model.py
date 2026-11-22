"""Conditional Doppler shape fits with a single linear receiver-height term."""

from dataclasses import dataclass
from time import process_time

import numpy as np
from scipy.optimize import least_squares

from leo.analysis.localization_v3.marginal import integrated_gaussian
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from .height_sensitivity import height_gradient


LIGHT_KM_S = 299792.458
PHASE_STEP_S = .05
SIGMA_HZ = 80.
HEIGHT_BOUNDS_KM = (-.5, 4.)


@dataclass(frozen=True)
class Geometry:
    """Three phase slices of fixed orbit states at each track's observation times."""

    position: np.ndarray
    velocity: np.ndarray
    times: np.ndarray
    receiver: np.ndarray
    rf_hz: np.ndarray

    def mean_and_phase(self, region, point, *, exact_height=False):
        lat, lon = region.latlon(point[:2])
        height = point[2]
        observer = geodetic_to_ecef_km(lat, lon, 1000 * height if exact_height else 0.)
        rf = self.rf_hz[:, None]
        relative = self.position - observer
        slant = np.linalg.norm(relative, axis=-1)
        velocity = np.sum(relative * self.velocity, axis=-1) / slant
        frequencies = -rf / LIGHT_KM_S * velocity
        if not exact_height:
            up = ecef_to_enu_matrix(lat, lon)[2]
            frequencies += height * height_gradient(self.position, self.velocity, observer, up, rf)
        return frequencies[0], (frequencies[1] - frequencies[2]) / (2 * PHASE_STEP_S)

    def fixed_design(self):
        ntracks, count = self.times.shape
        orbit = np.repeat(np.eye(ntracks), count, axis=0)
        radios = np.repeat(np.eye(2)[self.receiver], count, axis=0)
        local = self.times - self.times.mean(axis=1, keepdims=True)
        normalized = local / np.ptp(self.times, axis=1)[:, None] * 2
        global_time = (self.times.ravel() - 150) / 150
        ordinary = np.column_stack((650 * radios, 90 * radios * global_time[:, None],
                                    180 * orbit, 75 * orbit * normalized.ravel()[:, None]))
        rf = np.repeat((self.rf_hz / 1e9 - 11.5) * 1800, count)
        return ordinary, orbit, rf


def synthesize(region, geometry, truth_point, rng):
    """Plant exact ellipsoid height and a correlated clock component left out of the fit."""
    ordinary, orbit, rf = geometry.fixed_design()
    base, phase = geometry.mean_and_phase(region, truth_point, exact_height=True)
    phase_bias = orbit @ rng.normal(0, 1, orbit.shape[1])
    noise = rng.normal(0, SIGMA_HZ, size=geometry.times.shape)
    clock_phase = rng.uniform(-np.pi, np.pi, 2)[geometry.receiver, None]
    clock = 45 * np.sin(2 * np.pi * geometry.times / 175 + clock_phase)
    return (base + (ordinary @ rng.normal(size=ordinary.shape[1]) + .65 * rf).reshape(base.shape)
            + phase * phase_bias.reshape(base.shape) + noise + clock)


def affine_residual(values, times):
    """Apply the fixed per-track time contrast to one or more columns."""
    t = (times - times.mean(axis=1, keepdims=True))[..., None]
    centered = values - values.mean(axis=1, keepdims=True)
    slope = np.sum(t * centered, axis=1, keepdims=True) / np.sum(t * t, axis=1, keepdims=True)
    return centered - t * slope


def information(geometry, region, point, design, training):
    """Local mean-geometry information with and without the affine nuisance priors."""
    step = np.eye(3) * .001
    columns = [(geometry.mean_and_phase(region, point + delta)[0]
                - geometry.mean_and_phase(region, point - delta)[0]) / .002 for delta in step]
    jacobian = np.stack(columns, axis=-1)[training] / SIGMA_HZ
    j = jacobian.reshape(-1, 3)
    a = design / SIGMA_HZ
    gram = np.eye(a.shape[1]) + a.T @ a
    marginal = j.T @ (j - a @ np.linalg.solve(gram, a.T @ j))
    singular = np.sqrt(np.maximum(0., np.linalg.eigvalsh(marginal)))[::-1]
    covariance = np.linalg.pinv(marginal)
    shape = affine_residual(jacobian, geometry.times[training]).reshape(-1, 3)
    shape_singular = np.linalg.svd(shape, compute_uv=False)
    return dict(singular_per_km=singular.tolist(),
                condition=float(singular[0] / singular[-1]) if singular[-1] > 0 else None,
                local_height_sigma_km=float(np.sqrt(covariance[2, 2])) if singular[-1] > 1e-8 else None,
                affine_projected_singular_per_km=shape_singular.tolist())


def fit(region, geometry, observations, training, *, fit_height, fitted_c):
    """Fit from whole training tracks and lock its state before reading held CFO."""
    start_time = process_time()
    training = np.asarray(training, dtype=bool)
    rows = np.repeat(training, geometry.times.shape[1])
    measured = observations.ravel()[rows]
    fixed, orbit, rf = geometry.fixed_design()
    if fitted_c:
        fixed = np.column_stack((fixed, rf))

    def predict(point):
        base, phase = geometry.mean_and_phase(region, point)
        return base.ravel(), np.column_stack((fixed, orbit * phase.ravel()[:, None]))

    def position(parameters):
        return parameters if fit_height else np.r_[parameters, 0.]

    def objective(parameters):
        base, design = predict(position(parameters))
        return integrated_gaussian(measured - base[rows], design[rows], SIGMA_HZ)["residual"]

    radius = region.half_width_km
    lower, upper = [-radius, -radius], [radius, radius]
    if fit_height:
        lo, hi = HEIGHT_BOUNDS_KM
        lower.append(lo)
        upper.append(hi)
    result = least_squares(objective, np.zeros(len(lower)), bounds=(lower, upper),
                           max_nfev=70, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    point = position(result.x)
    base, design = predict(point)
    fit_result = integrated_gaussian(measured - base[rows], design[rows], SIGMA_HZ)
    predicted = (base + design @ fit_result["coefficient"]).reshape(observations.shape)
    elapsed = process_time() - start_time
    held = ~training
    raw = observations[held] - predicted[held]
    shape = affine_residual(raw[..., None], geometry.times[held])[..., 0]
    return dict(position_km=point.tolist(), prediction=predicted,
                c_hz_per_ghz=float(1800 * fit_result["coefficient"][fixed.shape[1] - 1]) if fitted_c else 0.,
                held_rms_hz=float(np.sqrt(np.mean(raw**2))),
                held_shape_rms_hz=float(np.sqrt(np.sum(shape**2) / (shape.size - 2 * held.sum()))),
                fit_cpu_s=elapsed, evaluations=result.nfev, success=result.success,
                active_bounds=result.active_mask.tolist(),
                information=information(geometry, region, point, design[rows], training))
