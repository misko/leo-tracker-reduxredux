"""Signed phase-prior centers learned solely from earlier TLE innovations."""

import numpy as np
from scipy.optimize import minimize_scalar

from learn_ds23_causal_phase_forecast import distribution_cost

KINDS = ('seconds', 'standardized', 'age', 'age_squared')


def location_feature(kind, sigma, age_s, multiplier):
    sigma, age = np.broadcast_arrays(np.asarray(sigma, float), np.asarray(age_s, float))
    if kind not in KINDS or not np.isfinite(multiplier) or multiplier <= 0:
        raise ValueError('known mean feature and positive fixed scale required')
    if not np.isfinite(sigma).all() or not np.isfinite(age).all() or np.any(sigma <= 0) or np.any(age < 0):
        raise ValueError('positive finite phase scales and nonnegative causal ages required')
    return dict(seconds=np.ones_like(sigma), standardized=sigma*multiplier,
                age=age/43200., age_squared=(age/43200.)**2)[kind]


def predict(rows, model, kind=None, coefficient=0.):
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    age = np.array([r['age_s'] for r in rows])
    ordinary = model['shrinkage']*np.array([r['unit_forecast_s'] for r in rows])
    correction = 0. if kind is None else coefficient*location_feature(kind, sigma, age, model['multiplier'])
    limit = np.minimum(15., 3*sigma)
    return np.clip(ordinary+correction, -limit, limit)


def cost(rows, model, kind=None, coefficient=0.):
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    target = np.array([r['next_innovation_s'] for r in rows])
    return float(distribution_cost(target-predict(rows, model, kind, coefficient),
                                   sigma, model['multiplier'], model['nu']).sum())


def fit_location(rows, model, kinds=KINDS):
    baseline = cost(rows, model)
    choices = [dict(kind=None, coefficient=0., cost=baseline, criterion=baseline)]
    for kind in kinds:
        fitted = minimize_scalar(lambda b:cost(rows, model, kind, b)+b*b,
                                 bounds=(-3., 3.), method='bounded', options=dict(xatol=1e-7))
        b = float(fitted.x)
        value = cost(rows, model, kind, b)
        choices.append(dict(kind=kind, coefficient=b, cost=value,
            criterion=value+np.log(max(1,len(rows)))+2*np.log(len(KINDS))+b*b))
    return dict(min(choices, key=lambda r:r['criterion']), choices=choices)


def qualify(rows, boundary, prefix_model, full_model):
    training = [r for r in rows if r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0]
    future = [r for r in rows if r['validation_time_ns'] > boundary]
    disjoint = [r for r in future if r['norad'] % 5 == 0]
    if min(map(len, (training, future, disjoint))) < 30:
        return dict(qualified=False, reason='insufficient chronological and satellite-disjoint evidence')
    prefix = fit_location(training, prefix_model)
    kind, b = prefix['kind'], prefix['coefficient']
    gain = cost(future, prefix_model)-cost(future, prefix_model, kind, b)
    disjoint_gain = cost(disjoint, prefix_model)-cost(disjoint, prefix_model, kind, b)
    penalty = lambda n:np.log(n)+2*np.log(len(KINDS))
    qualified = bool(kind and gain > penalty(len(future)) and disjoint_gain > penalty(len(disjoint)))
    full = fit_location(rows, full_model, (kind,)) if qualified else None
    # Full-data selection may conservatively return the nested zero-mean model.
    qualified = bool(qualified and full['kind'] is not None)
    return dict(qualified=qualified, kind=full['kind'] if qualified else None,
        coefficient=full['coefficient'] if qualified else 0., prefix=prefix, all_past=full,
        future_gain=gain, disjoint_future_gain=disjoint_gain,
        training_count=len(training), future_count=len(future), disjoint_future_count=len(disjoint),
        correction_form_selected_on_training_only=True)


def adjust_means(ordinary, receipts, model, selection):
    if not selection['qualified']:
        return np.asarray(ordinary).copy()
    sigma = np.array([r['sigma_s'] for r in receipts])
    ages = np.array([r['age_s']+150. for r in receipts])
    correction = selection['coefficient']*location_feature(selection['kind'], sigma, ages, model['multiplier'])
    limit = np.minimum(15., 3*sigma)
    return np.clip(np.asarray(ordinary)+correction, -limit, limit)
