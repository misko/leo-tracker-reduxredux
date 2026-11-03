"""Empirical shared satellite constant-Hz biases on the exact shared likelihood.

These are empirical nuisance coefficients, not identified transmitter clocks or
orbit errors. Every coefficient applies to its satellite across all RX/channel
rows. The existing physical parameters, q normalization and visibility remain.
"""
import numpy as np

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.shared_scan_model import density, elevation_geometry, horizon_weight


BIAS_BOUND_HZ = 4000.
PRIOR_WIDTHS_HZ = (300., 1000.)


class ConstantBiasObjective:
    def __init__(self, base, sigma_hz):
        if sigma_hz not in PRIOR_WIDTHS_HZ:
            raise ValueError('Predeclared bias prior width must be 300 or 1000 Hz')
        self.base_model = base
        self.bias_sigma_hz = float(sigma_hz)
        self.bias_start = len(base.initial_nuisance)
        self.bias_count = len(base.bank.numbers)
        self.initial_nuisance = np.r_[base.initial_nuisance, np.zeros(self.bias_count)]
        self.group_limits = np.r_[base.group_limits, np.full(self.bias_count, BIAS_BOUND_HZ)]
        self.group_scales = np.r_[base.group_scales, np.full(self.bias_count, 200.)]
        self.group_count = base.group_count+self.bias_count

    def __getattr__(self, name):
        if name == 'base_model':
            raise AttributeError(name)
        return getattr(self.base_model, name)

    def split(self, nuisance):
        n = np.asarray(nuisance, float)
        if n.shape != self.initial_nuisance.shape or not np.isfinite(n).all():
            raise ValueError('Finite original nuisance followed by K constant-Hz biases required')
        if np.any(abs(n[self.bias_start:]) > BIAS_BOUND_HZ+1e-7):
            raise ValueError('Satellite frequency bias outside +/-4000 Hz')
        return n[:self.clock_count], n[self.clock_count:]

    def evaluate_details(self, vector, nuisance):
        v, n = np.asarray(vector, float), np.asarray(nuisance, float)
        self.split(n)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError('Finite original physical vector required')
        model, raw = self.base_model, self.base_model.original
        obs, mask = model.scored_observations, model.mask
        clock, group = raw.split(n[:model.base_nuisance_count])
        tail = n[model.base_nuisance_count:self.bias_start]
        bias = n[self.bias_start:]
        relative = model.basis@v[8:]
        shifts = v[7]+relative
        prediction, hard_visible, spatial, timing = predict_orbits(
            model.bank, obs, model.prior, v[:2], shifts)
        sine, elevation_spatial, elevation_timing, cells = elevation_geometry(
            model.bank, obs, model.prior, v[:2], shifts)
        weight, slope = horizon_weight(sine, model.visibility_width)
        baseline = raw.baseline+raw.group_design@group
        correction = raw.design[mask]@v[2:7]+baseline[mask]+raw.clock_design[mask]@clock
        prediction += correction[:, None]
        prediction += bias[None, :]
        sigma, _, q, q_jacobian, intercept = model.hyperparameters(tail)
        terms, details = density(obs.measured_hz, prediction, weight, sigma, q, model.score)
        frequency_weight = terms.prediction_gradient
        elevation_weight = details['visibility_weight_gradient']*slope
        shift = np.sum(frequency_weight*timing+elevation_weight*elevation_timing, axis=0)
        gradient = np.zeros(model.size)
        gradient[:2] = np.einsum('nk,nki->i', frequency_weight, spatial)+np.einsum(
            'nk,nki->i', elevation_weight, elevation_spatial)
        gradient[2:7] = raw.design[mask].T@frequency_weight.sum(axis=1)
        gradient[7] = shift.sum()+v[7]/model.score.common_sigma_s**2
        gradient[8:] = model.basis.T@(shift+relative/model.score.relative_sigma_s**2)
        clock_gradient = raw.clock_design[mask].T@frequency_weight.sum(axis=1)+raw.base.precision@clock
        group_gradient = raw.group_design[mask].T@frequency_weight.sum(axis=1)+raw.group_precision@group
        tail_gradient = q_jacobian.T@details['detection_probability_gradient']+model.observation_precision*tail
        bias_gradient = frequency_weight.sum(axis=0)+bias/self.bias_sigma_hz**2
        penalty = .5*(v[7]/model.score.common_sigma_s)**2
        penalty += .5*np.sum((relative/model.score.relative_sigma_s)**2)
        penalty += .5*float(clock@raw.base.precision@clock+group@raw.group_precision@group)
        penalty += .5*float(tail@(model.observation_precision*tail))
        fixed = model.fixed_contrast_prior_penalty
        bias_penalty = .5*float(bias@bias)/self.bias_sigma_hz**2
        value = terms.nll+float(penalty)+fixed+bias_penalty
        details.update(sigma_hz=sigma, detection_probability=q, budget_intercept=intercept,
            observation_parameters=tail, sine_elevation=sine, visibility_weight=weight,
            hard_visible=hard_visible, elevation_spatial=elevation_spatial,
            elevation_timing=elevation_timing, interpolation_cells=cells,
            visibility_width=model.visibility_width, fixed_contrast_prior=fixed,
            prior_penalty=float(penalty)+fixed+bias_penalty,
            satellite_bias_hz=bias.copy(), satellite_bias_prior_penalty=bias_penalty,
            satellite_bias_sigma_hz=self.bias_sigma_hz)
        return (value, gradient, np.r_[clock_gradient, group_gradient, tail_gradient, bias_gradient], terms), details

    def evaluate_joint(self, vector, nuisance):
        return self.evaluate_details(vector, nuisance)[0]
