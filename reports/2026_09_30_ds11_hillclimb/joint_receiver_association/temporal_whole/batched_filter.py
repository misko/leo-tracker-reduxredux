"""Conditional source-sequence filtering for different subset window supports."""
import numpy as np


def filter_subsets(times, logp, states, observed, tau_s, derivatives):
    times, states, observed = np.asarray(times), np.asarray(states), np.asarray(observed, bool)
    if logp.shape[:2] != states.shape or logp.shape[2] != 3 or derivatives.shape[:-1] != logp.shape or len(times) != states.shape[1] or observed.shape != times.shape or tau_s < 0 or not np.isfinite(tau_s):
        raise ValueError('invalid subset filter design')
    if np.any(np.diff(times) < 0) or not np.isin(states, [0, 1, 2, 3]).all():
        raise ValueError('invalid times or states')
    n, dimensions = len(states), derivatives.shape[-1]
    alpha, da = np.zeros((n, 3)), np.zeros((n, 3, dimensions))
    last = np.full(n, np.nan)
    score, gradient = np.zeros(n), np.zeros((n, dimensions))
    for j, t in enumerate(times):
        active = np.flatnonzero(states[:, j] > 0)
        if not len(active):
            continue
        p = np.exp(logp[active, j])
        dp = p[..., None] * derivatives[active, j]
        first = np.isnan(last[active])
        rho = np.zeros(len(active))
        if tau_s:
            rho[~first] = np.exp(-(t - last[active[~first]]) / tau_s)
        alpha[active] = rho[:, None] * alpha[active] + (1 - rho[:, None]) * p
        da[active] = rho[:, None, None] * da[active] + (1 - rho[:, None, None]) * dp
        last[active] = t
        if observed[j]:
            state = states[active, j] - 1
            value = alpha[active, state]
            if np.any(value <= 0):
                raise ValueError('unsupported state')
            score[active] += np.log(value)
            gradient[active] += da[active, state] / value[:, None]
            alpha[active] = 0.
            alpha[active, state] = 1.
            da[active] = 0.
    return score, gradient
