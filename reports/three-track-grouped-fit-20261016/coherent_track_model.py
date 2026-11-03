"""Research likelihood for supplied real tracks with one latent identity each."""
import numpy as np
from scipy.special import logsumexp

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood, circular
from leo.analysis.shared_scan_model import elevation_geometry, horizon_weight


def coherent_density(measured, prediction, visibility, sigma=125.):
    """A normalized categorical identity prior and independent Gaussian errors.

    This is conditional on the supplied group being a real single-satellite
    track. It has no clutter alternative. Visibility supplies a normalized
    geometric-mean prior; the floor is explicit numerical regularization.
    """
    measured, prediction, visibility = map(np.asarray, (measured, prediction, visibility))
    if (prediction.ndim != 2 or len(prediction) < 2 or prediction.shape[1] < 2
            or measured.shape != (len(prediction),) or visibility.shape != prediction.shape
            or not all(np.isfinite(a).all() for a in (measured, prediction, visibility))
            or np.any((visibility < 0) | (visibility > 1)) or not np.isfinite(sigma) or not 0 < sigma <= 1000):
        raise ValueError("Finite aligned track data, visibility and positive sigma required")
    floor = 1e-12
    clipped = np.maximum(visibility, floor)
    log_prior = np.log(clipped).mean(axis=0)
    residual = circular(measured[:, None] - prediction)
    images = residual[..., None] + np.array([-ALIAS_HZ, 0., ALIAS_HZ])
    log_gaussian = -.5 * (images / sigma)**2 - np.log(sigma * np.sqrt(2 * np.pi))
    log_rows = logsumexp(log_gaussian, axis=2)
    log_emission = log_rows.sum(axis=0)
    mean_residual = np.sum(np.exp(log_gaussian-log_rows[..., None])*images, axis=2)
    log_total = logsumexp(log_prior + log_emission)
    prior = np.exp(log_prior - logsumexp(log_prior))
    posterior = np.exp(log_prior + log_emission - log_total)
    value = float(logsumexp(log_prior) - log_total)
    prediction_gradient = -posterior[None, :] * mean_residual / sigma**2
    visibility_gradient = (prior - posterior)[None, :] / (len(measured) * clipped)
    visibility_gradient *= visibility > floor
    return value, posterior, prediction_gradient, visibility_gradient, residual


class CoherentTrackModel:
    """Replace target rows' independent mixtures with complete-track mixtures."""
    def __init__(self, background, groups):
        self.base = background
        self.groups = tuple(np.asarray(g, int) for g in groups)
        flat = np.concatenate(self.groups)
        if (any(len(g) < 2 or g.ndim != 1 for g in self.groups)
                or len(np.unique(flat)) != len(flat)
                or np.any(flat < 0) or np.any(flat >= len(background.observations.times_s))
                or background.mask[flat].any()
                or not np.all(background.mask | np.isin(np.arange(len(background.mask)), flat))):
            raise ValueError("Disjoint supplied tracks must exactly complement background rows")

    def __getattr__(self, name):
        if name == 'base':
            raise AttributeError(name)
        return getattr(self.base, name)

    def evaluate_details(self, vector, nuisance):
        old, details = self.base.evaluate_details(vector, nuisance)
        v, n = np.asarray(vector), np.asarray(nuisance)
        value, gradient, extra = old[0], old[1].copy(), old[2].copy()
        obs = self.observations
        count, satellites = len(obs.times_s), len(self.bank.numbers)
        posterior = np.zeros((count, satellites)); residual = np.zeros_like(posterior)
        prediction_gradient = np.zeros_like(posterior); clutter = np.zeros(count)
        posterior[self.base.mask] = old[3].responsibilities
        residual[self.base.mask] = old[3].residual_hz
        prediction_gradient[self.base.mask] = old[3].prediction_gradient
        clutter[self.base.mask] = old[3].clutter_probability
        nll = old[3].nll
        shifts = v[7] + self.basis @ v[8:]
        correction = self.original.correction(v, n[:self.base.base_nuisance_count])
        records = []
        for rows in self.groups:
            subset = observation_subset(obs, rows)
            prediction, _, spatial, timing = predict_orbits(self.bank, subset, self.prior, v[:2], shifts)
            prediction += correction[rows, None]
            sine, elevation_spatial, elevation_timing, _ = elevation_geometry(
                self.bank, subset, self.prior, v[:2], shifts)
            weight, slope = horizon_weight(sine, self.visibility_width)
            addition, probability, dw, de, rr = coherent_density(subset.measured_hz, prediction, weight)
            elevation_gradient = de * slope
            gradient[:2] += np.einsum('nk,nki->i', dw, spatial)
            gradient[:2] += np.einsum('nk,nki->i', elevation_gradient, elevation_spatial)
            gradient[2:7] += self.original.design[rows].T @ dw.sum(axis=1)
            dt = np.sum(dw * timing + elevation_gradient * elevation_timing, axis=0)
            gradient[7] += dt.sum(); gradient[8:] += self.basis.T @ dt
            extra[:self.clock_count] += self.original.clock_design[rows].T @ dw.sum(axis=1)
            extra[self.clock_count:self.base.base_nuisance_count] += self.original.group_design[rows].T @ dw.sum(axis=1)
            value += addition; nll += addition
            posterior[rows] = probability[None, :]; residual[rows] = rr
            prediction_gradient[rows] = dw
            k = int(np.argmax(probability))
            records.append(dict(satellite=int(self.bank.numbers[k]), probability=float(probability[k]),
                                rms_hz=float(np.sqrt(np.mean(rr[:, k]**2))), nll=addition))
        terms = WindowLikelihood(float(nll), posterior, clutter, prediction_gradient, residual)
        return (float(value), gradient, extra, terms), dict(details, coherent_tracks=records)

    def evaluate_joint(self, vector, nuisance):
        return self.evaluate_details(vector, nuisance)[0]
