"""Normalized low-rank stay/reset HMM, with no data or geometry dependencies."""

from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

LOG_RESOLUTION_LIMIT = 2.0**-20


def _check_log_resolution(value):
    """Fail closed if a finite internal contrast loses sub-micro log resolution."""
    finite = np.asarray(value)[np.isfinite(value)]
    if np.any(np.abs(np.spacing(finite)) > LOG_RESOLUTION_LIMIT):
        raise FloatingPointError("Unsupported internal log dynamic range/resolution")


def _normalize_log(value):
    maximum = float(np.max(value))
    if not np.isfinite(maximum):
        raise ValueError("Observed sequence has zero or nonfinite likelihood")
    centered = value - maximum
    _check_log_resolution(centered)
    small = float(logsumexp(centered))
    return centered - small, maximum + small


@dataclass(frozen=True)
class HMMTerms:
    nll: float
    log_normalizers: np.ndarray
    posterior: np.ndarray
    log_emission_gradient: np.ndarray
    reset_log_weight_gradient: np.ndarray
    stay_probability_gradient: np.ndarray


def _exp_finite(log_value):
    """Underflow is a zero representable derivative; overflow is never clipped."""
    value = np.asarray(log_value)
    if np.any(np.isnan(value)) or np.any(value > np.log(np.finfo(float).max)):
        raise FloatingPointError("HMM derivative overflow or invalid logarithm")
    with np.errstate(under="ignore", over="raise", invalid="raise"):
        return np.exp(value)


def _signed_exp_difference(a, b):
    """exp(a)-exp(b), avoiding both exp(large)-exp(large) and zero*infinity."""
    a, b = np.broadcast_arrays(a, b)
    result = np.zeros(a.shape)
    for use, first, second, sign in ((a > b, a, b, 1.0), (b > a, b, a, -1.0)):
        if np.any(use):
            # This branch never subtracts equal infinities: first>second.
            with np.errstate(under="ignore", divide="ignore", invalid="raise"):
                log_absolute = first[use] + np.log(-np.expm1(second[use] - first[use]))
            result[use] = sign * _exp_finite(log_absolute)
    return result


