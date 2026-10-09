"""Synthetic-only O(NK) identity persistence kernel; no tracks or position fitter."""

import numpy as np

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ, circular


def transition(pi, active, rho):
    """Dense diagnostic oracle only; the sequence kernel never builds this matrix."""
    return np.diag(rho * active) + (1 - rho * active)[:, None] * pi[None, :]


def components(measured, prediction, visible, score):
    independent = likelihood(measured, prediction, visible, score)
    n, k = prediction.shape
    q = score.detection_budget / k
    weight = q / (1 - q)
    counts = visible.sum(axis=1)
    total = score.clutter_rate + counts * weight
    pi = np.column_stack([np.full(n, score.clutter_rate), visible * weight]) / total[:, None]
    active = np.column_stack([np.zeros(n, dtype=bool), visible])
    residual = circular(measured[:, None] - prediction)
    emission = np.column_stack(
        [
            np.full(n, 1 / ALIAS_HZ),
            np.exp(-0.5 * (residual / score.sigma_hz) ** 2) / (score.sigma_hz * np.sqrt(2 * np.pi)),
        ]
    )
    log_p0 = -score.clutter_rate + counts * np.log1p(-q)
    log_detection = log_p0 - np.log(-np.expm1(log_p0)) + np.log(total)
    return independent, pi, active, emission, log_detection, residual


def evaluate(measured, prediction, visible, score, *, rho, reset):
    """Marginalize labels; reset[n] starts a new independent segment at row n.

    Each input row occurs exactly once. The caller must supply frozen valid segment
    boundaries; this kernel never invents continuity or selects a persistence value.
    Visibility is held fixed for frequency derivatives, as in hard60.
    """
    measured, prediction, visible = (
        np.asarray(measured),
        np.asarray(prediction),
        np.asarray(visible),
    )
    reset = np.asarray(reset)
    if not np.isfinite(rho) or not 0 <= rho < 1:
        raise ValueError("rho must be in [0,1)")
    if not 0 < score.sigma_hz <= 1000:
        raise ValueError("Only hard60 nearest-wrapped narrow-width regime is implemented")
    if prediction.ndim != 2 or len(prediction) == 0:
        raise ValueError("At least one row required")
    if reset.shape != (len(prediction),) or reset.dtype != bool or not reset[0]:
        raise ValueError("Boolean reset per row, beginning with True, required")
    independent, pi, active, emission, log_detection, residual = components(
        measured, prediction, visible, score
    )
    alpha = np.empty_like(pi)
    normalizer = np.empty(len(pi))
    for n in range(len(pi)):
        if reset[n]:
            beta = pi[n]
        else:
            sticky = rho * active[n] * alpha[n - 1]
            beta = sticky + (1 - sticky.sum()) * pi[n]
        weighted = beta * emission[n]
        normalizer[n] = weighted.sum()
        alpha[n] = weighted / normalizer[n]
    backward = np.ones_like(pi)
    for n in range(len(pi) - 2, -1, -1):
        if reset[n + 1]:
            continue
        weighted = emission[n + 1] * backward[n + 1] / normalizer[n + 1]
        redraw = pi[n + 1] @ weighted
        backward[n] = rho * active[n + 1] * weighted + (1 - rho * active[n + 1]) * redraw
    gamma = alpha * backward
    gamma /= gamma.sum(axis=1)[:, None]
    nll = -float(np.sum(log_detection + np.log(normalizer)))
    gradient = -gamma[:, 1:] * residual / score.sigma_hz**2
    if rho == 0:
        # Exact bitwise independent limit, including hard60's floating-point order.
        nll, gradient = independent.nll, independent.prediction_gradient.copy()
        gamma = np.column_stack([independent.clutter_probability, independent.responsibilities])
    return dict(
        nll=nll,
        prediction_gradient=gradient,
        occupancy=gamma,
        filtered=alpha,
        normalizer=normalizer,
        residual_hz=residual,
    )
