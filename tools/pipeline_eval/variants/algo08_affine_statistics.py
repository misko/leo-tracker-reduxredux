"""Reuse conditional normal blocks across site trials within one geometry patch."""

import numpy as np
from scipy.linalg import cho_factor, cho_solve


class AffineScore:
    """Gaussian marginal score with fixed weights/priors and a local affine design."""

    def __init__(self, terms, sigma, weights, prior):
        terms, sigma, weights, prior = map(np.asarray, (terms, sigma, weights, prior))
        if (terms.ndim != 3 or terms.shape[0] != 3 or terms.shape[2] != len(prior) + 1
                or sigma.shape != (terms.shape[1],) or weights.shape != sigma.shape
                or np.any(sigma <= 0) or np.any(weights < 0) or np.any(prior <= 0)
                or not all(np.isfinite(a).all() for a in (terms, sigma, weights, prior))):
            raise ValueError("Three finite affine row terms, fixed noise, weights, and priors required")
        blocks = terms * (np.sqrt(weights) / sigma)[None, :, None]
        base, east, north = blocks
        ee, nn, en = east.T @ east, north.T @ north, east.T @ north
        e0, n0 = east.T @ base, north.T @ base
        self.normal = np.stack((base.T @ base, e0 + e0.T, n0 + n0.T,
                                ee, en + en.T, nn))
        self.prior = prior.copy()
        self.prior_log = np.log(prior).sum()

    def normal_at(self, east, north):
        powers = np.array([1., east, north, east*east, east*north, north*north])
        width = len(self.prior) + 1
        return (powers @ self.normal.reshape(6, -1)).reshape(width, width)

    def score(self, east, north):
        g = self.normal_at(east, north)
        matrix = g[:-1, :-1] + np.diag(self.prior)
        rhs = g[:-1, -1]
        root = cho_factor(matrix, lower=True)
        beta = cho_solve(root, rhs)
        volume = 2 * np.log(np.diag(root[0])).sum() - self.prior_log
        return float(g[-1, -1] - rhs @ beta + volume)
