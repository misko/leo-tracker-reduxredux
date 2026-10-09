"""Local affine observed mixture curvature; fixed visibility and wrapped branches.

Allow at most 1e-12 probability-sum excess for float64 normalization roundoff.
Accepted probabilities are used unchanged: no renormalization or eigenvalue clipping.
"""

import numpy as np


def curvature(prediction_jacobian, residual_hz, responsibilities, sigma_hz):
    jacobian = np.asarray(prediction_jacobian, float)
    residual = np.asarray(residual_hz, float)
    probability = np.asarray(responsibilities, float)
    if (
        jacobian.ndim != 3
        or residual.shape != jacobian.shape[:2]
        or probability.shape != residual.shape
        or jacobian.shape[0] == 0
        or jacobian.shape[1] == 0
        or jacobian.shape[2] == 0
        or not np.isfinite(jacobian).all()
        or not np.isfinite(residual).all()
        or not np.isfinite(probability).all()
        or np.any(probability < 0)
        or np.any(probability.sum(axis=1) > 1 + 1e-12)
        or not np.isscalar(sigma_hz)
        or not np.isfinite(sigma_hz)
        or sigma_hz <= 0
    ):
        raise ValueError(
            "Finite Jacobians/residuals, subprobability responsibilities "
            "and positive sigma required"
        )
    complete = np.einsum("nk,nkp,nkq->pq", probability, jacobian, jacobian) / sigma_hz**2
    scores = residual[:, :, None] * jacobian / sigma_hz**2
    mean = np.einsum("nk,nkp->np", probability, scores)
    missing = np.einsum("nk,nkp,nkq->pq", probability, scores, scores) - mean.T @ mean
    return dict(complete=complete, missing_information=missing, observed_local=complete - missing)
