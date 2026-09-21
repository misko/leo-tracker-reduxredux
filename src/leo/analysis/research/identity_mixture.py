"""Numerical identity-mixture likelihoods for Doppler position research.

The caller owns catalogue selection, orbit propagation, and receiver geometry.
This module only profiles source-frequency offsets on training samples and
combines candidate and unassigned likelihoods without inspecting held-out data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def logsumexp(values: np.ndarray) -> float:
    """Stable scalar log-sum-exp, including the all-impossible case."""
    values = np.asarray(values, dtype=float)
    maximum = np.max(values)
    if not np.isfinite(maximum):
        return float(maximum)
    return float(maximum + np.log(np.sum(np.exp(values - maximum))))


def profile_offsets(
    residual_hz: np.ndarray, segment: np.ndarray, training: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Profile one constant offset per source using training observations only.

    This is the same clearly labelled approximation used by the fixed-identity
    baseline: arithmetic-mean offsets are profiled before robustification.  The
    fitted offsets are then frozen when held-out residuals are evaluated.
    """
    residual = np.asarray(residual_hz, dtype=float)
    segment = np.asarray(segment)
    training = np.asarray(training)
    if residual.ndim not in (1, 2) or segment.shape != (residual.shape[-1],):
        raise ValueError("residuals must be observation or candidate x observation arrays")
    if training.shape != segment.shape or training.dtype != bool:
        raise ValueError("training must be a matching boolean vector")
    if not np.all(np.isfinite(residual)):
        raise ValueError("residuals must be finite")
    rows = residual[None] if residual.ndim == 1 else residual
    result = rows.copy()
    labels = np.unique(segment)
    offsets = np.empty((len(rows), len(labels)))
    for index, label in enumerate(labels):
        selected = segment == label
        if not np.any(selected & training):
            raise ValueError("every source segment needs training observations")
        offsets[:, index] = np.mean(rows[:, selected & training], axis=1)
        result[:, selected] -= offsets[:, index, None]
    if residual.ndim == 1:
        return result[0], offsets[0]
    return result, offsets


def pseudo_huber_log_likelihood(
    residual_hz: np.ndarray, selected: np.ndarray, sigma_hz: float
) -> np.ndarray:
    """Return a robust Gaussian-like log likelihood over selected samples."""
    residual = np.asarray(residual_hz, dtype=float)
    selected = np.asarray(selected)
    if residual.ndim not in (1, 2) or selected.shape != (residual.shape[-1],):
        raise ValueError("invalid residual or selection shape")
    if selected.dtype != bool or not np.any(selected) or not np.isfinite(sigma_hz) or sigma_hz <= 0:
        raise ValueError("nonempty boolean selection and positive sigma required")
    z = residual[..., selected] / sigma_hz
    # rho(z) = 2 (sqrt(1 + z^2) - 1), matching the fixed-ID least-squares
    # residual transform.  Constants shared by all candidates are retained so
    # the signal and broad unassigned models remain comparable.
    energy = np.sum(np.sqrt(1 + z * z) - 1, axis=-1)
    return -energy - np.sum(selected) * np.log(sigma_hz)


@dataclass(frozen=True)
class MixtureConfig:
    signal_sigma_hz: float = 250.0
    unassigned_sigma_hz: float = 30_000.0
    signal_prior: float = 0.5

    def __post_init__(self) -> None:
        if not (
            0 < self.signal_sigma_hz < self.unassigned_sigma_hz
            and 0 < self.signal_prior < 1
        ):
            raise ValueError("invalid identity-mixture scales or prior")


def mixture_statistics(
    candidate_residual_hz: np.ndarray,
    unassigned_residual_hz: np.ndarray,
    segment: np.ndarray,
    training: np.ndarray,
    catalogue_size: int,
    *,
    visible: np.ndarray | None = None,
    config: MixtureConfig | None = None,
) -> dict[str, np.ndarray | float]:
    """Score one episode and condition held-out prediction on training only.

    The supplied candidates retain prior mass ``signal_prior/catalogue_size``;
    omitted catalogue entries are never renormalized into the shortlist.  A
    caller that truncates support must separately bound the omitted likelihood.
    """
    config = config or MixtureConfig()
    candidate = np.asarray(candidate_residual_hz, dtype=float)
    unassigned = np.asarray(unassigned_residual_hz, dtype=float)
    if candidate.ndim != 2 or unassigned.shape != (candidate.shape[1],):
        raise ValueError("candidate residuals must be candidate x observation")
    if catalogue_size < len(candidate) or catalogue_size < 1:
        raise ValueError("catalogue size cannot be smaller than supplied support")
    if visible is None:
        visible = np.ones(len(candidate), dtype=bool)
    visible = np.asarray(visible)
    if visible.shape != (len(candidate),) or visible.dtype != bool:
        raise ValueError("visibility must be one boolean per candidate")
    centered, offsets = profile_offsets(candidate, segment, training)
    null_centered, null_offsets = profile_offsets(unassigned, segment, training)
    train_ll = pseudo_huber_log_likelihood(centered, training, config.signal_sigma_hz)
    test_ll = pseudo_huber_log_likelihood(centered, ~training, config.signal_sigma_hz)
    train_ll = np.where(visible, train_ll, -np.inf)
    test_ll = np.where(visible, test_ll, -np.inf)
    null_train_ll = float(
        pseudo_huber_log_likelihood(null_centered, training, config.unassigned_sigma_hz)
    )
    null_test_ll = float(
        pseudo_huber_log_likelihood(null_centered, ~training, config.unassigned_sigma_hz)
    )
    components = np.concatenate(
        [
            train_ll + np.log(config.signal_prior / catalogue_size),
            [null_train_ll + np.log1p(-config.signal_prior)],
        ]
    )
    train_evidence = logsumexp(components)
    log_posterior = components - train_evidence
    posterior = np.exp(log_posterior)
    heldout_components = np.concatenate([test_ll, [null_test_ll]])
    # Keep conditioning weights in log space.  A component with training weight
    # below the floating-point exp range can still dominate an extreme held-out
    # predictive density; converting to probabilities here would erase it.
    predictive = logsumexp(log_posterior + heldout_components)
    train_sq = np.mean(centered[:, training] ** 2, axis=1)
    test_sq = np.mean(centered[:, ~training] ** 2, axis=1)
    null_train_sq = float(np.mean(null_centered[training] ** 2))
    null_test_sq = float(np.mean(null_centered[~training] ** 2))
    return {
        "train_log_evidence": train_evidence,
        "heldout_log_predictive": predictive,
        "candidate_posterior": posterior[:-1],
        "unassigned_posterior": float(posterior[-1]),
        "candidate_train_log_likelihood": train_ll,
        "candidate_heldout_log_likelihood": test_ll,
        "profiled_offsets_hz": offsets,
        "unassigned_offsets_hz": null_offsets,
        "posterior_train_mse_hz2": float(
            posterior @ np.concatenate([train_sq, [null_train_sq]])
        ),
        "posterior_heldout_mse_hz2": float(
            posterior @ np.concatenate([test_sq, [null_test_sq]])
        ),
    }
