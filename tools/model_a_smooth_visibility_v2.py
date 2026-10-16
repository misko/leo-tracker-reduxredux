"""V2 bounded-quintic conditional folded A density with differentiable horizon detection.

The compact transition is numerical regularization, not a hardware uncertainty
estimate. Original observations, orbital interpolation, calibration and priors
are unchanged. Effective Bernoulli detection is p(window,satellite)=q*w.
"""

import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood, circular, observer
from leo.analysis.research import model_b_observation_cv as port

DEFAULT_WIDTH = 1e-5
OBSERVER_STENCIL_KM = 0.001


def horizon_weight(sine_elevation, width=DEFAULT_WIDTH):
    s = np.asarray(sine_elevation, float)
    if not np.isfinite(s).all() or not np.isfinite(width) or not 0 < width < 0.01:
        raise ValueError("Finite elevation and explicit small positive transition width required")
    x = np.clip((s + width) / (2 * width), 0.0, 1.0)
    value = x**3 * (10 + x * (-15 + 6 * x))
    derivative = 30 * x**2 * (1 - x) ** 2 / (2 * width)
    return np.clip(value, 0.0, 1.0), derivative


def elevation_geometry(bank, observations, prior, point, shifts):
    """Differentiate the original linear state interpolation and observer site/up."""
    query = observations.times_s[:, None] + np.asarray(shifts)[None, :]
    step = bank.nodes_s[1] - bank.nodes_s[0]
    if (
        not np.isfinite(query).all()
        or query.min() < bank.nodes_s[0]
        or query.max() > bank.nodes_s[-1]
        or not np.allclose(np.diff(bank.nodes_s), step)
    ):
        raise ValueError("Original uniform ephemeris support required")
    frac = (query - bank.nodes_s[0]) / step
    lower = np.minimum(np.floor(frac).astype(int), len(bank.nodes_s) - 2)
    satellites = np.arange(len(bank.numbers))[None, :]
    position = bank.position_km[satellites, lower]
    difference = bank.position_km[satellites, lower + 1] - position
    position = position + (frac - lower)[..., None] * difference
    position_rate = difference / step
    site, up = observer(prior, point)
    delta = position - site
    distance = np.linalg.norm(delta, axis=2)
    if np.any(distance <= 0):
        raise ValueError("Satellite coincides with observer")
    direction = delta / distance[..., None]
    sine = np.einsum("nka,a->nk", direction, up)
    offsets = np.eye(2) * OBSERVER_STENCIL_KM
    pairs = [
        (observer(prior, np.asarray(point) + d), observer(prior, np.asarray(point) - d))
        for d in offsets
    ]
    site_jac = np.stack([(a[0] - b[0]) / (2 * OBSERVER_STENCIL_KM) for a, b in pairs])
    up_jac = np.stack([(a[1] - b[1]) / (2 * OBSERVER_STENCIL_KM) for a, b in pairs])
    spatial = (
        -site_jac @ up + sine[..., None] * np.einsum("nka,ia->nki", direction, site_jac)
    ) / distance[..., None] + np.einsum("nka,ia->nki", direction, up_jac)
    timing = (
        np.einsum("nka,a->nk", position_rate, up)
        - sine * np.einsum("nka,nka->nk", direction, position_rate)
    ) / distance
    return sine, spatial, timing, lower


