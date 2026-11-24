"""Research-only predictor that forms moments before posterior whitening."""

import numpy as np
from scipy.linalg import cho_solve, cholesky
from scipy.linalg.blas import dsyrk
from scipy.linalg.lapack import dpocon


PRECISION_FLOOR = np.sqrt(np.finfo(np.float64).eps)


def predictive_precision(raw, design, sigma, groups, capture, member_count, *, check_condition=False):
    """Apply the determinant lemma after eliminating each group's bias.

    In the exported order let P = LLᵀ, R = design / sigma, r = raw / sigma,
    and B contain the scaled bias column for each curve. The coefficient
    system is K = P + RᵀR - RᵀB (I + BᵀB)⁻¹ BᵀR.
    """
    if (not 0 < member_count <= capture.width or not len(raw)
            or groups.shape != raw.shape or sigma.shape != raw.shape
            or not np.issubdtype(groups.dtype, np.integer) or groups[0] < 0
            or np.any(groups[1:] < groups[:-1]) or np.any(sigma <= 0)):
        raise ValueError("Incompatible posterior or predictive rows")

    order = capture.order
    lower = np.tril(capture.lower)
    starts = np.r_[0, 1 + np.flatnonzero(groups[1:] != groups[:-1])]
    counts = np.diff(np.r_[starts, len(raw)])
    inverse = 1. / sigma
    bias = 300. * inverse
    values = raw * inverse
    rows = np.asfortranarray(design[:, order])
    rows[:, order >= capture.width - member_count] *= .3
    rows *= inverse[:, None]

    bias_norm = np.add.reduceat(bias * bias, starts)
    bias_root = np.sqrt(1. + bias_norm)
    curve_design = np.add.reduceat(rows * bias[:, None], starts, axis=0)
    curve_values = np.add.reduceat(values * bias, starts)
    curve_design /= bias_root[:, None]
    curve_values /= bias_root

    gram = dsyrk(1., lower, lower=1)
    gram = dsyrk(1., rows, beta=1., c=gram, trans=1, lower=1, overwrite_c=1)
    diagonal = gram.diagonal().copy() if check_condition else None
    gram = dsyrk(-1., curve_design, beta=1., c=gram, trans=1, lower=1, overwrite_c=1)
    root = cholesky(gram, lower=True, check_finite=True)
    if check_condition:
        if np.any(gram.diagonal() <= PRECISION_FLOOR * diagonal):
            raise ValueError("Predictive bias subtraction loses the diagonal precision margin")
        # Bound the full symmetric 1-norm using the original computed triangle.
        triangle = np.abs(np.tril(gram))
        norm = max(triangle.sum(axis=0) + triangle.sum(axis=1) - triangle.diagonal())
        reciprocal, info = dpocon(root, norm, uplo="L")
        if info or not np.isfinite(reciprocal) or reciprocal < PRECISION_FLOOR:
            raise ValueError("Poorly conditioned predictive coefficient system")
    coefficient = cho_solve((root, True), rows.T @ values - curve_design.T @ curve_values,
                            check_finite=True)
    # Keep the published residual in the original whitened coordinate system.
    rotated = lower.T @ coefficient
    innovation = values - rows @ coefficient
    cross = np.add.reduceat(innovation * bias, starts)
    innovation -= bias * np.repeat(cross / (bias_root * (bias_root + 1.)), counts)
    volume = float(np.log1p(bias_norm).sum()
                   + 2 * (np.log(root.diagonal()) - np.log(lower.diagonal())).sum())
    normalization = float(np.sum(np.log(2 * np.pi) + 2 * np.log(sigma)))
    objective = float(innovation @ innovation + rotated @ rotated + volume + normalization)
    if not np.isfinite(objective) or volume < 0:
        raise ValueError("Non-finite or negative predictive volume")
    return dict(objective=objective, normalization_constant=normalization,
                residual=np.r_[innovation, rotated, np.sqrt(volume)])


def guarded_predictor(incumbent, counts):
    """Restrict the option to the incumbent's complete, checked grid operands."""
    def evaluate(raw, design, sigma, groups, capture, member_count, *, include_residual=False):
        if include_residual and capture.valid():
            # The original compact residual omits a structural zero prefix.
            if not np.any(design[:, capture.order[0]]):
                counts["original_compact_layout"] += 1
            else:
                try:
                    result = predictive_precision(raw, design, sigma, groups, capture, member_count,
                                                  check_condition=True)
                except (ValueError, ArithmeticError, np.linalg.LinAlgError):
                    counts["rejected_or_unsupported"] += 1
                else:
                    counts["precision"] += 1
                    return result, dict(prefix=0, biases=1 + np.count_nonzero(groups[1:] != groups[:-1]))
        counts["incumbent"] += 1
        return incumbent(raw, design, sigma, groups, capture, member_count, include_residual=include_residual)

    return evaluate
