"""Physical-element-conditioned phase uncertainty, using historical TLEs only.

TLE revisions are correlated prediction proxies, not observed orbit errors.
Neither a satellite identifier nor receiver/GPS evidence is a scale feature.
"""

import numpy as np
from scipy.optimize import minimize
from sgp4.api import Satrec

from ds23_continuous_forecast import arrays
from ds23_causal_phase_location import fit_location
from learn_ds23_causal_phase_forecast import distribution_cost


FEATURES = ('intercept', 'mean_motion', 'log_eccentricity', 'log_abs_bstar')


def features(lines):
    satellite = Satrec.twoline2rv(*lines)
    motion = satellite.no_kozai * 1440 / (2 * np.pi)
    return np.array([1., np.clip((motion - 15.4) / .5, -3, 3),
        np.clip(np.log(max(satellite.ecco, 1e-6) / .001), -3, 3),
        np.clip(np.log(max(abs(satellite.bstar), 1e-7) / .0001), -3, 3)])


def attach_features(history, forecast):
    """Join each transition to its middle, previously available element set."""
    cutoff = history['cutoff_utc_ns']
    lookup = {}
    for number, versions in history['past_versions'].items():
        if any(max(v['epoch'], v['collected_utc_ns']) > cutoff for v in versions):
            raise ValueError('future TLE in historical scale model')
        for k in range(2, len(versions)):
            a, b, c = versions[k-2:k+1]
            target = c['collected_utc_ns']
            if not (a['collected_utc_ns'] <= b['collected_utc_ns'] <= target and
                    a['epoch'] < b['epoch'] < c['epoch'] <= target):
                continue
            gap = (b['epoch'] - a['epoch']) / 1e9
            if gap < 1:
                continue
            key = (int(number), target, round((target-b['epoch'])/1e9, 4), round(gap, 4))
            if key in lookup:
                raise ValueError('ambiguous historical transition')
            lookup[key] = b
    result = []
    for row in forecast['transitions']:
        key = (row['norad'], row['validation_time_ns'], round(row['age_s'], 4),
               round(row['epoch_gap_s'], 4))
        b = lookup[key]
        result.append(dict(row, scale_features=features(b['lines']).tolist(),
            feature_epoch_ns=b['epoch'], feature_collection_ns=b['collected_utc_ns']))
    return result


def objective(theta, x, errors, sigma, model, penalty=True):
    scale = np.asarray(sigma) * np.exp(np.clip(x @ theta, -np.log(4.), np.log(4.)))
    value = distribution_cost(errors, scale, model['multiplier'], model['nu']).sum()
    # Unit Gaussian coefficient prior: extra model complexity is explicit.
    return float(value + (np.asarray(theta) @ theta if penalty else 0.))


def fit_scale(rows, model, bias=None, conditional=True):
    a = arrays(rows, model, bias)
    means = np.clip(np.clip(model['shrinkage']*a['unit'], -a['limit'], a['limit']) +
                    a['correction'], -a['limit'], a['limit'])
    x = np.array([r['scale_features'] for r in rows])
    if not conditional:
        x = x[:, :1]
    errors = a['target'] - means
    # Bounded coefficients limit extrapolation; no value is selected by GPS.
    fit = minimize(objective, np.zeros(x.shape[1]), args=(x, errors, a['sigma'], model),
        method='L-BFGS-B', bounds=[(-1., 1.)]*x.shape[1], options=dict(maxiter=160, ftol=1e-12))
    if not fit.success:
        raise ValueError('historical scale optimizer failed: ' + str(fit.message))
    theta = fit.x if conditional else np.r_[fit.x, 0., 0., 0.]
    return dict(coefficients=theta.tolist(), objective=float(fit.fun), conditional=conditional,
        features=list(FEATURES), converged=True, count=len(rows))


def score(rows, model, bias, coefficients):
    a = arrays(rows, model, bias)
    means = np.clip(np.clip(model['shrinkage']*a['unit'], -a['limit'], a['limit']) +
                    a['correction'], -a['limit'], a['limit'])
    x = np.array([r['scale_features'] for r in rows])
    return objective(np.array(coefficients), x, a['target']-means, a['sigma'], model, False)


def scale_for_elements(lines, coefficients):
    return float(np.exp(np.clip(features(lines) @ np.array(coefficients), -np.log(4.), np.log(4.))))


def qualify(history, forecast, full_model, bias_enabled, full_bias):
    rows = attach_features(history, forecast)
    boundary = forecast['temporal_split_boundary_ns']
    train = [r for r in rows if r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0]
    future = [r for r in rows if r['validation_time_ns'] > boundary]
    disjoint = [r for r in future if r['norad'] % 5 == 0]
    if min(len(train), len(future), len(disjoint)) < 30:
        return dict(qualified=False, reason='insufficient historical temporal/satellite validation')
    model = forecast['prefix_distribution']
    bias = fit_location(train, model) if bias_enabled else None
    scalar = fit_scale(train, model, bias, conditional=False)
    conditional = fit_scale(train, model, bias, conditional=True)
    validation = {}
    penalty = float(3 * np.log(len(train)))
    for name, subset in (('future', future), ('disjoint_future', disjoint)):
        scores = {kind: score(subset, model, bias, theta) for kind, theta in
            (('baseline', [0.]*4), ('scalar', scalar['coefficients']),
             ('conditional', conditional['coefficients']))}
        validation[name] = dict(count=len(subset), scores=scores,
            gain_vs_baseline=scores['baseline']-scores['conditional'],
            gain_vs_scalar=scores['scalar']-scores['conditional'])
    qualified = all(min(r['gain_vs_baseline'], r['gain_vs_scalar']) > penalty
                    for r in validation.values())
    return dict(qualified=bool(qualified), prefix_scalar=scalar, prefix_conditional=conditional,
        validation=validation, penalty=penalty, train_count=len(train),
        all_past_scalar=fit_scale(rows, full_model, full_bias, conditional=False),
        all_past_conditional=fit_scale(rows, full_model, full_bias, conditional=True),
        earlier_middle_element_features_only=True, target_or_future_element_not_a_feature=True,
        baseline_prefix_variance_and_tail_model_conditioned_not_relearned=True,
        features=list(FEATURES), multiplier_bounds=[.25, 4.],
        historical_TLE_revisions_correlated_proxies_not_orbit_truth=True)
