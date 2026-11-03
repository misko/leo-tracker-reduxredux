"""Exact Gaussian shared-nuisance integration for fixed linearized hypotheses.

Each block obeys r_i = H_i b + e_i, with independent e_i ~ N(0, C_i)
and one shared b ~ N(0, diag(sigma**2)). The result integrates b once across
all blocks. It is not the marginal likelihood of a Student-t IRLS surrogate,
nor does it integrate satellite identities or nonlinear location uncertainty.
"""
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class GaussianNuisanceEvidence:
    log_likelihood: float
    nuisance_mean: NDArray[np.float64]
    whitened_information_cholesky: NDArray[np.float64]


def integrate_shared_gaussian(
    blocks: Sequence[tuple[NDArray, NDArray, NDArray]],
    nuisance_sigma: NDArray,
) -> GaussianNuisanceEvidence:
    """Return normalized joint evidence and conditional nuisance mean.

Blocks contain residual, nuisance design, and noise covariance. Prior
whitening makes the reduced information dimensionless; no large stacked
observation covariance is constructed. Cholesky failures remain explicit.
"""
    sigma = np.asarray(nuisance_sigma, dtype=float)
    if sigma.ndim != 1 or not np.all(np.isfinite(sigma)) or np.any(sigma <= 0):
        raise ValueError('nuisance scales must be finite positive vector')
    information = np.eye(sigma.size)
    gradient = np.zeros(sigma.size)
    whitened_blocks = []
    logdet_noise = 0.
    count = 0
    for residual, design, covariance in blocks:
        r, h, c = (np.asarray(a, dtype=float) for a in (residual, design, covariance))
        if (r.ndim != 1 or h.shape != (r.size, sigma.size)
                or c.shape != (r.size, r.size) or r.size == 0
                or not all(np.all(np.isfinite(a)) for a in (r, h, c))
                or not np.allclose(c, c.T, rtol=1e-12, atol=1e-12)):
            raise ValueError('invalid Gaussian residual block')
        chol = np.linalg.cholesky(c)
        white_r = np.linalg.solve(chol, r)
        white_h = np.linalg.solve(chol, h*sigma)
        information += white_h.T@white_h
        gradient += white_h.T@white_r
        whitened_blocks.append((white_r, white_h))
        logdet_noise += float(2*np.log(np.diag(chol)).sum())
        count += r.size
    if count == 0:
        raise ValueError('at least one residual block is required')
    chol_info = np.linalg.cholesky(information)
    solved = np.linalg.solve(chol_info, gradient)
    posterior_white = np.linalg.solve(chol_info.T, solved)
    # Evaluate the completed square as a sum of squares, avoiding catastrophic
    # cancellation when a broad nuisance prior explains almost all residual.
    marginalized_quadratic = float(posterior_white@posterior_white)
    for white_r, white_h in whitened_blocks:
        remainder = white_r-white_h@posterior_white
        marginalized_quadratic += float(remainder@remainder)
    log_likelihood = -.5*(count*np.log(2*np.pi)+logdet_noise
                         +2*np.log(np.diag(chol_info)).sum()
                         +marginalized_quadratic)
    return GaussianNuisanceEvidence(float(log_likelihood), sigma*posterior_white, chol_info)
