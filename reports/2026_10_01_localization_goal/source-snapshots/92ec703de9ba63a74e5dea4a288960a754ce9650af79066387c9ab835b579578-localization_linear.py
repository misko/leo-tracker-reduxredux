"""Small shared-state solve with independent scalar nuisance coordinates.

This is an algebraic solve of an IRLS quadratic, not marginalization of a
nonlinear posterior. No branch weights are truncated. Callers retain ownership
of objective checks, state scaling, damping, and convergence decisions.
"""
from __future__ import annotations

import numpy as np


def student_t_branch_quadratics(
    residuals: np.ndarray,
    jacobians: np.ndarray,
    covariance: np.ndarray,
    probabilities: np.ndarray,
    degrees_of_freedom: float = 4.,
) -> tuple[np.ndarray, np.ndarray]:
    """Batch exact responsibility-weighted IRLS terms with one common scale.

    Input shapes are (branches, observations), (branches, observations,
    coordinates), (observations, observations), and (branches,). Return each
    branch's compact normal matrix and right-hand side. The Student-t scale
    matrix is not its covariance. Every positive probability is retained.
    """
    r, j, c, p = (np.asarray(value, dtype=float) for value in
                  (residuals, jacobians, covariance, probabilities))
    if r.ndim != 2 or j.ndim != 3 or j.shape[:2] != r.shape:
        raise ValueError("incompatible residual and Jacobian dimensions")
    n, m = r.shape
    q = j.shape[2]
    if m == 0 or q == 0 or c.shape != (m, m) or p.shape != (n,):
        raise ValueError("incompatible scale or responsibility dimensions")
    if any(not np.all(np.isfinite(value)) for value in (r, j, c, p)):
        raise ValueError("branch inputs must be finite")
    if np.any(p < 0) or p.sum() > 1 + 1e-12:
        raise ValueError("invalid branch responsibilities")
    if not np.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0:
        raise ValueError("degrees of freedom must be positive")
    if not np.allclose(c, c.T, rtol=1e-12, atol=1e-14):
        raise ValueError("Student-t scale must be symmetric")
    np.linalg.cholesky(c)
    if n == 0:
        return np.empty((0, q, q)), np.empty((0, q))
    combined = np.concatenate((r[:, :, None], j), axis=2)
    solved = np.linalg.solve(c, combined.transpose(1, 0, 2).reshape(m, -1))
    solved = solved.reshape(m, n, q+1).transpose(1, 0, 2)
    quadratic = np.einsum("nm,nm->n", r, solved[:, :, 0])
    weights = p * (degrees_of_freedom + m) / (degrees_of_freedom + quadratic)
    matrices = np.einsum("nmi,nmj,n->nij", j, solved[:, :, 1:], weights)
    gradients = np.einsum("nmi,nm,n->ni", j, solved[:, :, 0], weights)
    return matrices, gradients


def solve_diagonal_nuisance(
    shared: np.ndarray,
    coupling: np.ndarray,
    nuisance_diagonal: np.ndarray,
    rhs_shared: np.ndarray,
    rhs_nuisance: np.ndarray,
) -> np.ndarray:
    """Solve ``[[A, B], [B.T, diag(d)]] x = rhs`` without a dense big matrix.

    Requires a symmetric positive-definite system and strictly positive ``d``.
    Invalid inputs raise ValueError; an indefinite or singular reduced system
    raises LinAlgError. In particular this does not silently replace an
    unidentifiable direction with a least-squares minimum-norm solution.
    Storage is O(k*n + k*k), where k is the shared state size. Numerical
    cancellation in a poorly conditioned Schur complement remains possible;
    this primitive is not a substitute for scaled coordinates or regularization.
    """
    a, b, d, g, h = (np.asarray(value, dtype=float) for value in
                     (shared, coupling, nuisance_diagonal, rhs_shared, rhs_nuisance))
    if g.ndim != 1 or h.ndim != 1:
        raise ValueError("right-hand sides must be vectors")
    k, n = g.size, h.size
    if k == 0 or a.shape != (k, k) or b.shape != (k, n) or d.shape != (n,):
        raise ValueError("inconsistent block dimensions")
    if any(not np.all(np.isfinite(value)) for value in (a, b, d, g, h)):
        raise ValueError("system must be finite")
    if np.any(d <= 0):
        raise ValueError("nuisance precision must be strictly positive")
    if not np.allclose(a, a.T, rtol=1e-12, atol=1e-14):
        raise ValueError("shared block must be symmetric")
    weighted = b / d
    reduced = a - weighted @ b.T
    # Roundoff can break symmetry by a few ulps during block accumulation.
    reduced = 0.5 * (reduced + reduced.T)
    chol = np.linalg.cholesky(reduced)
    shared_step = np.linalg.solve(chol.T, np.linalg.solve(chol, g - weighted @ h))
    nuisance_step = (h - b.T @ shared_step) / d
    return np.concatenate((shared_step, nuisance_step))
