"""Remove exact zero RHS prefixes and analytical group biases from the published grid."""

from time import process_time_ns

import numpy as np
from scipy.linalg import cho_solve, solve_triangular


def reduced_whiten(design, lower, order, scales):
    """A lower-triangular system with a zero prefix has a zero solution there."""
    nonzero = np.any(design != 0., axis=0)[order]
    present = np.flatnonzero(nonzero)
    prefix = int(present[0]) if len(present) else len(order)
    if prefix == len(order):
        return np.empty((len(design), 0)), prefix
    tail = order[prefix:]
    rhs = (design[:, tail] * scales[tail]).T
    return solve_triangular(lower[prefix:, prefix:], rhs, lower=True, check_finite=False).T, prefix


def collapse_biases(raw, uncertainty, sigma, groups):
    """Apply the symmetric inverse square root of each rank-one bias block."""
    if (not len(raw) or groups.shape != raw.shape or sigma.shape != raw.shape
            or not np.issubdtype(groups.dtype, np.integer) or groups[0] < 0
            or np.any(groups[1:] < groups[:-1]) or np.any(sigma <= 0)):
        raise ValueError("Sorted predictive curve labels and positive noise scales required")
    starts = np.r_[0, np.flatnonzero(groups[1:] != groups[:-1]) + 1]
    counts = np.diff(np.r_[starts, len(groups)])
    inverse = 1. / sigma
    bias = 300. * inverse
    weighted = np.column_stack((uncertainty, raw)) * inverse[:, None]
    lengths = np.add.reduceat(bias * bias, starts)
    root = np.sqrt(1. + lengths)
    cross = np.add.reduceat(weighted * bias[:, None], starts, axis=0)
    collapsed = weighted - bias[:, None] * np.repeat(cross / (root * (root + 1.))[:, None],
                                                     counts, axis=0)
    return collapsed[:, :-1], collapsed[:, -1], float(np.log1p(lengths).sum()), len(starts)


def reduced_predictive(raw, design, sigma, groups, capture, member_count, *, include_residual=False):
    if not 0 < member_count <= capture.width:
        raise ValueError("The checked posterior and latent scales are incompatible")
    axis_time = process_time_ns()
    scales = np.ones(capture.width)
    scales[-member_count:] = .3
    uncertainty, prefix = reduced_whiten(design, capture.lower, capture.order, scales)
    collapse_time = process_time_ns()
    features, values, volume, biases = collapse_biases(raw, uncertainty, sigma, groups)
    factor_time = process_time_ns()
    if features.shape[1]:
        gram = np.eye(features.shape[1]) + features.T @ features
        root = np.linalg.cholesky(gram)
        coefficient = cho_solve((root, True), features.T @ values, check_finite=False)
        innovation = values - features @ coefficient
        volume += float(2 * np.log(root.diagonal()).sum())
    else:
        coefficient = np.empty(0)
        innovation = values
    normalization = float(np.sum(np.log(2 * np.pi) + 2 * np.log(sigma)))
    quadratic = float(innovation @ innovation + coefficient @ coefficient)
    result = dict(objective=quadratic+volume+normalization, normalization_constant=normalization)
    if not np.isfinite(result["objective"]):
        raise ValueError("Non-finite reduced predictive objective")
    if include_residual:
        result["residual"] = np.r_[innovation, coefficient, np.sqrt(volume)]
    return result, dict(rows=len(raw), width=capture.width, prefix=prefix, biases=biases,
                        whiten_cpu_ns=collapse_time-axis_time, bias_cpu_ns=factor_time-collapse_time,
                        factor_cpu_ns=process_time_ns()-factor_time)
