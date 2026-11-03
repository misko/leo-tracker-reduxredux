"""Constant-emission refresh likelihood after exact missing-row integration."""
import numpy as np


def score(log_tau, sequences):
    tau = np.exp(log_tau)
    value, gradient = 0., 0.
    for times, states, probabilities in sequences:
        times, states, p = np.asarray(times), np.asarray(states, int), np.asarray(probabilities)
        if not len(times):
            continue
        if np.any(np.diff(times) <= 0) or not np.isin(states, [1, 2, 3]).all() or p.shape != (3,) or np.any(p <= 0) or not np.isclose(p.sum(), 1.):
            raise ValueError('invalid sequence')
        value += np.log(p[states[0] - 1])
        dt = np.diff(times)
        rho = np.exp(-dt / tau)
        target = p[states[1:] - 1]
        same = states[1:] == states[:-1]
        transition = rho * same + (-np.expm1(-dt / tau)) * target
        value += np.log(transition).sum()
        gradient += np.sum(rho * dt / tau * (same - target) / transition)
    return float(value), float(gradient)
