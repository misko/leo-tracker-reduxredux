"""Use one triangular solve for a selected grid point's predictive rows."""

import numpy as np
from scipy.linalg import solve_triangular

from leo.analysis.localization_v3.predictive_linear import conditional_gaussian, predictive_residual


def triangular_prediction(raw, design, curved_gram, sigma, groups, bias_sigma=300.0):
    """Evaluate the same conditional likelihood without LU-factorizing its known root."""
    y, u = np.asarray(raw, float), np.asarray(design, float)
    gram = np.asarray(curved_gram, float)
    g = np.asarray(groups)
    if (u.ndim != 2 or gram.shape != (u.shape[1], u.shape[1]) or g.shape != y.shape
            or not np.issubdtype(g.dtype, np.integer) or np.any(g < 0) or not len(g)):
        return predictive_residual(raw, design, curved_gram, sigma, groups, bias_sigma)
    root = np.linalg.cholesky(gram)
    # The original solve computes L^-1 U' for all prediction rows at once.
    # Passing the known triangular structure keeps the same system and avoids LU.
    uncertainty = solve_triangular(root, u.T, lower=True, check_finite=False).T
    biases = np.zeros((len(y), int(g.max()) + 1))
    biases[np.arange(len(y)), g] = bias_sigma
    features = np.column_stack((uncertainty, biases))
    return conditional_gaussian(
        y, features, np.asarray(sigma, float), np.ones(len(y)), np.ones(len(y)),
        np.ones(features.shape[1]), 1.0,
    )
