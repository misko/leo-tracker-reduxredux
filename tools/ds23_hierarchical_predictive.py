"""Gamma-noise posterior prediction without updating curved calibration.

The existing predictive Gaussian replaces an unseen Gamma(2,2) precision by
its mean inverse, inflating noise variance by two. Here the same Gamma prior
is integrated with a normalized Gaussian/Gamma variational bound. Shared
curved-calibration uncertainty and per-track Gaussian constants are retained.
"""

import numpy as np

from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from dsx01_hierarchical_bound import hierarchical_bound


def predictive_bound(raw, design, curved_gram, sigma, groups, *, bias_sigma_hz=300.):
    y, u = np.asarray(raw, float), np.asarray(design, float)
    gram, g = np.asarray(curved_gram, float), np.asarray(groups)
    if (u.ndim != 2 or y.shape != (u.shape[0],) or gram.shape != (u.shape[1], u.shape[1]) or
            g.shape != y.shape or not np.issubdtype(g.dtype, np.integer) or np.any(g < 0) or
            not np.isfinite(bias_sigma_hz) or bias_sigma_hz < 0):
        raise ValueError('matching predictive arrays and nonnegative constant prior required')
    root = np.linalg.cholesky(gram)
    uncertainty = np.linalg.solve(root, u.T).T
    biases = np.zeros((len(y), int(g.max())+1))
    biases[np.arange(len(y)), g] = bias_sigma_hz
    return hierarchical_bound(y, np.column_stack((uncertainty, biases)), sigma, g,
                              powers=1., noise_nu=4.)


def attach_hierarchical_predictive(p, entries, powers):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved = p.calculate
    def calculate(position):
        c = curved(position)
        g = p.noise_groups[p.keep]
        w = np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None])
        geometry = geometry_features(view, position, 0.)
        mean = view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction = predictive_bound(values-mean, geometry['features'], gram, sigma, groups)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['negative_twice_elbo']
        c['negative_twice_elbo'] += prediction['negative_twice_elbo']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        # Gates and returned calibration always use the unmodified curved-only
        # posterior mean, never the predictive integrator's latent adjustment.
        c['linear_raw_prediction_residual_hz'] = values-mean
        c['linear_elevation'] = geometry['elevation']
        c['linear_noise_precision'] = prediction['noise_precision']
        c['linear_precision_iterations'] = prediction['precision_iterations']
        c['linear_precision_change'] = prediction['final_log_precision_change']
        c['linear_calibration_coefficient_unchanged'] = True
        return c
    p.calculate = calculate
    p.curved_calculate = curved
    p.linear_entries, p.linear_slices = entries, slices
    return p
