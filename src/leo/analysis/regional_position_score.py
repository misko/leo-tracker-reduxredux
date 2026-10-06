"""C0/V16 singleton likelihood, orbit prediction and analytic fit derivatives.

All original top-one windows contribute, including unassigned/clutter windows.
No reference location, acquisition, storage or report-module dependencies.
"""

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from leo.contracts.regional_position import (
    PositionObservations,
    PositionOrbitBank,
    PositionScore,
    RegionalPrior,
)

ALIAS_HZ = 1 / 4.4e-6
LIGHT_KM_S = 299_792.458


def circular(value):
    return (np.asarray(value) + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def zero_sum_basis(count):
    if count < 1:
        raise ValueError("at least one satellite required")
    basis = np.zeros((count, count - 1))
    for j in range(count - 1):
        scale = np.sqrt((j + 1) * (j + 2))
        basis[: j + 1, j] = 1 / scale
        basis[j + 1, j] = -(j + 1) / scale
    return basis


def coordinates(prior: RegionalPrior, point):
    east, north = np.asarray(point, dtype=float)
    angular, bearing = np.hypot(east, north) / 6371.0088, np.arctan2(east, north)
    lat0, lon0 = np.radians([prior.latitude_deg, prior.longitude_deg])
    latitude = np.arcsin(
        np.sin(lat0) * np.cos(angular) + np.cos(lat0) * np.sin(angular) * np.cos(bearing)
    )
    longitude = lon0 + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(lat0),
        np.cos(angular) - np.sin(lat0) * np.sin(latitude),
    )
    return float(np.degrees(latitude)), float((np.degrees(longitude) + 180) % 360 - 180)


def observer(prior, point):
    lat, lon = np.radians(coordinates(prior, point))
    e2 = 6.6943799901413165e-3
    normal = 6378.137 / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    altitude = prior.altitude_m / 1000
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    ecef = (normal + altitude) * up
    ecef[2] = (normal * (1 - e2) + altitude) * np.sin(lat)
    return ecef, up


def predict_orbits(bank, observations, prior, point, shifts_s, *, derivatives=True):
    """Return Hz, visibility, position Jacobian and timing Jacobian, window x sat.

    Differentiate the actual piecewise-linear state interpolator, including its
    velocity slope. Receiver clock terms use receive time, never shifted orbit time.
    """
    shifts = np.asarray(shifts_s, dtype=float)
    if shifts.shape != (len(bank.numbers),) or not np.isfinite(shifts).all():
        raise ValueError("one finite orbit shift per satellite required")
    query = observations.times_s[:, None] + shifts[None, :]
    if np.any(query < bank.nodes_s[0]) or np.any(query > bank.nodes_s[-1]):
        raise ValueError("orbit query outside ephemeris support")
    step = bank.nodes_s[1] - bank.nodes_s[0]
    fractional = (query - bank.nodes_s[0]) / step
    lower = np.minimum(np.floor(fractional).astype(int), len(bank.nodes_s) - 2)
    weight = (fractional - lower)[..., None]
    satellites = np.arange(len(bank.numbers))[None, :]
    pos0, pos1 = bank.position_km[satellites, lower], bank.position_km[satellites, lower + 1]
    vel0 = bank.velocity_km_s[satellites, lower]
    vel1 = bank.velocity_km_s[satellites, lower + 1]
    position, velocity = pos0 + weight * (pos1 - pos0), vel0 + weight * (vel1 - vel0)
    site, up = observer(prior, point)
    delta = position - site
    distance = np.linalg.norm(delta, axis=2)
    if np.any(distance <= 0):
        raise ValueError("satellite coincides with observer")
    direction = delta / distance[..., None]
    radial = np.sum(direction * velocity, axis=2)
    factor = observations.rf_hz[:, None] / LIGHT_KM_S
    prediction = -factor * radial
    visible = np.sum(direction * up, axis=2) >= 0
    if not derivatives:
        return prediction, visible, None, None
    # Only the two-coordinate chart derivative uses central differences (1 m).
    # Orbit/likelihood derivatives are analytic; no finite-difference orbit calls.
    eye = np.eye(2) * 0.001
    site_jac = np.stack(
        [
            (observer(prior, np.asarray(point) + d)[0] - observer(prior, np.asarray(point) - d)[0])
            / 0.002
            for d in eye
        ]
    )
    spatial = factor[..., None] * (velocity - radial[..., None] * direction)
    spatial = np.einsum("nkj,ij->nki", spatial / distance[..., None], site_jac)
    pos_rate, acceleration = (pos1 - pos0) / step, (vel1 - vel0) / step
    direction_rate = pos_rate - direction * np.sum(direction * pos_rate, axis=2)[..., None]
    direction_rate /= distance[..., None]
    timing = -factor * np.sum(direction_rate * velocity + direction * acceleration, axis=2)
    return prediction, visible, spatial, timing


