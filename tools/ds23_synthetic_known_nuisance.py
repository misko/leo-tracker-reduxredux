"""Diagnostic truth-conditioned priors; never use on real scan observations.

Known coordinates retain 1e-5 of their original prior standard deviation.
Linear tracks remain predictive and cannot update curved calibration.
"""

import numpy as np

from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry, predictive_residual
from dsx01_hierarchical_bound import hierarchical_bound
from dsx01_joint_marginal import JointMarginal
from probe_ds23_history_calibrated_phase import make_problem
from probe_ds23_receiver_smooth_prior import scale_posterior

COMPONENTS = ('radio', 'smooth', 'phase', 'orbit', 'fragment')


def conditional_prior(widths, fitted_c, means, sigma, truth, known, fraction=1e-5):
    """Map the c=0 generating coordinates into either fitted coordinate system."""
    widths = tuple(widths)
    known = frozenset(known)
    if len(widths) != 5 or widths[0] != 8 or min(widths) < 0:
        raise ValueError('original five-block c0 coordinates required')
    if not known.issubset(COMPONENTS) or not np.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError('declared components and positive finite precision fraction required')
    sigma, means = np.asarray(sigma, float), np.asarray(means, float)
    coefficient = np.asarray(truth['selected_coefficients'], float)
    phases = np.asarray(truth['true_phases_s'], float)
    if coefficient.shape != (sum(widths),) or sigma.shape != (widths[2],) or phases.shape != sigma.shape or means.shape != sigma.shape:
        raise ValueError('matching generating coordinates required')
    if np.any(sigma <= 0) or not all(np.isfinite(x).all() for x in (coefficient, phases, sigma, means)):
        raise ValueError('finite truths and positive phase uncertainties required')
    if fitted_c:
        coefficient = np.insert(coefficient, 8, 0.)  # generating c is zero
        widths = (9, *widths[1:])
    edges = np.r_[0, np.cumsum(widths)]
    blocks = {name: slice(a, b) for name, a, b in zip(COMPONENTS, edges[:-1], edges[1:], strict=True)}
    mean = np.zeros(sum(widths)); scale = np.ones(sum(widths))
    scale[blocks['fragment']] = .3
    mean[blocks['phase']] = means / sigma
    for name in known:
        sl = blocks[name]
        mean[sl] = phases / sigma if name == 'phase' else coefficient[sl]
        scale[sl] *= fraction
    groups = np.full(len(mean), -1, int)
    if 'phase' not in known:
        groups[blocks['phase']] = np.arange(widths[2])
    return mean, scale, groups


def known_problem(scan, node, keep, arm, reference, powers, means, hyper, truth, known):
    p = make_problem(scan, node, keep, arm, reference, powers, means, hyper['multiplier'], hyper['nu'])
    p.events = []
    mean, scales, groups = conditional_prior(truth['coordinate_widths'], p.fitted_c,
        means, p.phase_sigma, truth, known)
    def calculate(position):
        geometry = JointMarginal.calculate(p, position)
        u = geometry['features']
        raw = p.values - p.q * geometry['intercept'] - u @ mean
        present = np.unique(p.noise_groups[keep])
        bound = hierarchical_bound(raw[keep], (u * scales)[keep], p.point_noise[keep], p.noise_groups[keep],
            powers=np.asarray(powers)[present], prior_groups=None if hyper['nu'] is None else groups,
            prior_nu=4 if hyper['nu'] is None else hyper['nu'])
        bound = scale_posterior(bound, scales)
        bound['latent_coefficient'] = bound['coefficient'].copy()
        bound['coefficient'] += mean
        precision = np.zeros(len(p.members)); precision[present] = bound['noise_precision']
        bound['noise_precision'] = precision
        bound['conditional_residual_hz'] = p.values - p.q * geometry['intercept'] - u @ bound['coefficient']
        volume = float(2 * np.sum(np.asarray(powers)[p.noise_groups[keep]] * np.log(p.point_noise[keep] / 40)))
        bound['residual'] = np.r_[bound['residual'], np.sqrt(volume)]
        geometry.update(bound)
        return geometry
    p.calculate = calculate
    return p


def generating_linear_bias(truth, count):
    """Replay the generator's independent per-linear-fragment bias draw."""
    rng = np.random.default_rng(truth['latent_seed'])
    rng.normal(size=sum(truth['coordinate_widths']))
    rng.uniform(size=len(truth['true_phases_s']))
    return 300 * rng.normal(size=count)


def attach_known_predictive(p, entries, powers, truth, known):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved = p.calculate
    known_bias = generating_linear_bias(truth, len(entries))[groups] if 'fragment' in known else np.zeros(len(values))
    bias_sigma = 300e-5 if 'fragment' in known else 300.
    def calculate(position):
        c = curved(position)
        g = p.noise_groups[p.keep]
        w = np.asarray(powers)[g] * c['noise_precision'][g] / p.point_noise[p.keep] ** 2
        u = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision']) + u.T @ (u * w[:, None])
        geometry = geometry_features(view, position, 0.)
        predicted = view.q * geometry['intercept'] + geometry['features'] @ c['coefficient'] + known_bias
        prediction = predictive_residual(values - predicted, geometry['features'], gram,
            sigma * np.sqrt(2), groups, bias_sigma=bias_sigma)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['objective']
        c['negative_twice_elbo'] += prediction['objective']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        c['linear_raw_prediction_residual_hz'] = values - predicted
        c['linear_elevation'] = geometry['elevation']
        return c
    p.calculate = calculate; p.curved_calculate = curved
    p.linear_slices = slices; p.linear_entries = entries
    return p
