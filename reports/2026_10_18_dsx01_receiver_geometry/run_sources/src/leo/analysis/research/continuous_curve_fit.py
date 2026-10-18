"""Small numerical controls for continuous, fixed-family localization probes.

These helpers make no satellite identities or geographic priors. Affine
projection is a discovery diagnostic, not a final residual acceptance test.
"""

import numpy as np

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles


def paired_phase_frequency(bank, times, labels, phases, latitude, longitude, *, altitude_m=0.0):
    """Evaluate one nominated satellite per observation without a dense grid.

    Uses exactly the same linear state interpolation and Earth rotation as
    phase_shifted_states, with no extrapolation. Duplicate times are allowed.
    """
    t, j, phi = np.asarray(times), np.asarray(labels), np.asarray(phases)
    if not np.isfinite(altitude_m):
        raise ValueError("finite receiver altitude required")
    knots = np.asarray(bank["time_s"])
    if t.ndim != 1 or j.shape != t.shape or not np.issubdtype(j.dtype, np.integer):
        raise ValueError("one integer satellite label per observation required")
    if (
        not np.isfinite(t).all()
        or not np.isfinite(phi).all()
        or np.any(j < 0)
        or np.any(j >= len(phi))
    ):
        raise ValueError("finite observation times and valid satellite labels required")
    requested = t + phi[j]
    if np.any(requested < knots[0]) or np.any(requested > knots[-1]):
        raise ValueError("phase interpolation never extrapolates")
    index = np.clip(np.searchsorted(knots, requested, side="right") - 1, 0, len(knots) - 2)
    fraction = (requested - knots[index]) / (knots[index + 1] - knots[index])
    angle = EARTH_ROTATION_RAD_S * phi[j]
    cosine, sine = np.cos(angle), np.sin(angle)
    states = []
    for key in ("position_km", "velocity_km_s"):
        source = np.asarray(bank[key])
        values = source[j, index] + fraction[:, None] * (source[j, index + 1] - source[j, index])
        x, y = values[:, 0].copy(), values[:, 1].copy()
        values[:, 0], values[:, 1] = cosine * x - sine * y, sine * x + cosine * y
        states.append(values)
    _, elevation, _, rate = look_angles(
        *states,
        geodetic_to_ecef_km(latitude, longitude, altitude_m),
        ecef_to_enu_matrix(latitude, longitude),
    )
    return -11.5e9 * rate / 299792.458, elevation


def project_curve(raw, inverse, times, *, affine=False, bias_sigma=1000.0):
    """Profile a Gaussian constant, or remove an unpenalized affine subspace.

    Return residual coordinates whose squared norm is the profiled quadratic
    including the Gaussian constant prior. Alias integers must be fixed by the
    caller before optimization, so there is no rounding cliff in this helper.
    """
    raw, w, t = np.asarray(raw), np.asarray(inverse), np.asarray(times)
    if raw.ndim != 1 or t.shape != raw.shape or w.shape != (len(t), len(t)):
        raise ValueError("matching curve, time and inverse covariance dimensions required")
    if not np.isfinite(raw).all() or not np.isfinite(w).all() or not np.isfinite(t).all():
        raise ValueError("finite curve inputs required")
    z = w @ raw
    if affine:
        x = np.column_stack((np.ones(len(t)), t - t.mean()))
        wx = w @ x
        coefficient = np.linalg.lstsq(wx, z, rcond=None)[0]
        return z - wx @ coefficient
    if not np.isfinite(bias_sigma) or bias_sigma <= 0:
        raise ValueError("positive finite Gaussian bias sigma required")
    one = w @ np.ones(len(t))
    bias = one @ z / (one @ one + 1 / bias_sigma**2)
    return np.r_[z - bias * one, bias / bias_sigma]


def robust_curve(residual, effective_points):
    """Smooth whole-curve Student-like cost; no residual acceptance gate."""
    z = np.asarray(residual)
    if effective_points <= 0:
        raise ValueError("positive effective support required")
    energy = float(z @ z) / effective_points
    scale = np.sqrt(np.log1p(energy) / energy) if energy > 1e-12 else 1.0
    return scale * z


def bounded_gauss_newton(residual, initial, lower, upper, *, iterations=24, step=1e-3):
    """Damped finite-difference least squares with explicit bounded iterates.

    Parameters must be scaled by the caller. The reported history records
    accepted iterates, including their objective, never a GPS accuracy test.
    """
    x, lo, hi = (np.asarray(a, float) for a in (initial, lower, upper))
    if x.ndim != 1 or lo.shape != x.shape or hi.shape != x.shape:
        raise ValueError("matching one-dimensional parameter bounds required")
    if np.any(lo >= hi) or step <= 0 or iterations < 1:
        raise ValueError("ordered bounds and positive numerical budgets required")
    x = np.clip(x, lo, hi)
    r = residual(x)
    score, damping, evaluations = float(r @ r), 1e-2, 1
    history = [dict(parameters=x.copy(), score=score)]
    stopped = "iteration_budget"
    for _ in range(iterations):
        columns = []
        for k in range(len(x)):
            a, b = x.copy(), x.copy()
            a[k], b[k] = max(lo[k], x[k] - step), min(hi[k], x[k] + step)
            columns.append((residual(b) - residual(a)) / (b[k] - a[k]))
            evaluations += 2
        jacobian = np.array(columns).T
        normal, gradient = jacobian.T @ jacobian, jacobian.T @ r
        diagonal = np.maximum(np.diag(normal), 1e-6)
        accepted = False
        for _trial in range(9):
            delta = np.linalg.solve(normal + damping * np.diag(diagonal), -gradient)
            proposal = np.clip(x + delta, lo, hi)
            rr = residual(proposal)
            evaluations += 1
            candidate = float(rr @ rr)
            if candidate < score - 1e-9:
                improvement = score - candidate
                x, r, score = proposal, rr, candidate
                history.append(dict(parameters=x.copy(), score=score))
                damping = max(1e-7, damping / 3)
                accepted = True
                if np.linalg.norm(delta[:2]) < 1e-4 and improvement < 1e-5:
                    stopped = "small_step_and_improvement"
                break
            damping *= 5
        if not accepted:
            stopped = "no_accepted_damped_step"
            break
        if stopped == "small_step_and_improvement":
            break
    return dict(
        parameters=x,
        score=score,
        history=history,
        evaluations=evaluations,
        stopped=stopped,
    )