def evaluate(log_emission, reset_log_weight, stay_probability, observedmask):
    """Return NLL, filtered normalizers, smoothed states and exact NLL gradients.

    All three numeric inputs have shape [N,K]. Reset pi[n] is the row softmax
    of reset_log_weight[n]. Initial state is pi[0]; stay_probability[0] is
    unused and has zero gradient. For n>0,
      T[n,i,j] = s[n,i] 1(i=j) + (1-s[n,i]) pi[n,j].
    A missing row uses emission one, irrespective of its log_emission input.
    Its emission gradient is zero; its reset/stay gradients need not be zero
    because transitions still connect the surrounding observed rows.

    Emission distributions must be normalized externally. This component has
    no observation values, visibility transform, candidate IDs or grouping.
    Finite log values and -inf inactive entries are supported. Only OBSERVED
    emission entries are validated; unobserved entries are never consumed.
    Arbitrary finite COMMON row offsets are removed before normalization.
    Internal finite log contrasts must have float64 ULP <=2^-20 log units
    (supports magnitudes through approximately 8.6e9); larger contrasts fail
    closed. Returned large absolute NLL/log-normalizers retain float64's
    coarse precision. Genuine derivative/logarithmic overflow raises.
    Storage and work are O(NK); no K-by-K transition matrix is constructed.
    """
    emission = np.asarray(log_emission, dtype=float)
    weights = np.asarray(reset_log_weight, dtype=float)
    stay = np.asarray(stay_probability, dtype=float)
    observed = np.asarray(observedmask)
    if emission.ndim != 2 or min(emission.shape, default=0) < 1:
        raise ValueError("Nonempty [N,K] inputs required")
    if weights.shape != emission.shape or stay.shape != emission.shape:
        raise ValueError("Aligned [N,K] emission, reset and stay inputs required")
    count, states = emission.shape
    if observed.dtype != bool or observed.shape != (count,):
        raise ValueError("Explicit boolean observedmask[N] required")
    if np.any(np.isnan(weights)) or np.any(np.isposinf(weights)):
        raise ValueError("Reset log weights must be finite or -inf")
    if np.any(~np.isfinite(stay)) or np.any((stay < 0) | (stay > 1)):
        raise ValueError("Stay probabilities must lie in [0,1]")
    if np.any(np.isnan(emission[observed])) or np.any(np.isposinf(emission[observed])):
        raise ValueError("Observed log emissions must be finite or -inf")
    with np.errstate(over="raise", invalid="raise", under="ignore"):
        reset_maximum = np.max(weights, axis=1)
        if np.any(~np.isfinite(reset_maximum)):
            raise ValueError("At least one active reset state required per metadata row")
        centered_weights = weights - reset_maximum[:, None]
        _check_log_resolution(centered_weights)
        log_pi = centered_weights - logsumexp(centered_weights, axis=1)[:, None]
    pi = _exp_finite(log_pi)
    log_g = np.zeros_like(emission)
    emission_offset = np.zeros(count)
    if observed.any():
        emission_offset[observed] = np.max(emission[observed], axis=1)
        if np.any(~np.isfinite(emission_offset[observed])):
            raise ValueError("Observed sequence has zero or nonfinite likelihood")
        with np.errstate(over="raise", invalid="raise"):
            log_g[observed] = emission[observed] - emission_offset[observed, None]
        _check_log_resolution(log_g)
    with np.errstate(divide="ignore"):
        log_s = np.log(stay)
        log_reset = np.log1p(-stay)
    log_alpha = np.empty((count, states))
    log_z = np.empty(count)
    centered_log_z = np.empty(count)
    log_reset_mass = np.full(count, -np.inf)
    with np.errstate(over="raise", invalid="raise", under="ignore"):
        for row in range(count):
            if row == 0:
                predicted = log_pi[0]
            else:
                log_reset_mass[row] = logsumexp(log_alpha[row - 1] + log_reset[row])
                predicted = np.logaddexp(
                    log_alpha[row - 1] + log_s[row], log_reset_mass[row] + log_pi[row]
                )
            raw = predicted + log_g[row]
            log_alpha[row], normalizer = _normalize_log(raw)
            centered_log_z[row] = normalizer if observed[row] else 0.0
            # Missing emission integrates to one exactly; retain its transition.
            log_z[row] = normalizer + emission_offset[row] if observed[row] else 0.0
        if not observed.any():
            return HMMTerms(
                0.0,
                log_z,
                _exp_finite(log_alpha),
                np.zeros_like(emission),
                np.zeros_like(weights),
                np.zeros_like(stay),
            )
        posterior = np.empty_like(emission)
        reset_gradient = np.zeros_like(weights)
        stay_gradient = np.zeros_like(stay)
        log_beta = np.zeros(states)
        for row in range(count - 1, -1, -1):
            log_gamma = log_alpha[row] + log_beta
            log_gamma, _ = _normalize_log(log_gamma)
            posterior[row] = _exp_finite(log_gamma)
            if row == 0:
                reset_gradient[0] = pi[0] - posterior[0]
                break
            log_v = log_g[row] + log_beta - centered_log_z[row]
            _check_log_resolution(log_v)
            log_c = float(logsumexp(log_pi[row] + log_v))
            previous_beta = np.logaddexp(log_s[row] + log_v, log_reset[row] + log_c)
            # Remove accumulated common roundoff, preserving the backward gauge.
            gauge = float(logsumexp(log_alpha[row - 1] + previous_beta))
            if not np.isfinite(gauge):
                raise FloatingPointError("Invalid backward likelihood normalization")
            log_v = log_v - gauge
            log_c -= gauge
            previous_beta -= gauge
            _check_log_resolution(previous_beta)
            destination = _exp_finite(log_reset_mass[row] + log_pi[row] + log_v)
            reset_gradient[row] = pi[row] * destination.sum() - destination
            stay_gradient[row] = -_signed_exp_difference(
                log_alpha[row - 1] + log_v, log_alpha[row - 1] + log_c
            )
            log_beta = previous_beta
        nll = -float(np.sum(log_z, dtype=np.longdouble))
        if not np.isfinite(nll):
            raise FloatingPointError("Total NLL exceeds float64 range")
    return HMMTerms(
        nll, log_z, posterior, -posterior * observed[:, None], reset_gradient, stay_gradient
    )
