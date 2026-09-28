"""Numerical candidate-set likelihoods for the receiver geometry pilot.

The functions in this module operate only on in-memory arrays.  Frequencies are
represented on a circle.  The three-image wrapped-normal approximation is
intended for the frozen pilot domain: ``period >= 200_000`` Hz and
``100 <= sigma <= 20_000`` Hz.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]


class ScoreUpdate(NamedTuple):
    """Result of reception filtering followed by sequential held scoring.

    All posterior values remain in the log domain.  ``log_evidence`` is the
    conditional log evidence of the complete held block, and the individual
    entries of ``held_window_log_scores`` sum to it.
    """

    log_evidence: float
    reception_log_posterior: FloatArray
    held_log_posterior: FloatArray
    held_window_log_scores: FloatArray

    @property
    def reception_posterior(self) -> FloatArray:
        """Compatibility name; values are normalized log probabilities."""
        return self.reception_log_posterior

    @property
    def held_posterior(self) -> FloatArray:
        """Compatibility name; values are normalized log probabilities."""
        return self.held_log_posterior


def _logsumexp(values: FloatArray, axis: int | None = None) -> FloatArray:
    maximum = np.max(values, axis=axis, keepdims=True)
    finite_maximum = np.where(np.isfinite(maximum), maximum, 0.0)
    total = np.sum(np.exp(values - finite_maximum), axis=axis, keepdims=True)
    result = np.log(total) + finite_maximum
    result = np.squeeze(result) if axis is None else np.squeeze(result, axis=axis)
    return np.asarray(result, dtype=float)


def _log_expit(value: FloatArray) -> FloatArray:
    return -np.logaddexp(0.0, -value)


def periodic_signal_ratio(
    frequencies: ArrayLike,
    predicted: ArrayLike,
    period: float,
    sigma: float,
) -> FloatArray:
    """Return ``period * sum_j g(f_j | predicted)`` for a periodic normal.

    The returned array has the shape of ``predicted``.  An empty candidate set
    returns zeros.  Reducing the displacement to the principal circle before
    summing the centre and adjacent images makes the result alias invariant.
    """
    frequencies_array = np.asarray(frequencies, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if frequencies_array.ndim != 1:
        raise ValueError("frequencies must be one-dimensional")
    if not np.all(np.isfinite(frequencies_array)) or not np.all(np.isfinite(predicted_array)):
        raise ValueError("frequencies and predicted values must be finite")
    if not np.isfinite(period) or period <= 0:
        raise ValueError("period must be positive and finite")
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma must be positive and finite")
    if frequencies_array.size == 0:
        return np.zeros_like(predicted_array, dtype=float)

    displacement = frequencies_array.reshape((-1,) + (1,) * predicted_array.ndim) - predicted_array
    displacement = np.remainder(displacement + period / 2.0, period) - period / 2.0
    images = displacement[..., None] + period * np.array([-1.0, 0.0, 1.0])
    density = np.exp(-0.5 * (images / sigma) ** 2).sum(axis=-1)
    density /= sigma * np.sqrt(2.0 * np.pi)
    return np.asarray(period * density.sum(axis=0), dtype=float)


def paired_log_likelihood(
    signal_sums: ArrayLike,
    counts: ArrayLike,
    logits: ArrayLike,
    visibility: ArrayLike,
    lambdas: ArrayLike,
    period: float,
    latent_sd: float = 1.0,
    quadrature_order: int = 5,
) -> FloatArray:
    """Integrate each paired-receiver set likelihood over one shared intercept.

    ``signal_sums[w, c, r]`` is the output of :func:`periodic_signal_ratio`.
    Invisible components use the clutter-only likelihood for both receivers.
    The shared normal intercept has standard deviation ``latent_sd``; there is
    deliberately no AR state in this first, rho-zero implementation.
    """
    sums = np.asarray(signal_sums, dtype=float)
    candidate_counts = np.asarray(counts)
    linear = np.asarray(logits, dtype=float)
    visible = np.asarray(visibility, dtype=bool)
    clutter_rates = np.asarray(lambdas, dtype=float)

    if sums.ndim != 3 or sums.shape[-1] != 2:
        raise ValueError("signal_sums must have shape (windows, components, 2)")
    windows, components, _ = sums.shape
    if linear.shape != sums.shape:
        raise ValueError("logits must have the same shape as signal_sums")
    if candidate_counts.shape != (windows, 2):
        raise ValueError("counts must have shape (windows, 2)")
    if visible.shape != (windows, components):
        raise ValueError("visibility must have shape (windows, components)")
    if clutter_rates.shape != (2,):
        raise ValueError("lambdas must have shape (2,)")
    if np.any(sums < 0) or not np.all(np.isfinite(sums)):
        raise ValueError("signal_sums must be finite and nonnegative")
    if not np.all(np.isfinite(linear)):
        raise ValueError("logits must be finite")
    if np.any(candidate_counts < 0) or not np.all(candidate_counts == np.floor(candidate_counts)):
        raise ValueError("counts must be nonnegative integers")
    if np.any(clutter_rates <= 0) or not np.all(np.isfinite(clutter_rates)):
        raise ValueError("lambdas must be positive and finite")
    if not np.isfinite(period) or period <= 0:
        raise ValueError("period must be positive and finite")
    if not np.isfinite(latent_sd) or latent_sd < 0:
        raise ValueError("latent_sd must be finite and nonnegative")
    if (
        isinstance(quadrature_order, bool)
        or int(quadrature_order) != quadrature_order
        or quadrature_order < 1
    ):
        raise ValueError("quadrature_order must be a positive integer")

    # numpy's Hermite rule integrates exp(-x**2); sqrt(2)*x therefore gives
    # standard-normal nodes and weights/sqrt(pi) their probabilities.
    nodes, weights = np.polynomial.hermite.hermgauss(int(quadrature_order))
    latent = np.sqrt(2.0) * latent_sd * nodes
    log_weights = np.log(weights) - 0.5 * np.log(np.pi)
    clutter = -clutter_rates + candidate_counts * np.log(clutter_rates / period)
    log_sums = np.full_like(sums, -np.inf)
    positive = sums > 0
    log_sums[positive] = np.log(sums[positive])
    # signal_sums contains period * sum(g); dividing by lambda completes
    # g / (lambda / period), the signal-to-clutter density ratio.
    log_sums -= np.log(clutter_rates)[None, None, :]

    joint_by_node = np.empty((quadrature_order, windows, components), dtype=float)
    for node_index, offset in enumerate(latent):
        shifted = linear + offset
        log_p = _log_expit(shifted)
        log_not_p = _log_expit(-shifted)
        mixture = np.logaddexp(log_not_p, log_p + log_sums)
        mixture = np.where(visible[..., None], mixture, 0.0)
        receiver_loglike = clutter[:, None, :] + mixture
        joint_by_node[node_index] = receiver_loglike.sum(axis=-1)

    return _logsumexp(joint_by_node + log_weights[:, None, None], axis=0)


def update_score(
    logprior: ArrayLike,
    loglik: ArrayLike,
    reception_mask: ArrayLike,
    held_mask: ArrayLike,
) -> ScoreUpdate:
    """Filter reception windows, then score and consume held windows in order."""
    prior = np.asarray(logprior, dtype=float)
    likelihood = np.asarray(loglik, dtype=float)
    reception = np.asarray(reception_mask, dtype=bool)
    held = np.asarray(held_mask, dtype=bool)
    if prior.ndim != 1 or prior.size == 0:
        raise ValueError("logprior must be a nonempty one-dimensional array")
    if likelihood.ndim != 2 or likelihood.shape[1] != prior.size:
        raise ValueError("loglik must have shape (windows, components)")
    if reception.shape != (likelihood.shape[0],) or held.shape != reception.shape:
        raise ValueError("masks must have shape (windows,)")
    if np.any(reception & held):
        raise ValueError("reception and held masks must be disjoint")
    if np.any(np.isnan(prior)) or np.any(np.isnan(likelihood)) or np.any(np.isposinf(prior)):
        raise ValueError("log inputs may not contain NaN or positive infinity")
    if not np.any(np.isfinite(prior)):
        raise ValueError("at least one prior component must have finite mass")

    posterior = prior - float(_logsumexp(prior))
    for row in likelihood[reception]:
        updated = posterior + row
        normalizer = float(_logsumexp(updated))
        if not np.isfinite(normalizer):
            raise ValueError("reception window has zero predictive density")
        posterior = updated - normalizer
    reception_posterior = posterior.copy()

    held_scores = []
    for row in likelihood[held]:
        updated = posterior + row
        score = float(_logsumexp(updated))
        if not np.isfinite(score):
            raise ValueError("held window has zero predictive density")
        held_scores.append(score)
        posterior = updated - score
    scores = np.asarray(held_scores, dtype=float)
    return ScoreUpdate(float(scores.sum()), reception_posterior, posterior, scores)
