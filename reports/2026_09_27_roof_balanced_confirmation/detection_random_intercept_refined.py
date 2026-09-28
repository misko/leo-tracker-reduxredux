"""Mode-centered adaptive quadrature for a shared detection random intercept."""
from __future__ import annotations

from functools import lru_cache
import math
import operator

import numpy as np


@lru_cache(maxsize=None)
def _quadrature(order: int) -> tuple[np.ndarray, np.ndarray]:
    nodes, weights = np.polynomial.hermite.hermgauss(order)
    nodes = np.asarray(nodes, float)
    log_weights = np.log(np.asarray(weights, float)) - .5 * math.log(math.pi)
    nodes.setflags(write=False); log_weights.setflags(write=False)
    return nodes, log_weights


def _logsumexp(values: np.ndarray, axis: int) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    return np.squeeze(maximum, axis=axis) + np.log(
        np.sum(np.exp(values - maximum), axis=axis))


def _mode_curvature(logits: np.ndarray, y: np.ndarray,
                    sigma: float) -> tuple[np.ndarray, np.ndarray]:
    """Solve the strictly concave conditional posterior mode per candidate."""
    inverse_variance = 1. / sigma**2
    modes = np.zeros(logits.shape[0])
    curvature = np.empty(logits.shape[0])
    successes = float(np.sum(y)); rows = len(y)
    for candidate, row in enumerate(logits):
        # Since 0 <= sum(sigmoid) <= N, these bounds contain the unique root.
        lower = sigma**2 * (successes - rows)
        upper = sigma**2 * successes
        mode = min(upper, max(lower, 0.))
        converged = False
        for _ in range(64):
            shifted = row + mode
            probability = 1. / (1. + np.exp(-np.clip(shifted, -40., 40.)))
            gradient = float(np.sum(y - probability) - mode * inverse_variance)
            negative_hessian = float(
                np.sum(probability * (1. - probability)) + inverse_variance)
            if abs(gradient) <= 1e-12 * (1. + rows):
                converged = True
                break
            if gradient > 0:
                lower = mode
            else:
                upper = mode
            proposal = mode + gradient / negative_hessian
            width = upper - lower
            mode = (proposal if lower + .1 * width < proposal < upper - .1 * width
                    else (lower + upper) / 2.)
        if not converged:
            # Guaranteed fallback for flat all-hit/all-miss tails.  The score
            # is monotone decreasing, so bisection cannot leave the bracket.
            for _ in range(160):
                mode = (lower + upper) / 2.
                shifted = row + mode
                probability = 1. / (1. + np.exp(-np.clip(shifted, -40., 40.)))
                gradient = float(np.sum(y - probability) - mode * inverse_variance)
                if abs(gradient) <= 1e-12 * (1. + rows):
                    converged = True
                    break
                if gradient > 0:
                    lower = mode
                else:
                    upper = mode
            if not converged:
                raise RuntimeError("random-intercept bracket solve did not converge")
        shifted = row + mode
        probability = 1. / (1. + np.exp(-np.clip(shifted, -40., 40.)))
        final_gradient = float(np.sum(y - probability) - mode * inverse_variance)
        negative_hessian = float(
            np.sum(probability * (1. - probability)) + inverse_variance)
        if (abs(final_gradient) > 1e-9 * (1. + len(y)) or
                not math.isfinite(negative_hessian) or negative_hessian <= 0):
            raise RuntimeError("random-intercept mode failed residual check")
        modes[candidate] = mode
        curvature[candidate] = negative_hessian
    return modes, curvature


def candidate_detection_loglik(logits, matched, sigma,
                               quadrature_order: int = 64) -> np.ndarray:
    """Integrate one Normal random intercept shared by all rows of a track."""
    values = np.asarray(logits, dtype=float)
    outcomes = np.asarray(matched)
    if (values.ndim != 2 or not values.shape[0] or not values.shape[1] or
            not np.all(np.isfinite(values))):
        raise ValueError("logits must be a nonempty finite candidate-row matrix")
    if (outcomes.ndim != 1 or outcomes.shape != (values.shape[1],) or
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
        return np.sum(y[None, :] * values - np.logaddexp(0., values), axis=1)

    modes, curvature = _mode_curvature(values, y, scale)
    proposal_sd = 1. / np.sqrt(curvature)
    nodes, log_weights = _quadrature(order)
    u = modes[:, None] + math.sqrt(2.) * proposal_sd[:, None] * nodes[None, :]
    shifted = values[:, None, :] + u[:, :, None]
    bernoulli = np.sum(
        y[None, None, :] * shifted - np.logaddexp(0., shifted), axis=2)
    log_prior = (-.5 * (u / scale)**2
                 - math.log(scale) - .5 * math.log(2. * math.pi))
    log_proposal = (-.5 * ((u - modes[:, None]) / proposal_sd[:, None])**2
                    - np.log(proposal_sd)[:, None]
                    - .5 * math.log(2. * math.pi))
    result = _logsumexp(
        bernoulli + log_prior - log_proposal + log_weights[None, :], axis=1)
    if not np.all(np.isfinite(result)):
        raise FloatingPointError("adaptive random-intercept likelihood is nonfinite")
    return result
