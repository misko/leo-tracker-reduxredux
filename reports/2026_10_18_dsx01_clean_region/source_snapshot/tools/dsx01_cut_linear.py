"""Transfer curved-only nuisance posteriors to independent linear fragments.

This is a modular conditional score: linear evidence may inform position, but
the calibration posterior at every proposed position is computed from curves
alone. Nominations are frozen at the blind c0 endpoint, never at evaluation GPS.
"""

import numpy as np
from dsx01_joint_marginal import absolute_phase_linearization, integrated_gaussian
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis


def posterior_root(features, sigma, weight, precision):
    """Return R with RR' equal to the conditional coefficient covariance."""
    a = np.asarray(features) / np.asarray(sigma)[:, None] * np.sqrt(weight)[:, None]
    root = np.linalg.cholesky(np.diag(precision) + a.T @ a)
    return np.linalg.solve(root, np.eye(len(root))).T


def predictive_gaussian(raw, design, mean, root, *, sigma=150.0, bias_sigma=1000.0, groups=None):
    """Joint predictive density retaining uncertainty shared across fragments."""
    y, u = np.asarray(raw), np.asarray(design)
    if groups is None:
        groups = np.zeros(len(y), dtype=int)
    g = np.asarray(groups)
    if g.shape != y.shape or np.any(g < 0) or not np.issubdtype(g.dtype, np.integer):
        raise ValueError("one nonnegative integer group per observation required")
    if not np.isfinite(bias_sigma) or bias_sigma <= 0:
        raise ValueError("positive finite independent fragment bias scale required")
    _, g = np.unique(g, return_inverse=True)
    constants = np.eye(g.max() + 1)[g] * bias_sigma
    result = integrated_gaussian(y - u @ mean, np.column_stack((u @ root, constants)), sigma)
    scale = np.broadcast_to(np.asarray(sigma), y.shape)
    result["negative_twice_log_probability"] = float(
        result["residual"] @ result["residual"] + np.sum(np.log(2 * np.pi) + 2 * np.log(scale))
    )
    return result


def transfer_design(problem, track, candidate, x):
    """Normal-control nuisance coordinates evaluated on a new fragment."""
    p = problem
    if p.hypothesis != "normal":
        raise ValueError("transfer currently supports the unchanged Gaussian-prior control")
    j = list(p.labels).index(candidate)
    times = np.asarray(track["times"])
    local = np.full(len(times), j, dtype=int)
    f, elevation = paired_phase_frequency(p.sky, times, local, p.reference, *latlon(x))
    h = 0.01
    plus = paired_phase_frequency(p.sky, times, local, p.reference + h, *latlon(x))[0]
    minus = paired_phase_frequency(p.sky, times, local, p.reference - h, *latlon(x))[0]
    derivative = (plus - minus) / (2 * h)
    intercept = absolute_phase_linearization(f, derivative, p.reference[j])
    q = track["rf_hz"] / 11.5e9
    nb, ns = p.hardware.shape[1], p.smooth.shape[1]
    width = nb + ns + len(p.labels) + 3 * len(p.supported) + len(p.members)
    u = np.zeros((len(times), width))
    rx = track["receiver"] - 1
    group = 2 * rx + int(track["channel"] > 4)
    u[:, group] = PERIOD / np.sqrt(12)
    u[:, 4 + 2 * rx] = (times - 150) * 10
    u[:, 5 + 2 * rx] = (times - 150) * (-1 if track["channel"] <= 4 else 1) * 0.5
    if p.fitted_c:
        u[:, nb - 1] = (track["rf_hz"] / 1e9 - 11.5) * 200000
    smooth = projected_receiver_basis(times)
    start = nb + rx * smooth.shape[1]
    u[:, start : start + smooth.shape[1]] = q * smooth * 200
    u[:, nb + ns + j] = q * derivative * p.phase_sigma[j]
    if candidate in p.supported:
        mode = p.supported.index(candidate)
        modes = paired_frequency_modes(p.sky, p.mode_bank, times, local, p.reference, *latlon(x))
        start = nb + ns + len(p.labels) + 3 * mode
        u[:, start : start + 3] = q * modes
    return q * intercept, u, elevation


def curve_posterior(problem, x):
    result = problem.calculate(np.asarray(x))
    root = posterior_root(
        result["features"],
        problem.point_noise,
        result["noise_precision"][problem.noise_groups],
        result["coefficient_prior_precision"],
    )
    return result, root


def bounded_scalar_newton(score, initial, *, lower=-12.5, upper=12.5, iterations=24):
    """Two-dimensional bounded search with finite differences and monotone steps."""
    x = np.clip(np.asarray(initial, float), lower, upper)
    if x.shape != (2,) or not np.isfinite(x).all():
        raise ValueError("two finite geographic coordinates required")
    value = float(score(x))
    history = []
    converged = False
    for _ in range(iterations):
        h = 0.05
        eye = np.eye(2) * h
        # Derivatives may be evaluated just inside a boundary, without moving
        # the incumbent away from its accepted constrained solution.
        probe = np.clip(x, lower + h, upper - h)
        center = float(score(probe))
        plus = np.array([score(probe + d) for d in eye])
        minus = np.array([score(probe - d) for d in eye])
        gradient = (plus - minus) / (2 * h)
        hessian = np.diag((plus + minus - 2 * center) / h**2)
        cross = (
            score(probe + eye[0] + eye[1])
            - score(probe + eye[0] - eye[1])
            - score(probe - eye[0] + eye[1])
            + score(probe - eye[0] - eye[1])
        ) / (4 * h**2)
        hessian[0, 1] = hessian[1, 0] = cross
        eigenvalues, eigenvectors = np.linalg.eigh(hessian)
        direction = -(eigenvectors @ ((eigenvectors.T @ gradient) / np.maximum(0.01, eigenvalues)))
        direction *= min(1.0, 2.0 / max(1e-15, np.linalg.norm(direction)))
        history.append(
            dict(parameters=x.copy(), score=value, gradient=gradient, eigenvalues=eigenvalues)
        )
        projected = x - np.clip(x - gradient, lower, upper)
        if np.linalg.norm(projected) < 0.002:
            converged = True
            break
        accepted = False
        for step in 2.0 ** -np.arange(12):
            trial = np.clip(x + step * direction, lower, upper)
            proposed = float(score(trial))
            if proposed < value - 1e-9:
                x, value, accepted = trial, proposed, True
                break
        if not accepted:
            break
    return dict(parameters=x, score=value, history=history, converged=converged)
