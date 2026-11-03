"""TLE-only, orbital-geometry-dependent phase-error covariance qualification.

The elliptical Student model has exactly the incumbent univariate Student
marginals. Its single shared Gamma scale differs from independent Student
coordinates even at identity covariance, so identity and global-covariance
controls are required. TLE innovations are proxies, not measured orbit truth.
"""

import math

import numpy as np

from ds23_causal_phase_location import fit_location, predict
from ds23_shared_phase_events import event_cost as publication_cost
from learn_ds23_causal_phase_forecast import distribution_cost, select_distribution

KINDS = ('normal', 'radial_velocity')
RHOS = (0., .01, .03, .1, .3, .6, .8)
PUBLICATION_RHOS = (0., .01, .03, .1, .2, .4, .6, .8)
MINIMUM_EVENT_SIZE = 5


def orbital_features(position, velocity):
    """Unit-norm kernels in TEME; no receiver coordinate is involved."""
    r, v = np.asarray(position, float), np.asarray(velocity, float)
    if r.shape != (3,) or v.shape != (3,) or not np.isfinite(np.r_[r, v]).all():
        raise ValueError('finite three-dimensional orbital state required')
    h = np.cross(r, v)
    if min(np.linalg.norm(r), np.linalg.norm(v), np.linalg.norm(h)) <= 0:
        raise ValueError('nondegenerate orbital state required')
    return dict(normal=h/np.linalg.norm(h),
                radial_velocity=np.r_[r/np.linalg.norm(r), v/np.linalg.norm(v)]/np.sqrt(2))


def quadratic_logdet(z, features, rho):
    """Woodbury evaluation for R=(1-rho)I+rho F F', with diag(R)=1."""
    z, features = np.asarray(z, float), np.asarray(features, float)
    if (z.ndim != 1 or not len(z) or features.ndim != 2 or
            features.shape[0] != len(z) or not features.shape[1] or
            not np.isfinite(z).all() or not np.isfinite(features).all() or
            not np.isfinite(rho) or not 0 <= rho < 1 or
            not np.allclose(np.sum(features**2, axis=1), 1., atol=1e-12, rtol=1e-12)):
        raise ValueError('finite aligned unit-norm feature rows and rho in [0,1) required')
    if rho == 0:
        return float(z@z), 0.
    a = 1-rho
    small = np.eye(features.shape[1])+(rho/a)*(features.T@features)
    projected = features.T@z
    quadratic = (z@z)/a-rho/(a*a)*(projected@np.linalg.solve(small, projected))
    sign, logdet_small = np.linalg.slogdet(small)
    if sign != 1 or quadratic < -1e-9*max(float(z@z), 1.):
        raise ValueError('invalid positive definite covariance')
    return max(float(quadratic), 0.), float(len(z)*np.log(a)+logdet_small)


def joint_cost(z, features, rho, nu):
    """Normalized -2 log density, parameterized by unit marginal variance."""
    quadratic, logdet = quadratic_logdet(z, features, rho)
    n = len(z)
    if nu is None:
        return float(quadratic+logdet+n*np.log(2*np.pi))
    if not np.isfinite(nu) or nu <= 2:
        raise ValueError('Student degrees of freedom must exceed two')
    return float(n*np.log((nu-2)*np.pi)+logdet+2*math.lgamma(nu/2)
                 -2*math.lgamma((nu+n)/2)+(nu+n)*np.log1p(quadratic/(nu-2)))


def independent_cost(z, nu):
    return float(distribution_cost(z, np.ones(len(z)), 1., nu).sum())


def make_events(rows, model, location):
    groups = {}
    for row in rows:
        groups.setdefault(row['validation_time_ns'], []).append(row)
    result = []
    for stamp, values in sorted(groups.items()):
        if len({r['norad'] for r in values}) != len(values):
            raise ValueError('one innovation per satellite per validation event required')
        if len(values) < MINIMUM_EVENT_SIZE:
            continue
        sigma = np.array([r['predicted_sigma_s'] for r in values])*model['multiplier']
        if not np.isfinite(sigma).all() or np.any(sigma <= 0):
            raise ValueError('positive finite marginal standard deviations required')
        mean = predict(values, model, location.get('kind'), location.get('coefficient', 0.))
        z = (np.array([r['next_innovation_s'] for r in values])-mean)/sigma
        result.append(dict(time_ns=stamp, z=z,
                           publication=np.array([r['forecast_publication_ns'] for r in values]),
                           **{kind: np.array([r[kind] for r in values]) for kind in KINDS}))
    return result


