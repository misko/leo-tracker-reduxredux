"""Conditional tangent influence of fixed satellite families on a position fit."""

import numpy as np


def tangent_position_step(a, b, residual, nuisance, weights, precision, *, noise_hz=150.0):
    """Solve the full augmented Gaussian system with zero-mean nuisance priors.

    No observations or identities are selected here. Deletion experiments are
    diagnostic influences, not a final estimator or a geographic confidence set.
    The result ignores bounds, volume derivatives and nonlinear curvature.
    """
    a, b = np.asarray(a, float), np.asarray(b, float)
    residual, nuisance = np.asarray(residual, float), np.asarray(nuisance, float)
    weights, precision = np.asarray(weights, float), np.asarray(precision, float)
    if (
        a.ndim != 2
        or a.shape[1] != 2
        or b.ndim != 2
        or len(a) != len(b)
        or residual.shape != (len(a),)
        or weights.shape != (len(a),)
        or nuisance.shape != (b.shape[1],)
        or precision.shape != nuisance.shape
        or not all(np.isfinite(x).all() for x in (a, b, residual, nuisance, weights, precision))
        or np.any(weights < 0)
        or np.any(precision < 0)
        or not np.isfinite(noise_hz)
        or noise_hz <= 0
    ):
        raise ValueError(
            "finite paired derivatives, residuals and nonnegative weights/priors required"
        )
    root, prior = np.sqrt(weights) / noise_hz, np.sqrt(precision)
    design = np.vstack(
        (np.c_[a, b] * root[:, None], np.c_[np.zeros((len(prior), 2)), np.diag(prior)])
    )
    target = np.r_[residual * root, -prior * nuisance]
    scale = np.linalg.norm(design, axis=0)
    active = scale > 0
    step = np.zeros(design.shape[1])
    normalized = design[:, active] / scale[active]
    solution, _, rank, singular = np.linalg.lstsq(normalized, target, rcond=1e-10)
    step[active] = solution / scale[active]
    return dict(
        east_north_step_km=step[:2],
        nuisance_step=step[2:],
        rank=int(rank),
        singular_values=singular,
        quadratic_before=float(target @ target),
        quadratic_after=float(np.sum((target - design @ step) ** 2)),
        local_tangent_diagnostic_only=True,
    )
