"""Causal cross-satellite TLE innovations as a phase-prior mean predictor.

This qualification uses TLE updates as imperfect orbit-error proxies. No RF,
GPS, candidate nomination or per-scan position is an input.
"""

import numpy as np
from scipy.optimize import minimize_scalar
from ds23_causal_phase_location import predict, fit_location
from learn_ds23_causal_phase_forecast import distribution_cost

KINDS = ('global', 'plane')


def orbit_coordinates(lines):
    line = lines[1]
    return np.array([float(line[8:16]), float(line[17:25]), float(line[52:63])])


def attach_orbits(rows, versions):
    lookup = {(int(n), v['collected_utc_ns']): (old, v)
              for n, group in versions.items() for old, v in zip(group[:-1], group[1:])}
    result = []
    for r in rows:
        old, new = lookup[(r['norad'], r['validation_time_ns'])]
        result.append(dict(r, target_orbit=orbit_coordinates(old['lines']), available_orbit=orbit_coordinates(new['lines'])))
    return sorted(result, key=lambda r: (r['validation_time_ns'], r['norad']))


def normalized_innovations(rows, model, location):
    baseline = predict(rows, model, location.get('kind'), location.get('coefficient', 0.))
    sigma = np.array([r['predicted_sigma_s'] for r in rows])*model['multiplier']
    return np.clip((np.array([r['next_innovation_s'] for r in rows])-baseline)/sigma, -5, 5)


def features(rows, model, location, queries=None):
    """Latest distinct-neighbor innovations, lagged >=300s; no same-batch leak."""
    ordered = sorted(rows, key=lambda r: (r['validation_time_ns'], r['norad']))
    z = normalized_innovations(ordered, model, location)
    queries = ordered if queries is None else queries
    # Queries may include a current scan cutoff beyond every history update.
    qorder = sorted(enumerate(queries), key=lambda q: (q[1]['validation_time_ns'], q[1]['norad']))
    result = np.zeros((len(queries), 2)); counts = np.zeros_like(result); newest = {}
    cursor = 0
    for index, target in qorder:
        cutoff = target['validation_time_ns']-300_000_000_000
        while cursor < len(ordered) and ordered[cursor]['validation_time_ns'] < cutoff:
            row = ordered[cursor]
            newest[row['norad']] = (row, z[cursor]); cursor += 1
        neighbors = [(r, value) for number, (r, value) in newest.items()
                     if number != target['norad'] and 0 <= (target['validation_time_ns']-r['validation_time_ns'])/1e9 <= 43200]
        if not neighbors:
            continue
        age = np.array([(target['validation_time_ns']-r['validation_time_ns'])/1e9 for r, _ in neighbors])
        orbital = np.array([r['available_orbit'] for r, _ in neighbors])
        difference = orbital-np.asarray(target['target_orbit'])
        difference[:, 1] = (difference[:, 1]+180)%360-180
        weights = np.exp(-age/21600)
        plane = weights*np.exp(-.5*np.sum((difference/np.array([1., 10., .1]))**2, axis=1))
        values = np.array([value for _, value in neighbors])
        for j, w in enumerate([weights, plane]):
            effective = w.sum()**2/max(float(w@w), 1e-30)
            counts[index, j] = effective
            if effective >= (10 if j == 0 else 3) and w.sum() > 1e-8:
                result[index, j] = float(w@values/w.sum())
    return result, counts


def cost(rows, model, location, feature, coefficient):
    baseline = predict(rows, model, location.get('kind'), location.get('coefficient', 0.))
    sigma = np.array([r['predicted_sigma_s'] for r in rows])
    mean = baseline+coefficient*sigma*model['multiplier']*np.asarray(feature)
    mean = np.clip(mean, -np.minimum(15., 3*sigma), np.minimum(15., 3*sigma))
    return float(distribution_cost(np.array([r['next_innovation_s'] for r in rows])-mean,
                                   sigma, model['multiplier'], model['nu']).sum())


def fit_predictor(rows, model, location, design):
    baseline = cost(rows, model, location, np.zeros(len(rows)), 0.)
    choices = [dict(kind=None, coefficient=0., cost=baseline, criterion=baseline)]
    for j, kind in enumerate(KINDS):
        fitted = minimize_scalar(lambda b: cost(rows, model, location, design[:, j], b)+b*b,
                                 bounds=(-3., 3.), method='bounded')
        b = float(fitted.x); value = cost(rows, model, location, design[:, j], b)
        choices.append(dict(kind=kind, coefficient=b, cost=value,
                            criterion=value+b*b+np.log(len(rows))+2*np.log(len(KINDS))))
    return dict(min(choices, key=lambda r: r['criterion']), choices=choices)


def qualify(rows, boundary, prefix_model, full_model, full_location):
    training = [r for r in rows if r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0]
    prefix_location = fit_location(training, prefix_model)
    design, counts = features(rows, prefix_model, prefix_location)
    training_mask = np.array([r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0 for r in rows])
    fitted = fit_predictor(training, prefix_model, prefix_location, design[training_mask])
    gains = {}; qualified = bool(fitted['kind'])
    if fitted['kind']:
        j = KINDS.index(fitted['kind'])
        for name, mask in [('chronological', np.array([r['validation_time_ns'] > boundary for r in rows])),
                           ('satellite_disjoint', np.array([r['validation_time_ns'] > boundary and r['norad'] % 5 == 0 for r in rows]))]:
            subset = [r for r, use in zip(rows, mask, strict=True) if use]
            old = min(cost(subset, prefix_model, prefix_location, np.zeros(len(subset)), 0.),
                      cost(subset, prefix_model, {}, np.zeros(len(subset)), 0.))
            new = cost(subset, prefix_model, prefix_location, design[mask, j], fitted['coefficient'])
            gain = old-new; penalty = np.log(len(subset))+2*np.log(len(KINDS))
            gains[name] = dict(gain=gain, penalty=float(penalty), count=len(subset))
            qualified = qualified and len(subset) >= 30 and gain > penalty
    if qualified:
        complete_design, _ = features(rows, full_model, full_location)
        # Same feature selected using only training; refit its one coefficient.
        j = KINDS.index(fitted['kind'])
        b = minimize_scalar(lambda v: cost(rows, full_model, full_location, complete_design[:, j], v)+v*v,
                            bounds=(-3., 3.), method='bounded')
        full = dict(kind=fitted['kind'], coefficient=float(b.x))
    else:
        full = dict(kind=None, coefficient=0.)
    return dict(qualified=bool(qualified), prefix_selection=fitted, prefix_location=prefix_location,
                validation=gains, full=full, training_count=len(training),
                lag_seconds=300, maximum_history_age_s=43200,
                future_targets_are_not_available_as_neighbor_features=True)
