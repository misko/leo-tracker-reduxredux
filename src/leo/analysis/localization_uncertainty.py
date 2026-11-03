"""Local quadratic geometry helpers, without a calibration claim."""
import numpy as np


def profiled_position_covariance(information):
    """Invert the position Schur complement, profiling all later coordinates.

The first two coordinates are position. The caller owns the information
approximation and its units. An IRLS input produces an inverse IRLS curvature,
not an exact posterior covariance or a calibrated confidence region.
"""
    matrix = np.asarray(information, dtype=float)
    if (matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]
            or matrix.shape[0] < 2 or not np.all(np.isfinite(matrix))
            or not np.allclose(matrix, matrix.T, rtol=1e-10, atol=1e-12)):
        raise ValueError('invalid symmetric information matrix')
    reduced = matrix[:2, :2].copy()
    if matrix.shape[0] > 2:
        chol_nuisance = np.linalg.cholesky(matrix[2:, 2:])
        coupling = np.linalg.solve(chol_nuisance, matrix[2:, :2])
        reduced -= coupling.T@coupling
    reduced = .5*(reduced+reduced.T)
    chol = np.linalg.cholesky(reduced)
    inverse_chol = np.linalg.solve(chol, np.eye(2))
    return inverse_chol.T@inverse_chol
