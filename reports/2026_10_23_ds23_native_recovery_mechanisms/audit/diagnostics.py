"""Dense audit of native prediction at a caller-fixed phase linearization."""
import numpy as np


def dense_prediction(raw, features, coefficient_covariance, sigma, groups, bias_sigma=300.):
    """Joint Gaussian prediction, including covariance between distinct entries."""
    y = np.asarray(raw, float)
    u = np.asarray(features, float)
    c = np.asarray(coefficient_covariance, float)
    s = np.asarray(sigma, float)
    g = np.asarray(groups, int)
    covariance = np.diag(s*s) + u @ c @ u.T
    covariance += bias_sigma**2 * (g[:, None] == g[None, :])
    sign, logdet = np.linalg.slogdet(covariance)
    if sign <= 0:
        raise ValueError('predictive covariance must be positive definite')
    quadratic = float(y @ np.linalg.solve(covariance, y))
    normalization = float(len(y)*np.log(2*np.pi))
    return dict(predictive_quadratic=quadratic, predictive_logdet=float(logdet),
                predictive_normalization=normalization,
                predictive_objective=quadratic+float(logdet)+normalization,
                raw_residual_hz=y, covariance_hz2=covariance)


def decompose(p, position, powers):
    """Replay existing native objective; never updates phase reference or fits."""
    from ds23_predictive_linear import linear_geometry
    from ds23_height_problem import geometry_features
    from ds23_frequency_events import event_design
    x = np.asarray(position, float)
    full = p.calculate(x)
    curved = p.curved_calculate(x) if hasattr(p, 'curved_calculate') else full
    entries = getattr(p, 'linear_entries', [])
    curved_objective = float(curved['negative_twice_elbo'])
    if not entries:
        return dict(curved_objective=curved_objective, predictive_quadratic=0.,
                    predictive_logdet=0., predictive_normalization=0.,
                    predictive_objective=0., total_objective=curved_objective,
                    raw_residual_hz=np.empty(0), covariance_hz2=np.empty((0, 0)),
                    entry_slices=[], replay_difference=curved_objective-float(full['negative_twice_elbo']))
    view, values, sigma, groups, slices = linear_geometry(p, entries)
    geometry = geometry_features(view, x, 0.)
    features = geometry['features']
    events = getattr(p, 'events', [])
    if events:
        rx = np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']), p.scan.tracks[e['track_index']]['receiver']) for e in entries])
        ch = np.concatenate([np.full(len(p.scan.tracks[e['track_index']]['times']), p.scan.tracks[e['track_index']]['channel']) for e in entries])
        labels = np.asarray(p.labels)[view.flat_labels]
        features = np.column_stack((features, event_design(view.flat_times, rx, ch, view.q*11.5e9, labels, events)))
    g = p.noise_groups[p.keep]
    weights = np.asarray(powers)[g]*curved['noise_precision'][g]/p.point_noise[p.keep]**2
    train = curved['features'][p.keep]
    gram = np.diag(curved['coefficient_prior_precision']) + train.T @ (train*weights[:, None])
    raw = values-view.q*geometry['intercept']-features@curved['coefficient']
    result = dense_prediction(raw, features, np.linalg.inv(gram), sigma*np.sqrt(2), groups)
    result.update(curved_objective=curved_objective,
                  total_objective=curved_objective+result['predictive_objective'],
                  entry_slices=[(int(s.start), int(s.stop)) for s in slices],
                  groups=groups, features=features, coefficient_covariance=np.linalg.inv(gram))
    result['replay_difference'] = result['total_objective']-float(full['negative_twice_elbo'])
    if abs(result['replay_difference']) > 2e-5:
        raise ValueError('dense native objective does not replay: '+str(result['replay_difference']))
    return result


def conditional_gradients(p, position, powers, step_km=.001):
    """Symmetric E/N derivatives; phase reference fixed, nuisance recomputed."""
    if step_km <= 0:
        raise ValueError('positive finite-difference step required')
    keys = ('curved_objective', 'predictive_quadratic', 'predictive_logdet',
            'predictive_normalization', 'predictive_objective', 'total_objective')
    gradients = {key: [] for key in keys}
    x = np.asarray(position, float)
    for axis in range(2):
        delta = np.zeros(2); delta[axis] = step_km
        plus, minus = decompose(p, x+delta, powers), decompose(p, x-delta, powers)
        for key in keys:
            gradients[key].append((plus[key]-minus[key])/(2*step_km))
    return dict(kind='conditional fixed-phase symmetric east/north gradients',
                units='objective per km', step_km=step_km, gradients=gradients)