@dataclass(frozen=True)
class WindowLikelihood:
    nll: float
    responsibilities: np.ndarray
    clutter_probability: np.ndarray
    prediction_gradient: np.ndarray
    residual_hz: np.ndarray


def singleton_likelihood(measured_hz, prediction_hz, visible, score: PositionScore):
    measured, prediction = np.asarray(measured_hz), np.asarray(prediction_hz)
    visible = np.asarray(visible)
    if (
        prediction.ndim != 2
        or measured.shape != (len(prediction),)
        or visible.shape != prediction.shape
        or visible.dtype != bool
        or not np.isfinite(measured).all()
        or not np.isfinite(prediction).all()
    ):
        raise ValueError("invalid singleton likelihood arrays")
    count = prediction.shape[1]
    if count <= score.detection_budget:
        raise ValueError("detection budget must be below satellite count")
    q = np.where(visible, score.detection_budget / count, 0.0)
    residual = circular(measured[:, None] - prediction)
    sigma = score.sigma_hz
    images_count = max(
        1, int(np.ceil((sigma * np.sqrt(-2 * np.log(1e-15)) + ALIAS_HZ / 2) / ALIAS_HZ))
    )
    images = residual[..., None] + np.arange(-images_count, images_count + 1) * ALIAS_HZ
    log_images = -0.5 * (images / sigma) ** 2 - np.log(sigma * np.sqrt(2 * np.pi))
    log_phi = logsumexp(log_images, axis=2)
    mean_image = np.sum(np.exp(log_images - log_phi[..., None]) * images, axis=2)
    log_odds = np.full_like(q, -np.inf)
    log_odds[visible] = np.log(q[visible]) - np.log1p(-q[visible])
    signal = log_odds + log_phi
    clutter_log = np.log(score.clutter_rate / ALIAS_HZ)
    log_h = np.logaddexp(clutter_log, logsumexp(signal, axis=1))
    log_p0 = -score.clutter_rate + np.log1p(-q).sum(axis=1)
    log_density = log_p0 - np.log(-np.expm1(log_p0)) + log_h
    responsibility = np.exp(signal - log_h[:, None])
    return WindowLikelihood(
        float(-log_density.sum()),
        responsibility,
        np.exp(clutter_log - log_h),
        -responsibility * mean_image / sigma**2,
        residual,
    )


class PositionObjective:
    """Physical vector: east,north,a0,b0,a1,b1,c,tau,relative-basis coefficients.

    Offsets are Hz, slopes Hz/s, RF coefficient Hz/GHz, shifts seconds, location km.
    The same original observation inventory is scored at every location.
    """

    def __init__(
        self,
        observations: PositionObservations,
        bank: PositionOrbitBank,
        prior: RegionalPrior,
        score: PositionScore,
        *,
        receiver_baseline_hz=None,
    ):
        self.observations, self.bank, self.prior, self.score = observations, bank, prior, score
        self.basis = zero_sum_basis(len(bank.numbers))
        rx = observations.receiver
        centered = observations.times_s - observations.time_center_s
        self.design = np.column_stack(
            (
                rx == 0,
                (rx == 0) * centered,
                rx == 1,
                (rx == 1) * centered,
                (observations.rf_hz - observations.rf_center_hz) / 1e9,
            )
        )
        self.baseline = (
            np.zeros(len(rx))
            if receiver_baseline_hz is None
            else np.asarray(receiver_baseline_hz, float).copy()
        )
        if self.baseline.shape != rx.shape or not np.isfinite(self.baseline).all():
            raise ValueError("invalid frozen receiver baseline")

    @property
    def size(self):
        return 8 + self.basis.shape[1]

    def evaluate(self, vector):
        vector = np.asarray(vector, float)
        if vector.shape != (self.size,) or not np.isfinite(vector).all():
            raise ValueError("invalid position parameter vector")
        relative = self.basis @ vector[8:]
        shifts = vector[7] + relative
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], shifts
        )
        prediction += (self.design @ vector[2:7] + self.baseline)[:, None]
        terms = singleton_likelihood(self.observations.measured_hz, prediction, visible, self.score)
        weight = terms.prediction_gradient
        shift_gradient = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift_gradient.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative / self.score.relative_sigma_s**2)
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        return terms.nll + float(penalty), gradient, terms
