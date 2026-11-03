"""Per-lane simultaneous-error conditionals in one predictive covariance block."""

import numpy as np

from ds23_predictive_linear import linear_geometry, predictive_residual
from ds23_height_problem import geometry_features


def condition_multiple(values, features, mean, primary_values, primary_features, primary_mean,
                       rows, anchors, kappas):
    rows, anchors, k = np.asarray(rows, int), np.asarray(anchors, int), np.asarray(kappas, float)
    if rows.shape != anchors.shape or rows.shape != k.shape or rows.ndim != 1:
        raise ValueError('aligned conditional rows, anchors and per-row loadings required')
    if len(set(rows)) != len(rows) or len(set(anchors)) != len(anchors):
        raise ValueError('one conditional component per distinct original primary probe required')
    if not np.isfinite(k).all() or np.any(k < 0) or np.any(k >= 1):
        raise ValueError('finite conditional loadings in [0,1) required')
    y, u, m = np.asarray(values).copy(), np.asarray(features).copy(), np.asarray(mean).copy()
    y[rows] -= k*np.asarray(primary_values)[anchors]
    u[rows] -= k[:, None]*np.asarray(primary_features)[anchors]
    m[rows] -= k*np.asarray(primary_mean)[anchors]
    return y, u, m


def attach_multilane_prediction(p, entries, powers, anchors_by_component, covariance_by_component, correlated):
    if not entries:
        return p
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    rows, anchors, kappas = [], [], []
    sigma = sigma.copy()
    for entry, sl in zip(entries, slices, strict=True):
        key = entry['component']
        if key not in anchors_by_component:
            continue
        anchor = anchors_by_component[key]
        if len(anchor) != sl.stop-sl.start:
            raise ValueError('one original curved anchor per new component point required')
        covariance = covariance_by_component[key]
        kappa = covariance['kappa'] if correlated else 0.
        sigma[sl] = covariance['marginal_sigma_hz']*np.sqrt(1-kappa*kappa)
        rows.extend(range(sl.start, sl.stop)); anchors.extend(anchor); kappas.extend([kappa]*len(anchor))
    rows, anchors, kappas = np.asarray(rows, int), np.asarray(anchors, int), np.asarray(kappas, float)
    if len(set(anchors)) != len(anchors) or np.any(~p.keep[anchors]):
        raise ValueError('new independent conditional blocks require distinct active original probes')
    curved = p.calculate
    def calculate(position):
        c = curved(position)
        group = p.noise_groups[p.keep]
        weights = np.asarray(powers)[group]*c['noise_precision'][group]/p.point_noise[p.keep]**2
        old = c['features'][p.keep]
        gram = np.diag(c['coefficient_prior_precision'])+old.T@(old*weights[:, None])
        geometry = geometry_features(view, position, 0.)
        mean = view.q*geometry['intercept']+geometry['features']@c['coefficient']
        original_mean = p.q*c['intercept']+c['features']@c['coefficient']
        y, design, prediction_mean = condition_multiple(values, geometry['features'], mean, p.values,
            c['features'], original_mean, rows, anchors, kappas)
        prediction = predictive_residual(y-prediction_mean, design, gram, sigma*np.sqrt(2), groups)
        c['curved_negative_twice_elbo'] = c['negative_twice_elbo']
        c['linear_predictive_objective'] = prediction['objective']
        c['negative_twice_elbo'] += prediction['objective']
        c['normalization_constant'] += prediction['normalization_constant']
        c['residual'] = np.r_[c['residual'], prediction['residual']]
        c['linear_raw_prediction_residual_hz'] = y-prediction_mean
        c['linear_elevation'] = geometry['elevation']
        c['linear_calibration_coefficient_unchanged'] = True
        c['conditional_measurements'] = len(rows)
        return c
    p.calculate, p.curved_calculate = calculate, curved
    p.linear_entries, p.linear_slices = entries, slices
    return p
