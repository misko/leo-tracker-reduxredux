"""Pure conditional association-transfer score with one shared candidate."""
from __future__ import annotations

import math
import operator

import numpy as np


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.sum(np.exp(values - maximum))))


def _vector(name, value, size=None):
    result = np.asarray(value, dtype=float)
    if (result.ndim != 1 or not len(result) or
            (size is not None and result.shape != (size,)) or
            not np.all(np.isfinite(result))):
        raise ValueError(f"{name} must be a nonempty aligned finite vector")
    return result


def _posterior(candidate_ids, log_values):
    normalized = log_values - _logsumexp(log_values)
    probability = np.exp(normalized)
    position = int(np.argmax(normalized))
    return {
        "candidate_ids": list(candidate_ids),
        "log_weights": normalized.tolist(),
        "probabilities": probability.tolist(),
        "map_candidate_id": int(candidate_ids[position]),
    }


def association_transfer_score(candidate_ids, training_log_weights,
                               conditioning_frequency_ll,
                               conditioning_reception_ll,
                               held_frequency_ll, held_count):
    """Condition on A, then predict B without using B to change association.

    Candidate likelihood vectors are track-aggregated log likelihoods.  The
    returned mean NLLs divide the shared-candidate held evidence by the number
    of held observations, after marginalizing candidate identity exactly once.
    """
    raw_ids = np.asarray(candidate_ids)
    if raw_ids.ndim != 1 or not len(raw_ids):
        raise ValueError("candidate_ids must be a nonempty vector")
    try:
        ids = [operator.index(value) for value in raw_ids.tolist()]
    except TypeError as error:
        raise ValueError("candidate_ids must be integers") from error
    if len(set(ids)) != len(ids):
        raise ValueError("candidate_ids must be unique")
    try:
        count = operator.index(held_count)
    except TypeError as error:
        raise ValueError("held_count must be a positive integer") from error
    if isinstance(held_count, (bool, np.bool_)) or count <= 0:
        raise ValueError("held_count must be a positive integer")
    size = len(ids)
    prior = _vector("training_log_weights", training_log_weights, size)
    frequency_a = _vector("conditioning_frequency_ll", conditioning_frequency_ll, size)
    reception_a = _vector("conditioning_reception_ll", conditioning_reception_ll, size)
    frequency_b = _vector("held_frequency_ll", held_frequency_ll, size)
    prior = prior - _logsumexp(prior)
    baseline_log_q = prior + frequency_a
    baseline_log_q -= _logsumexp(baseline_log_q)
    # Preserve exact cancellation for the candidate-invariant negative control.
    if np.all(reception_a == reception_a[0]):
        reception_log_q = baseline_log_q.copy()
    else:
        reception_log_q = prior + frequency_a + reception_a
        reception_log_q -= _logsumexp(reception_log_q)
    baseline_nll = -_logsumexp(baseline_log_q + frequency_b) / count
    reception_nll = -_logsumexp(reception_log_q + frequency_b) / count
    if not all(math.isfinite(value) for value in (baseline_nll, reception_nll)):
        raise FloatingPointError("association-transfer score is nonfinite")
    return {
        "baseline_mean_nll": float(baseline_nll),
        "reception_mean_nll": float(reception_nll),
        "improvement_baseline_minus_reception": float(baseline_nll - reception_nll),
        "baseline_conditioning_posterior": _posterior(ids, baseline_log_q),
        "reception_conditioning_posterior": _posterior(ids, reception_log_q),
        "training_prior": _posterior(ids, prior),
        "held_count": count,
        "identity_model": "one candidate conditioned on A and shared across all held B observations",
    }
