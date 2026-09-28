"""Pure shared track-random-intercept detection likelihood."""
from __future__ import annotations

import math
import operator
from functools import lru_cache

import numpy as np


@lru_cache(maxsize=None)
def _quadrature(order: int) -> tuple[np.ndarray, np.ndarray]:
    """Return immutable normal-measure GH nodes and log weights."""
    nodes, weights = np.polynomial.hermite.hermgauss(order)
    nodes = np.asarray(nodes, float)
    log_weights = np.log(np.asarray(weights, float)) - .5 * math.log(math.pi)
    nodes.setflags(write=False)
    log_weights.setflags(write=False)
    return nodes, log_weights


def _logsumexp(values: np.ndarray, axis: int) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    return np.squeeze(maximum, axis=axis) + np.log(
        np.sum(np.exp(values - maximum), axis=axis))


def candidate_detection_loglik(logits, matched, sigma,
                               quadrature_order: int = 64) -> np.ndarray:
    """Return candidate detection log likelihoods with one shared track effect.

    ``logits`` has shape candidate by observation.  Conditional on candidate K
    and the single track effect u, observations are Bernoulli with logits
    ``logits[K, :] + u``; u is Normal(0, sigma**2).
    """
    values = np.asarray(logits, dtype=float)
    outcomes = np.asarray(matched)
    if (values.ndim != 2 or not values.shape[0] or not values.shape[1] or
            not np.all(np.isfinite(values))):
        raise ValueError("logits must be a nonempty finite candidate-row matrix")
    if (outcomes.ndim != 1 or outcomes.shape[0] != values.shape[1] or
            outcomes.dtype.kind not in "bui" or
            not np.all((outcomes == 0) | (outcomes == 1))):
        raise ValueError("matched must be a binary row vector")
    scale = float(sigma)
    if not math.isfinite(scale) or scale < 0:
        raise ValueError("sigma must be finite and nonnegative")
    try:
        order = operator.index(quadrature_order)
    except TypeError as error:
        raise ValueError("quadrature_order must be an integer") from error
    if order < 2:
        raise ValueError("quadrature_order must be at least two")
    y = outcomes.astype(float)
    if scale == 0.:
        # Deliberately the exact existing conditional Bernoulli expression.
        return np.sum(y[None, :] * values - np.logaddexp(0., values), axis=1)

    nodes, log_weights = _quadrature(order)
    shifted = values[:, None, :] + math.sqrt(2.) * scale * nodes[None, :, None]
    conditional = np.sum(
        y[None, None, :] * shifted - np.logaddexp(0., shifted), axis=2)
    result = _logsumexp(conditional + log_weights[None, :], axis=1)
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("random-intercept likelihood is nonfinite")
    return result
