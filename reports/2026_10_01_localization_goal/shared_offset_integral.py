"""Shared versus independent offset expectations on the alias circle."""
import math

import numpy as np


def logsumexp(values, axis=None):
    maximum = np.max(values, axis=axis, keepdims=True)
    out = maximum+np.log(np.sum(np.exp(values-maximum), axis=axis, keepdims=True))
    return np.squeeze(out, axis=axis)


def integrate(groups, offset_scale, df, noise_scale, probability, order=12):
    if not groups:
        return dict(shared=0., independent=0., prior_mass=1., nodes=0, tail_relative_bound=0.)
    period = groups[0]['period_hz']
    assert all(g['period_hz'] == period for g in groups)
    assert offset_scale > 0 and noise_scale > 0 and df > 2 and 0 <= probability <= 1
    # Split at every candidate peak and around its intrinsic width, plus a
    # geometric grid covering the offset prior. Resolve distant alias modes.
    centers = np.concatenate([g['residuals_hz'] for g in groups])
    cuts = np.r_[0., (offset_scale*np.array([-1., 1.])[:, None]*2.**np.arange(-3, 10)).ravel(),
                 (centers[:, None]+noise_scale*np.array([-8., -2., -.5, 0., .5, 2., 8.])).ravel()]
    cuts = np.unique(np.r_[-period/2, (cuts+period/2) % period-period/2, period/2])
    abscissa, weights = np.polynomial.legendre.leggauss(order)
    half, midpoint = np.diff(cuts)/2, (cuts[1:]+cuts[:-1])/2
    nodes = (midpoint[:, None]+half[:, None]*abscissa).ravel()
    quadrature = (half[:, None]*weights).ravel()
    log_constant = math.lgamma((df+1)/2)-math.lgamma(df/2)-.5*math.log(df*np.pi)-math.log(offset_scale)
    terms = [log_constant-(df+1)/2*np.log1p(((nodes+k*period)/offset_scale)**2/df)
             for k in range(-8, 9)]
    prior = logsumexp(np.array(terms), axis=0)
    # Power-law envelope bounds all omitted wrapped Student-t copies.
    k = 8.5
    log_tail = (math.log(2)+log_constant+(df+1)/2*math.log(df)
        +(df+1)*math.log(offset_scale/period)
        +math.log(k**(-df-1)+k**(-df)/df))
    relative_bound = float(np.exp(log_tail-np.min(prior)))
    assert relative_bound < 1e-8
    log_weights = np.log(quadrature)+prior
    prior_mass = float(np.exp(logsumexp(log_weights)))
    log_ratios = []
    a = 2*np.pi*noise_scale/period
    for g in groups:
        residual = np.asarray(g['residuals_hz'])[:, None]-nodes
        phase = ((residual+period/2) % period-period/2)*np.pi/period
        ratio = -np.expm1(-2*a)/(np.expm1(-a)**2+4*np.exp(-a)*np.sin(phase)**2)
        log_ratios.append(np.log((1-probability)+probability*ratio.mean(axis=0)))
    log_ratios = np.asarray(log_ratios)
    return dict(shared=float(logsumexp(log_weights+log_ratios.sum(axis=0))),
        independent=float(np.sum(logsumexp(log_weights+log_ratios, axis=1))),
        prior_mass=prior_mass, nodes=len(nodes), tail_relative_bound=relative_bound)
