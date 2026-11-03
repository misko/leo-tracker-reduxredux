"""Conditional RX-state calibration; no absolute presence claims."""
import numpy as np
from scipy.special import logsumexp


def design(los, rf_index, rf_count, arm):
    los = np.asarray(los, float)
    rf_index = np.asarray(rf_index, int)
    if los.shape != (len(rf_index), 3) or arm not in ('receiver', 'elevation', 'signed', 'swapped'):
        raise ValueError('invalid design')
    x = np.zeros((len(los), 2, 2 * rf_count + (arm != 'receiver')))
    for r in (0, 1):
        x[np.arange(len(los)), r, 2 * rf_index + r] = 1.
    if arm != 'receiver':
        if arm == 'elevation':
            x[:, :, -1] = los[:, 2, None]
        else:
            angle = np.radians(10.)
            east = np.array([-1., 1.]) * (1. if arm == 'signed' else -1.)
            x[:, :, -1] = np.cos(angle) * los[:, 2, None] + np.sin(angle) * los[:, 0, None] * east
    return x


def score_gradient(parameters, x, states):
    """Return per-observation log probability and summed analytic gradient."""
    parameters = np.asarray(parameters, float)
    x = np.asarray(x, float)
    states = np.asarray(states, int)
    if x.ndim != 3 or x.shape[1:] != (2, len(parameters)) or states.shape != (len(x),) or not np.isin(states, [1, 2, 3]).all():
        raise ValueError('expected known, nonempty receiver states')
    features = np.stack((x[:, 0], x[:, 1], x[:, 0] + x[:, 1]), axis=1)
    weights = features @ parameters
    norm = logsumexp(weights, axis=1)
    probabilities = np.exp(weights - norm[:, None])
    scores = weights[np.arange(len(x)), states - 1] - norm
    gradient = (features[np.arange(len(x)), states - 1] - np.einsum('ns,nsp->np', probabilities, features)).sum(axis=0)
    return scores, gradient
