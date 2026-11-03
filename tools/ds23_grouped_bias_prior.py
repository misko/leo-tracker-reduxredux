"""Fixed-marginal fragment-bias correlations and curved-only prediction.

Channel and transmitter random effects redistribute the existing300Hz prior
variance; they do not add free per-linear-track calibration parameters.
"""

import numpy as np

from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from ds23_frozen_precision import conditional_gaussian


def bias_covariance(channel_keys, family_keys, channel_share=0., family_share=0., sigma=300.):
    channel_keys, family_keys = list(channel_keys), list(family_keys)
    n = len(channel_keys)
    if len(family_keys) != n or not n or not np.isfinite([channel_share, family_share, sigma]).all():
        raise ValueError('matching nonempty groups and finite variance fractions required')
    if min(channel_share, family_share) < 0 or channel_share+family_share >= 1 or sigma <= 0:
        raise ValueError('nonnegative shared fractions summing below one and positive sigma required')
    channel = np.array([[a == b for b in channel_keys] for a in channel_keys], float)
    family = np.array([[a == b for b in family_keys] for a in family_keys], float)
    return sigma**2*((1-channel_share-family_share)*np.eye(n)+channel_share*channel+family_share*family)


def conditional_bias(covariance, curved_count):
    k = np.asarray(covariance, float); n = int(curved_count)
    if k.ndim != 2 or k.shape[0] != k.shape[1] or not 0 < n <= len(k):
        raise ValueError('square bias covariance and nonempty curved block required')
    cc, lc, ll = k[:n, :n], k[n:, :n], k[n:, n:]
    root = np.linalg.cholesky(cc)
    regression = np.linalg.solve(root.T, np.linalg.solve(root, lc.T)).T
    residual = ll-regression@lc.T
    residual = (residual+residual.T)/2
    conditional_root = np.linalg.cholesky(residual) if len(ll) else np.zeros((0, 0))
    return dict(curved_root=root, regression=regression, conditional_covariance=residual,
                conditional_root=conditional_root)


def make_grouped_bias_problem(scan, node, mask, arm, reference, powers, means, hyper,
                              entries, channel_share, family_share, *, include_linear=True):
    p = make_event_problem(scan, node, mask, arm, reference, powers, means, hyper, [])
    indices = p.members+[e['track_index'] for e in entries]
    labels = [r['candidate_index'] for r in p.rows]+[e['candidate_index'] for e in entries]
    keys = [(scan.tracks[i]['receiver'], scan.tracks[i]['channel'], float(scan.tracks[i]['rf_hz'])) for i in indices]
    covariance = bias_covariance(keys, labels, channel_share, family_share)
    conditioned = conditional_bias(covariance, len(p.members))
    transform = conditioned['curved_root']/300.
    p.constants = p.constants@transform
    p.bias_covariance = covariance
    p.bias_conditional = conditioned
    p.bias_group_shares = dict(channel=channel_share, family=family_share)
    if not entries or not include_linear:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    # The native coefficient coordinate has prior SD .3, and the old basis is
    #1000Hz. Map conditional linear-curve means to those exact coordinates.
    loading = conditioned['regression']@(1000*transform)
    view.constants = loading[groups]
    independent_bias_modes = conditioned['conditional_root'][groups]
    curved = p.calculate
    def calculate(position):
        c = curved(position)
        g = p.noise_groups[p.keep]
        weights = np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        u = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+u.T@(u*weights[:, None])
        geometry = geometry_features(view, position, 0.)
        predicted = view.q*geometry['intercept']+geometry['features']@c['coefficient']
        root = np.linalg.cholesky(gram)
        uncertainty = np.linalg.solve(root, geometry['features'].T).T
        design = np.column_stack((uncertainty, independent_bias_modes))
        prediction = conditional_gaussian(values-predicted, design, sigma*np.sqrt(2),
            np.ones(len(values)), np.ones(len(values)), np.ones(design.shape[1]), 1.)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['objective']
        c['negative_twice_elbo'] += prediction['objective']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        c['linear_raw_prediction_residual_hz'] = values-predicted
        c['linear_elevation'] = geometry['elevation']
        c['linear_calibration_coefficient_unchanged'] = True
        return c
    p.calculate, p.curved_calculate = calculate, curved
    p.linear_entries, p.linear_slices = entries, slices
    return p
