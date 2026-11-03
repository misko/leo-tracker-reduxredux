"""Local Gaussian quadrature of exp(-score/2), not a calibrated posterior.

The region has uniform area measure. No geographic target enters integration.
Numerical convergence and locality must be checked before using the mean.
"""

import numpy as np
from scipy.special import logsumexp


def local_covariance(score, anchor, step=.1):
    x = np.asarray(anchor, float)
    if x.shape != (2,) or not np.isfinite(x).all() or step <= 0:
        raise ValueError('finite two-dimensional anchor and positive step required')
    hessian = np.zeros((2, 2)); centre = score(x)
    directions = np.eye(2) * step
    for k in range(2):
        hessian[k, k] = (score(x+directions[k])+score(x-directions[k])-2*centre)/step**2
    a, b = directions
    hessian[0, 1] = hessian[1, 0] = (score(x+a+b)-score(x+a-b)-score(x-a+b)+score(x-a-b))/(4*step**2)
    if np.linalg.eigvalsh(hessian).min() <= 0:
        raise ValueError('local score curvature is not positive definite')
    return 2 * np.linalg.inv(hessian)


def score_integral(score, anchor, covariance, order, half_width=12.5):
    x, covariance = np.asarray(anchor, float), np.asarray(covariance, float)
    if x.shape != (2,) or covariance.shape != (2, 2) or order < 3 or half_width <= 0:
        raise ValueError('two-dimensional geometry, order >=3 and positive region required')
    root = np.linalg.cholesky(covariance)
    nodes, weights = np.polynomial.hermite.hermgauss(order)
    coordinates, terms, records = [], [], []
    centre = float(score(x))
    for i in range(order):
        for j in range(order):
            z = np.sqrt(2) * np.array([nodes[i], nodes[j]])
            position = x + root @ z
            if np.any(abs(position) > half_width): continue
            value = float(score(position))
            if not np.isfinite(value): raise ValueError('nonfinite spatial score')
            term = np.log(weights[i]*weights[j]/np.pi) - .5*(value-centre) + .5*(z@z)
            coordinates.append(position); terms.append(term)
            records.append(dict(position=position, score=value, outer_ring=bool(i in (0, order-1) or j in (0, order-1))))
    if not terms: raise ValueError('quadrature has no regional support')
    logmass = float(logsumexp(terms)); mass = np.exp(np.asarray(terms)-logmass)
    positions = np.asarray(coordinates); mean = mass @ positions
    delta = positions-mean
    return dict(mean=mean, covariance=(delta.T*mass)@delta, log_relative_mass=logmass,
        order=order, maximum_node_weight=float(mass.max()),
        outer_ring_mass=float(sum(w for w, r in zip(mass, records, strict=True) if r['outer_ring'])),
        nodes=records, weights=mass)
