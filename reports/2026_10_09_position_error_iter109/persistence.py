"""Synthetic marginal-preserving persistence; distinct from immutable108 model."""

import runpy
from pathlib import Path

import numpy as np

BASE = runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter108/persistence.py")
)


def transport(previous, current, rho):
    """Return diagonal retention and rank-one redraw preserving prescribed priors."""
    previous, current = np.asarray(previous, float), np.asarray(current, float)
    if (
        previous.ndim != 1
        or previous.shape != current.shape
        or len(previous) < 2
        or not np.isfinite(previous).all()
        or not np.isfinite(current).all()
        or np.any(previous < 0)
        or np.any(current < 0)
        or not np.isclose(previous.sum(), 1, atol=1e-12, rtol=0)
        or not np.isclose(current.sum(), 1, atol=1e-12, rtol=0)
        or not np.isfinite(rho)
        or not 0 <= rho < 1
    ):
        raise ValueError("Normalized categorical priors and rho in [0,1) required")
    retained_mass = rho * np.minimum(previous, current)
    retained_mass[0] = 0  # Clutter never retains its state through the diagonal term.
    retention = np.divide(retained_mass, previous, out=np.zeros_like(current), where=previous > 0)
    z = 1 - retained_mass.sum()
    redraw = (current - retained_mass) / z
    assert z > 0 and np.all(redraw >= 0)
    np.testing.assert_allclose(redraw.sum(), 1, atol=1e-12, rtol=0)
    return retention, redraw


def evaluate(measured, prediction, visible, score, *, rho, reset):
    measured, prediction, visible = (
        np.asarray(measured),
        np.asarray(prediction),
        np.asarray(visible),
    )
    reset = np.asarray(reset)
    if not np.isfinite(rho) or not 0 <= rho < 1:
        raise ValueError("rho must be in [0,1)")
    if not 0 < score.sigma_hz <= 1000:
        raise ValueError("Only nearest-wrapped narrow-width hard60 is implemented")
    if prediction.ndim != 2 or len(prediction) == 0:
        raise ValueError("At least one observation required")
    if reset.shape != (len(prediction),) or reset.dtype != bool or not reset[0]:
        raise ValueError("Boolean reset flags starting with True required")
    independent, pi, _, emission, log_detection, residual = BASE["components"](
        measured, prediction, visible, score
    )
    alpha, retention, redraw = np.empty_like(pi), np.zeros_like(pi), np.empty_like(pi)
    normalizer = np.empty(len(pi))
    for n in range(len(pi)):
        if reset[n]:
            beta = pi[n]
            redraw[n] = pi[n]
        else:
            retention[n], redraw[n] = transport(pi[n - 1], pi[n], rho)
            sticky = retention[n] * alpha[n - 1]
            beta = sticky + (1 - sticky.sum()) * redraw[n]
        weighted = beta * emission[n]
        normalizer[n] = weighted.sum()
        alpha[n] = weighted / normalizer[n]
    backward = np.ones_like(pi)
    for n in range(len(pi) - 2, -1, -1):
        if reset[n + 1]:
            continue
        weighted = emission[n + 1] * backward[n + 1] / normalizer[n + 1]
        backward[n] = retention[n + 1] * weighted + (1 - retention[n + 1]) * (
            redraw[n + 1] @ weighted
        )
    gamma = alpha * backward
    gamma /= gamma.sum(axis=1)[:, None]
    nll = -float(np.sum(log_detection + np.log(normalizer)))
    gradient = -gamma[:, 1:] * residual / score.sigma_hz**2
    if rho == 0:
        nll, gradient = independent.nll, independent.prediction_gradient.copy()
        gamma = np.column_stack([independent.clutter_probability, independent.responsibilities])
    return dict(
        nll=nll,
        prediction_gradient=gradient,
        occupancy=gamma,
        filtered=alpha,
        normalizer=normalizer,
        residual_hz=residual,
        retention=retention,
        redraw=redraw,
    )