def density(measured, prediction, weight, sigma, q, config):
    """Exact conditional selected-singleton density and both p derivative terms."""
    measured, prediction, weight, sigma, q = map(
        np.asarray, (measured, prediction, weight, sigma, q)
    )
    if (
        prediction.ndim != 2
        or measured.shape != (len(prediction),)
        or weight.shape != prediction.shape
        or sigma.shape != measured.shape
        or q.shape != (prediction.shape[1],)
        or any(not np.isfinite(a).all() for a in (measured, prediction, weight, sigma, q))
        or np.any((weight < 0) | (weight > 1))
        or np.any((q <= 0) | (q >= 1))
        or np.any((sigma <= 0) | (sigma > 1000))
        or abs(q.sum() - config.detection_budget) > 1e-10
    ):
        raise ValueError("Aligned finite soft visibility, sigma and full-bank q budget required")
    p = weight * q[None, :]
    odds = p / (1 - p)
    residual = circular(measured[:, None] - prediction)
    gaussian = np.exp(-0.5 * (residual / sigma[:, None]) ** 2) / (
        sigma[:, None] * np.sqrt(2 * np.pi)
    )
    signal = odds * gaussian
    total = config.clutter_rate / ALIAS_HZ + signal.sum(axis=1)
    normalizer = config.clutter_rate + odds.sum(axis=1)
    rows = np.log(normalizer) - np.log(total)
    responsibility = signal / total[:, None]
    # Including the normalizer term is essential even for zero-posterior satellites.
    p_gradient = (1 / normalizer[:, None] - gaussian / total[:, None]) / (1 - p) ** 2
    q_gradient = (p_gradient * weight).sum(axis=0)
    weight_gradient = p_gradient * q[None, :]
    terms = WindowLikelihood(
        float(rows.sum()),
        responsibility,
        config.clutter_rate / ALIAS_HZ / total,
        -responsibility * residual / sigma[:, None] ** 2,
        residual,
    )
    log_p0 = -config.clutter_rate + np.log1p(-p).sum(axis=1)
    details = dict(
        row_nll=rows,
        conditional_cfo_nll=rows,
        log_integrated_event_mass=log_p0 - np.log(-np.expm1(log_p0)) + np.log(normalizer),
        selected_cfo_normalizer=normalizer,
        effective_detection_probability=p,
        detection_probability_gradient=q_gradient,
        visibility_weight_gradient=weight_gradient,
        full_bank_budget=float(q.sum()),
    )
    return terms, details


class SmoothVisibilityModel(port.ObservationModel):
    """Keep the exact final-A calibration/clock/q layout; change visibility only."""

    def __init__(self, original, mask, *, width=DEFAULT_WIDTH):
        horizon_weight(np.zeros(1), width)
        super().__init__(original, mask, "detectability")
        self.visibility_width = float(width)

    def evaluate_details(self, vector, nuisance):
        v, n = np.asarray(vector, float), np.asarray(nuisance, float)
        self.split(n)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError("Original finite physical A vector required")
        base, obs, mask = self.original, self.scored_observations, self.mask
        clock, group = base.split(n[: self.base_nuisance_count])
        tail = n[self.base_nuisance_count :]
        relative = self.basis @ v[8:]
        shifts = v[7] + relative
        prediction, hard_visible, spatial, timing = predict_orbits(
            self.bank, obs, self.prior, v[:2], shifts
        )
        sine, elevation_spatial, elevation_timing, cells = elevation_geometry(
            self.bank, obs, self.prior, v[:2], shifts
        )
        weight, slope = horizon_weight(sine, self.visibility_width)
        baseline = base.baseline + base.group_design @ group
        correction = base.design[mask] @ v[2:7] + baseline[mask] + base.clock_design[mask] @ clock
        prediction += correction[:, None]
        sigma, _, q, q_jacobian, intercept = self.hyperparameters(tail)
        terms, details = density(obs.measured_hz, prediction, weight, sigma, q, self.score)
        frequency_weight = terms.prediction_gradient
        elevation_weight = details["visibility_weight_gradient"] * slope
        shift = np.sum(frequency_weight * timing + elevation_weight * elevation_timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", frequency_weight, spatial) + np.einsum(
            "nk,nki->i", elevation_weight, elevation_spatial
        )
        gradient[2:7] = base.design[mask].T @ frequency_weight.sum(axis=1)
        gradient[7] = shift.sum() + v[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        clock_gradient = (
            base.clock_design[mask].T @ frequency_weight.sum(axis=1) + base.base.precision @ clock
        )
        group_gradient = (
            base.group_design[mask].T @ frequency_weight.sum(axis=1) + base.group_precision @ group
        )
        tail_gradient = (
            q_jacobian.T @ details["detection_probability_gradient"]
            + self.observation_precision * tail
        )
        penalty = 0.5 * (v[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * float(
            clock @ base.base.precision @ clock + group @ base.group_precision @ group
        )
        penalty += 0.5 * float(tail @ (self.observation_precision * tail))
        details.update(
            sigma_hz=sigma,
            detection_probability=q,
            budget_intercept=intercept,
            observation_parameters=tail,
            sine_elevation=sine,
            visibility_weight=weight,
            hard_visible=hard_visible,
            elevation_spatial=elevation_spatial,
            elevation_timing=elevation_timing,
            interpolation_cells=cells,
            visibility_width=self.visibility_width,
            prior_penalty=float(penalty),
        )
        return (
            terms.nll + float(penalty),
            gradient,
            np.r_[clock_gradient, group_gradient, tail_gradient],
            terms,
        ), details