def total(events, kind, rho, nu):
    return float(sum(joint_cost(e['z'], np.ones((len(e['z']), 1)) if kind == 'global'
                                else e[kind], rho, nu) for e in events))


def old_publication_total(events, rho, nu):
    value = 0.
    for e in events:
        for stamp in np.unique(e['publication']):
            value += publication_cost(e['z'][e['publication'] == stamp], rho, nu)
    return float(value)


def fit_geometry(events, nu, kinds=KINDS):
    count = sum(len(e['z']) for e in events)
    penalty = np.log(max(count, 1))+2*np.log(len(KINDS))
    choices = [dict(kind=kind, rho=rho, cost=total(events, kind, rho, nu))
               for kind in kinds for rho in RHOS]
    for choice in choices:
        choice['criterion'] = choice['cost']+(penalty if choice['rho'] else 0.)
    return dict(min(choices, key=lambda c: c['criterion']), choices=choices)


def fit_controls(events, nu):
    count = sum(len(e['z']) for e in events)
    penalty = np.log(max(count, 1))
    publication = min((dict(rho=rho, cost=old_publication_total(events, rho, nu))
                       for rho in PUBLICATION_RHOS),
                      key=lambda c: c['cost']+(penalty if c['rho'] else 0.))
    global_model = min((dict(rho=rho, cost=total(events, 'global', rho, nu)) for rho in RHOS),
                       key=lambda c: c['cost']+(penalty if c['rho'] else 0.))
    return dict(publication=publication, global_model=global_model)


def evaluate(events, nu, selected, controls):
    count = sum(len(e['z']) for e in events)
    model = total(events, selected['kind'], selected['rho'], nu)
    costs = dict(independent=sum(independent_cost(e['z'], nu) for e in events),
                 common_Gamma_identity=total(events, 'normal', 0., nu),
                 old_publication=old_publication_total(events, controls['publication']['rho'], nu),
                 common_Gamma_global=total(events, 'global', controls['global_model']['rho'], nu))
    return dict(count=count, events=len(events), model_cost=model, control_costs=costs,
                gains={name: float(cost-model) for name, cost in costs.items()},
                penalty=float(np.log(max(count, 1))+2*np.log(len(KINDS))))


def qualify(rows, boundary, full_model, full_location):
    """Train on earlier batches/nonheld satellites; test later whole batches.

    The marginal and location prefix models are also fitted without the held
    satellites. Full-data marginal priors are the already-qualified incumbent;
    only covariance strength is refitted after dependency qualification.
    """
    training = [r for r in rows if r['validation_time_ns'] <= boundary and r['norad'] % 5 != 0]
    future = [r for r in rows if r['validation_time_ns'] > boundary]
    disjoint = [r for r in future if r['norad'] % 5 == 0]
    if min(map(len, (training, future, disjoint))) < 30:
        return dict(qualified=False, reason='insufficient temporal and satellite-disjoint transitions')
    prefix_model = select_distribution(training)
    prefix_location = fit_location(training, prefix_model)
    events = make_events(training, prefix_model, prefix_location)
    later = make_events(future, prefix_model, prefix_location)
    held = make_events(disjoint, prefix_model, prefix_location)
    if len(events) < 3 or min(len(later), len(held)) < 2:
        return dict(qualified=False, reason='fewer than three training or two later whole events',
                    event_counts=dict(training=len(events), chronological=len(later), disjoint=len(held)))
    fitted = fit_geometry(events, prefix_model['nu'])
    controls = fit_controls(events, prefix_model['nu'])
    checks = {name: evaluate(part, prefix_model['nu'], fitted, controls)
              for name, part in [('training', events), ('chronological', later), ('satellite_disjoint', held)]}
    qualified = bool(fitted['rho'] and all(v['count'] >= 30 and
                     min(v['gains'].values()) > v['penalty'] for v in checks.values()))
    complete = None
    if qualified:
        all_events = make_events(rows, full_model, full_location)
        complete = fit_geometry(all_events, full_model['nu'], (fitted['kind'],))
        qualified = bool(complete['rho'])
    return dict(qualified=qualified, prefix_model=prefix_model, prefix_location=prefix_location,
                prefix_selection=fitted, controls=controls, validation=checks, all_past=complete,
                selected_kind=complete['kind'] if qualified else None,
                selected_rho=complete['rho'] if qualified else 0.,
                train_and_validation_update_batches_disjoint=True,
                held_satellites_excluded_from_marginal_location_and_covariance_training=True,
                univariate_Student_marginals_unchanged=True,
                common_Gamma_tail_dependence_control_explicit=True,
                no_RF_GPS_or_future_elements_input=True)
