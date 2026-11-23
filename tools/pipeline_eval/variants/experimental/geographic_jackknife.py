"""Local exterior evidence from a signed paired fit and satellite deletions."""

import numpy as np
from scipy.special import ndtr, ndtri, stdtrit

from leo.analysis.localization_v3.reassociation_context import derivatives

ARMS = ("c0", "fitted_c")
FACES = ("west", "east", "south", "north")
FINE_KM, CHECK_KM = 0.025, 0.050


def clearances(point, half_width_km):
    east, north = point
    return half_width_km + np.array([east, -east, north, -north])


def separation_control(likelihood_scale_km):
    """Ideal Gaussian discrimination of two known points 200 m apart."""
    separation = 0.2 / likelihood_scale_km
    return dict(
        separation_sigma=float(separation),
        equal_prior_error=float(ndtr(-separation / 2)),
        power_at_5pct_false_withhold=float(ndtr(separation - ndtri(0.95))),
    )


def diagnose(loss, rebuilt_loss, satellites, endpoint_km, half_width_km):
    """Estimate the unrestricted local mode and its face-normal uncertainty."""
    if len(satellites) < 4:
        return dict(state="unresolved", reason="too_few_satellites")
    endpoint = np.asarray(endpoint_km, dtype=float)
    baseline = float(loss(endpoint))
    if not np.isfinite(baseline):
        return dict(state="unresolved", reason="nonfinite_objective")
    stencils = []
    for step in (FINE_KM, CHECK_KM):
        gradient, hessian = derivatives(loss, endpoint, h=step)
        if not np.isfinite(gradient).all() or not np.isfinite(hessian).all():
            return dict(state="unresolved", reason="nonfinite_derivatives")
        if np.linalg.eigvalsh(hessian)[0] <= 0:
            return dict(state="unresolved", reason="nonpositive_curvature")
        inverse = np.linalg.inv(hessian)
        stencils.append((gradient, hessian, inverse, -inverse @ gradient,
                         np.sqrt(2 * np.diag(inverse))))
    gradient, hessian, inverse, displacement, likelihood_scale = stencils[0]
    _, _, _, check_displacement, check_scale = stencils[1]
    estimate = endpoint + displacement
    if (np.any(abs(check_scale / likelihood_scale - 1) > 0.1)
            or np.any(abs(check_displacement - displacement) > 0.1 * likelihood_scale)
            or np.linalg.norm(displacement) > half_width_km / 4):
        return dict(state="unresolved", reason="unstable_local_extrapolation")
    quadratic_delta = float(gradient @ displacement + 0.5 * displacement @ hessian @ displacement)
    actual_delta = float(loss(estimate) - baseline)
    if (not np.isfinite(actual_delta)
            or abs(actual_delta - quadratic_delta) > 0.1 * max(1, abs(quadratic_delta))):
        return dict(state="unresolved", reason="nonquadratic_local_extrapolation")

    unit = np.eye(2) * FINE_KM
    stencil = [endpoint + i * unit[0] + j * unit[1] for i in (-1, 0, 1) for j in (-1, 0, 1)]
    rebuilt = rebuilt_loss(None)
    difference = [abs(rebuilt(point) - loss(point)) for point in stencil]
    if not np.isfinite(difference).all() or max(difference) > 1e-5:
        return dict(state="unresolved", reason="rebuilt_likelihood_mismatch")
    deleted = {}
    for satellite in satellites:
        reduced = rebuilt_loss(satellite)
        reduced_gradient = np.array(
            [(reduced(endpoint + delta) - reduced(endpoint - delta)) / (2 * FINE_KM)
             for delta in unit]
        )
        if not np.isfinite(reduced_gradient).all():
            return dict(state="unresolved", reason="nonfinite_deleted_derivatives")
        deleted[satellite] = endpoint - inverse @ reduced_gradient
    estimates = np.array(list(deleted.values()))
    groups = len(estimates)
    jackknife_scale = np.sqrt((groups - 1) * np.var(estimates, axis=0))
    effective_scale = np.maximum(likelihood_scale, jackknife_scale)
    multiplier = float(stdtrit(groups - 1, 1 - 0.05 / 8))
    clearance = clearances(estimate, half_width_km)
    margins = np.repeat(multiplier * effective_scale, 2)
    lower, upper = clearance - margins, clearance + margins
    exterior = [face for face, bound in zip(FACES, upper, strict=True) if bound < 0]
    state = "exterior" if exterior else "inside" if (lower > 0).all() else "unresolved"
    return dict(
        state=state, exterior_faces=exterior, endpoint_km=endpoint.tolist(),
        estimate_km=estimate.tolist(), displacement_km=displacement.tolist(),
        likelihood_scale_km=likelihood_scale.tolist(), jackknife_scale_km=jackknife_scale.tolist(),
        multiplier=multiplier, quadratic_delta=quadratic_delta, actual_delta=actual_delta,
        maximum_replay_difference=max(difference),
        deleted_estimates_km={str(sat): value.tolist() for sat, value in deleted.items()},
        faces={
            face: dict(
                clearance_km=float(clearance[i]),
                lower_km=float(lower[i]),
                upper_km=float(upper[i]),
                **separation_control(likelihood_scale[i // 2]),
            )
            for i, face in enumerate(FACES)
        },
    )


def paired_state(arms):
    first, second = (arms[arm] for arm in ARMS)
    if set(first.get("exterior_faces", ())) & set(second.get("exterior_faces", ())):
        return "exterior"
    if first["state"] == second["state"] == "inside":
        return "inside"
    return "unresolved"
