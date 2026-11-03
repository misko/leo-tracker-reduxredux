"""Pure statistical models for M2 covariance and M5 information diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable

import numpy as np


Array = np.ndarray


def exponential_covariance(
    times_s: Array,
    *,
    sigma_hz: float = 100.0,
    correlation_fraction: float = 0.2,
    correlation_time_s: float = 10.0,
) -> Array:
    """Frozen engineering covariance: white floor plus exponential component."""
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or not np.all(np.isfinite(times)):
        raise ValueError("times must be a finite vector")
    if sigma_hz <= 0 or correlation_time_s <= 0:
        raise ValueError("covariance scales must be positive")
    if not 0 <= correlation_fraction < 1:
        raise ValueError("correlation fraction must be in [0, 1)")
    lag = np.abs(times[:, None] - times[None, :])
    correlation = np.exp(-lag / correlation_time_s)
    return sigma_hz**2 * (
        (1.0 - correlation_fraction) * np.eye(times.size)
        + correlation_fraction * correlation
    )


def _spd(matrix: Array, dimension: int | None = None) -> Array:
    value = np.asarray(matrix, dtype=float)
    if value.ndim != 2 or value.shape[0] != value.shape[1]:
        raise ValueError("covariance must be square")
    if dimension is not None and value.shape != (dimension, dimension):
        raise ValueError("covariance dimension mismatch")
    if not np.all(np.isfinite(value)):
        raise ValueError("covariance must be finite")
    np.linalg.cholesky(value)
    return value


def constant_contrasts(size: int) -> Array:
    """Return orthonormal rows spanning the complement of the constant vector."""
    if size < 2:
        raise ValueError("at least two samples are required")
    rows = np.zeros((size - 1, size), dtype=float)
    for row in range(size - 1):
        width = row + 1
        rows[row, :width] = 1.0 / math.sqrt(width * (width + 1))
        rows[row, width] = -width / math.sqrt(width * (width + 1))
    return rows


def normalized_profile_logpdf(residual_hz: Array, covariance_hz2: Array) -> float:
    """Proper Gaussian density after removing one arbitrary constant offset."""
    residual = np.asarray(residual_hz, dtype=float)
    if residual.ndim != 1 or not np.all(np.isfinite(residual)):
        raise ValueError("residual must be a finite vector")
    covariance = _spd(covariance_hz2, residual.size)
    contrast = constant_contrasts(residual.size)
    projected = contrast @ residual
    projected_covariance = contrast @ covariance @ contrast.T
    chol = np.linalg.cholesky(projected_covariance)
    solved = np.linalg.solve(chol, projected)
    return float(
        -0.5
        * (
            projected.size * math.log(2.0 * math.pi)
            + 2.0 * np.log(np.diag(chol)).sum()
            + solved @ solved
        )
    )


@dataclass(frozen=True)
class ConditionalScore:
    offset_hz: float
    mean_hz: Array
    covariance_hz2: Array
    log_density: float


def conditional_held_logpdf(
    train_residual_hz: Array,
    held_residual_hz: Array,
    joint_covariance_hz2: Array,
) -> ConditionalScore:
    """Fit a train-only constant and score held residuals conditionally.

    The returned held covariance includes uncertainty from estimating the
    constant on training samples. No held value influences the fitted offset.
    """
    train = np.asarray(train_residual_hz, dtype=float)
    held = np.asarray(held_residual_hz, dtype=float)
    if train.ndim != 1 or held.ndim != 1 or train.size < 1 or held.size < 1:
        raise ValueError("non-empty train and held vectors are required")
    covariance = _spd(joint_covariance_hz2, train.size + held.size)
    ktt = covariance[: train.size, : train.size]
    kth = covariance[: train.size, train.size :]
    kht = kth.T
    khh = covariance[train.size :, train.size :]
    one = np.ones(train.size)
    inverse_one = np.linalg.solve(ktt, one)
    denominator = float(one @ inverse_one)
    offset = float(inverse_one @ train / denominator)
    inverse_centered = np.linalg.solve(ktt, train - offset)
    mean = offset + kht @ inverse_centered
    conditional = khh - kht @ np.linalg.solve(ktt, kth)
    sensitivity = np.ones(held.size) - kht @ inverse_one
    conditional += np.outer(sensitivity, sensitivity) / denominator
    conditional = (conditional + conditional.T) * 0.5
    chol = np.linalg.cholesky(conditional)
    solved = np.linalg.solve(chol, held - mean)
    log_density = -0.5 * (
        held.size * math.log(2.0 * math.pi)
        + 2.0 * np.log(np.diag(chol)).sum()
        + solved @ solved
    )
    return ConditionalScore(offset, mean, conditional, float(log_density))


@dataclass(frozen=True)
class InformationDiagnostic:
    jacobian_hz_per_km: Array
    profiled_information: Array
    eigenvalues: Array
    log_pseudodeterminant: float
    rank: int


def doppler_information(
    predictor: Callable[[Array], Array],
    position_km: Array,
    covariance_hz2: Array,
    *,
    step_km: float = 0.1,
    nuisance_design: Array | None = None,
) -> InformationDiagnostic:
    """Finite-difference Doppler information after GLS nuisance projection."""
    position = np.asarray(position_km, dtype=float)
    if position.shape != (2,) or step_km <= 0:
        raise ValueError("position must have two coordinates and step must be positive")
    center = np.asarray(predictor(position), dtype=float)
    if center.ndim != 1 or not np.all(np.isfinite(center)):
        raise ValueError("predictor must return a finite vector")
    covariance = _spd(covariance_hz2, center.size)
    jacobian = np.empty((center.size, 2), dtype=float)
    for axis in range(2):
        delta = np.zeros(2)
        delta[axis] = step_km
        plus = np.asarray(predictor(position + delta), dtype=float)
        minus = np.asarray(predictor(position - delta), dtype=float)
        if plus.shape != center.shape or minus.shape != center.shape:
            raise ValueError("predictor shape changed")
        jacobian[:, axis] = (plus - minus) / (2.0 * step_km)
    design = (
        np.ones((center.size, 1), dtype=float)
        if nuisance_design is None
        else np.asarray(nuisance_design, dtype=float)
    )
    if design.ndim != 2 or design.shape[0] != center.size:
        raise ValueError("nuisance design row mismatch")
    precision_j = np.linalg.solve(covariance, jacobian)
    precision_d = np.linalg.solve(covariance, design)
    nuisance_information = design.T @ precision_d
    projected_precision_j = precision_j - precision_d @ np.linalg.solve(
        nuisance_information, design.T @ precision_j
    )
    information = jacobian.T @ projected_precision_j
    information = (information + information.T) * 0.5
    eigenvalues = np.linalg.eigvalsh(information)
    tolerance = max(float(eigenvalues.max()), 1.0) * 1e-10
    positive = eigenvalues[eigenvalues > tolerance]
    rank = int(positive.size)
    log_pseudodeterminant = float(np.log(positive).sum()) if rank else -math.inf
    return InformationDiagnostic(jacobian, information, eigenvalues, log_pseudodeterminant, rank)


def normalized_information_weights(diagnostics: Iterable[InformationDiagnostic]) -> Array:
    values = np.asarray([item.log_pseudodeterminant for item in diagnostics], dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("no candidate has identifiable position information")
    shifted = np.zeros_like(values)
    shifted[finite] = np.exp(values[finite] - values[finite].max())
    return shifted / shifted.sum()
