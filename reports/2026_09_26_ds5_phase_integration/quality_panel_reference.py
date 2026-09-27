"""Observation-centered offset integration, independent of history compression.

Panel placement is numerical integration only: it changes neither the prior nor
the prefix likelihood. Prefix consistency under future-data changes is tested.
"""
import numpy as np
from scipy.special import logsumexp, roots_legendre


def log_integrand(beta, residual, scales, times, flags, kind):
    beta = np.atleast_1d(beta)
    scales = np.asarray(scales)
    q = len(scales)
    state = np.full((len(beta), q), -np.log(q))
    prior = -.5 * (beta / 1e6)**2 - np.log(1e6 * np.sqrt(2*np.pi))
    out = []
    for i, r in enumerate(residual):
        h = 0. if not i or kind == 'stationary' else -np.expm1(-(times[i]-times[i-1])/20.)
        if i and kind == 'timing_informed' and flags[i-1]:
            h = 1 - (1-h)*.5
        if h:
            state = np.logaddexp(state+np.log1p(-h), logsumexp(state, axis=-1, keepdims=True)+np.log(h/q))
        state += -.5*((r-beta[:, None])/scales)**2 - np.log(scales*np.sqrt(2*np.pi))
        out.append(prior + logsumexp(state, axis=-1))
    return np.stack(out, axis=-1)


def panel_evidence(residual, scales, times, flags, kind, order=8, tail=12):
    residual = np.asarray(residual)
    scales = np.asarray(scales)
    # Every conditional Gaussian history mean is inside the data range up to
    # the tiny broad-prior shrinkage. Resolve the narrowest possible posterior.
    widths = np.unique(np.r_[scales, scales/np.sqrt(len(residual)),
                             scales.max()*np.array([2.,4.,8.,float(tail)])])
    knots = np.unique(np.r_[(residual[:, None]+widths).ravel(),
                            (residual[:, None]-widths).ravel(), residual,
                            residual.min()-tail*scales.max(), residual.max()+tail*scales.max()])
    x, w = roots_legendre(order)
    half = np.diff(knots)/2
    beta = ((knots[:-1]+half)[:, None]+half[:, None]*x).ravel()
    weights = np.log((half[:, None]*w).ravel())
    values = []
    for first in range(0, len(beta), 2048):
        values.append(logsumexp(log_integrand(beta[first:first+2048], residual, scales, times, flags, kind)+weights[first:first+2048, None], axis=0))
    return logsumexp(values, axis=0), len(beta)
