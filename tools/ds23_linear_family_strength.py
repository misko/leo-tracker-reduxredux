"""Fixed family-support variance for linear prediction, with curved calibration.

The existing support powers are heuristic strengths, not calibrated identity
probabilities. This experiment uses them only to inflate independent predictive
measurement noise. Shared calibration covariance and fragment bias priors stay
unchanged. Linear measurements never enter calibration normal equations.
"""

import numpy as np
from ds23_predictive_linear import linear_geometry, predictive_residual
from ds23_height_problem import geometry_features


def family_strengths(rows, slices, keep, powers, entries):
    mask, weights = np.asarray(keep), np.asarray(powers, float)
    if len(rows) != len(slices) or weights.shape != (len(rows),) or mask.ndim != 1 or mask.dtype != bool:
        raise ValueError('one original strength per curved row and boolean observation mask required')
    if not np.isfinite(weights).all() or np.any((weights <= 0)|(weights > 1)):
        raise ValueError('original support strengths must lie in (0,1]')
    supported = {}
    for row, sl, weight in zip(rows, slices, weights, strict=True):
        if mask[sl].any(): supported[row['candidate_index']] = max(supported.get(row['candidate_index'], 0.), weight)
    result = []
    for entry in entries:
        if entry['candidate_index'] not in supported:
            raise ValueError('predictive family has no active curved calibration support')
        result.append(supported[entry['candidate_index']])
    return np.asarray(result)


def supported_prediction(raw, design, gram, sigma, groups, strength):
    y, s, g, strength = (np.asarray(v) for v in (raw, sigma, groups, strength))
    if (g.shape != y.shape or s.shape != y.shape or not np.issubdtype(g.dtype, np.integer)
            or strength.ndim != 1 or np.any(g < 0) or np.any(g >= len(strength))
            or not np.isfinite(strength).all() or np.any((strength <= 0)|(strength > 1))):
        raise ValueError('positive fixed curve strengths and matching integer point groups required')
    # Original unseen Gamma(2,2) moment E[1/tau]=2 is retained.
    effective_sigma = s*np.sqrt(2/strength[g])
    result = predictive_residual(y, design, gram, effective_sigma, g)
    result['effective_measurement_sigma_hz'] = effective_sigma
    return result


def attach_supported_prediction(p, entries, powers, *, unit_control=False):
    if not entries: return p
    strength = family_strengths(p.rows, p.slices, p.keep, powers, entries)
    if unit_control: strength = np.ones(len(entries))
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    curved = p.calculate
    def calculate(position):
        c = curved(position); g = p.noise_groups[p.keep]
        weight = np.asarray(powers)[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
        design = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+design.T@(design*weight[:, None])
        geometry = geometry_features(view, position, 0.)
        mean = view.q*geometry['intercept']+geometry['features']@c['coefficient']
        prediction = supported_prediction(values-mean, geometry['features'], gram, sigma, groups, strength)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['objective']; c['negative_twice_elbo'] += prediction['objective']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        c['linear_raw_prediction_residual_hz'] = values-mean; c['linear_elevation'] = geometry['elevation']
        c['linear_predictive_sigma_hz'] = prediction['effective_measurement_sigma_hz']
        c['linear_calibration_coefficient_unchanged'] = True
        return c
    p.calculate, p.curved_calculate = calculate, curved
    p.linear_entries, p.linear_slices, p.linear_family_strength = entries, slices, strength
    return p
