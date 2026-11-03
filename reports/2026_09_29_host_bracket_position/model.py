"""Box parameterization for measured capture brackets plus one common bias."""

import numpy as np


def unpack(z):
    z = np.asarray(z, float)
    return np.r_[z[:2], z[2] + z[3:]]


def chain(gradient):
    g = np.asarray(gradient, float)
    return np.r_[g[:2], g[2:].sum(), g[2:]]


def bounds(lower, upper):
    return (
        [(-12.0, 12.0)] * 2
        + [(-5.0 - min(lower), 5.0 - max(upper))]
        + list(zip(lower, upper, strict=True))
    )


def projected_gradient(x, g, limits):
    g = np.asarray(g).copy()
    for i, (lo, hi) in enumerate(limits):
        if (x[i] <= lo + 1e-8 and g[i] > 0) or (x[i] >= hi - 1e-8 and g[i] < 0):
            g[i] = 0
    return float(np.max(abs(g)))
