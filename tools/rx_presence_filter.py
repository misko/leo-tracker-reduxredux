"""Pure log-domain presence HMM for receiver candidate-set sequences.

The continuous-time process retains its current state with probability
``exp(-dt / tau)``.  Otherwise it refreshes from a fixed distribution with
absent mass ``1 - occupancy`` and present mass allocated by the conditional
candidate prior.  This reset process has an exact semigroup and keeps target
absence separate from omitted catalogue mass.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import logsumexp

FloatArray = NDArray[np.float64]


class ForwardScore(NamedTuple):
    window_log_scores: FloatArray
    reception_log_posterior: FloatArray
    held_log_posterior: FloatArray
    posterior_presence: FloatArray
    state_log_posteriors: FloatArray


def initial_log_prior(log_candidate_prior: ArrayLike, occupancy: float) -> FloatArray:
    """Build the absent-plus-candidate stationary distribution in log space."""
    candidate = np.asarray(log_candidate_prior, dtype=float)
    if candidate.ndim != 1 or candidate.size == 0:
        raise ValueError("log_candidate_prior must be a nonempty one-dimensional array")
    if np.any(np.isnan(candidate)) or np.any(np.isposinf(candidate)):
        raise ValueError("candidate log priors may not contain NaN or positive infinity")
    normalizer = float(logsumexp(candidate))
    if not np.isfinite(normalizer):
        raise ValueError("at least one candidate must have finite prior mass")
    if not np.isfinite(occupancy) or not 0.0 <= occupancy <= 1.0:
        raise ValueError("occupancy must lie in [0, 1]")
    log_absent = -np.inf if occupancy == 1.0 else np.log1p(-occupancy)
    log_present = -np.inf if occupancy == 0.0 else np.log(occupancy)
    return np.concatenate(([log_absent], log_present + candidate - normalizer))


def transition(
    log_candidate_prior: ArrayLike,
    dt_s: float,
    occupancy: float,
    tau: float,
) -> FloatArray:
    """Return the exact reset-process log transition matrix.

    Rows are source states and columns are destination states; state zero is
    absence.  A zero gap returns the identity exactly.
    """
    stationary = initial_log_prior(log_candidate_prior, occupancy)
    if not np.isfinite(dt_s) or dt_s < 0:
        raise ValueError("dt_s must be finite and nonnegative")
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError("tau must be positive and finite")
    states = len(stationary)
    if dt_s == 0:
        result = np.full((states, states), -np.inf)
        np.fill_diagonal(result, 0.0)
        return result
    log_persist = -dt_s / tau
    log_refresh = np.log(-np.expm1(log_persist))
    result = np.broadcast_to(log_refresh + stationary, (states, states)).copy()
    diagonal = np.diag_indices(states)
    result[diagonal] = np.logaddexp(result[diagonal], log_persist)
    return result


def forward_score(
    log_candidate_prior: ArrayLike,
    emissions: ArrayLike,
    times_s: ArrayLike,
    reception_mask: ArrayLike,
    held_mask: ArrayLike,
    occupancy: float,
    tau: float,
) -> ForwardScore:
    """Score and consume ordered reception then held windows sequentially."""
    candidate = np.asarray(log_candidate_prior, dtype=float)
    emission = np.asarray(emissions, dtype=float)
    times = np.asarray(times_s, dtype=float)
    reception = np.asarray(reception_mask, dtype=bool)
    held = np.asarray(held_mask, dtype=bool)
    windows = len(times)
    if emission.shape != (windows, candidate.size + 1):
        raise ValueError("emissions must have shape (windows, candidates + 1)")
    if reception.shape != (windows,) or held.shape != (windows,):
        raise ValueError("masks must have shape (windows,)")
    if np.any(reception & held) or not np.all(reception | held):
        raise ValueError("reception and held masks must be disjoint and cover every window")
    later_reception = np.cumsum(reception[::-1], dtype=int)[::-1] - reception
    if np.any(held & (later_reception > 0)):
        raise ValueError("all reception windows must precede held windows")
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) < 0):
        raise ValueError("times_s must be finite and nondecreasing")
    if np.any(np.isnan(emission)) or np.any(np.isposinf(emission)):
        raise ValueError("emissions may not contain NaN or positive infinity")

    posterior = initial_log_prior(candidate, occupancy)
    scores = np.empty(windows, dtype=float)
    state_posteriors = np.empty_like(emission)
    presence = np.empty(windows, dtype=float)
    reception_posterior = posterior.copy()
    for index in range(windows):
        if index:
            log_transition = transition(candidate, times[index] - times[index - 1], occupancy, tau)
            posterior = logsumexp(posterior[:, None] + log_transition, axis=0)
        updated = posterior + emission[index]
        score = float(logsumexp(updated))
        if not np.isfinite(score):
            raise ValueError("window has zero predictive density")
        scores[index] = score
        posterior = updated - score
        state_posteriors[index] = posterior
        presence[index] = float(np.exp(logsumexp(posterior[1:])))
        if reception[index]:
            reception_posterior = posterior.copy()
    return ForwardScore(scores, reception_posterior, posterior, presence, state_posteriors)
