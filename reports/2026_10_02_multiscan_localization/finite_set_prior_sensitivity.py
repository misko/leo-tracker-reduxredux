"""Bound-conditional local response to satellite timing-prior precision."""

from __future__ import annotations

import numpy as np
from gauss_newton import _free_variables


def prior_sensitivity(hessian, total_gradient, prior_gradient, vector, bounds, scales):
    hessian = np.asarray(hessian, dtype=float)
    total_gradient = np.asarray(total_gradient, dtype=float)
    prior_gradient = np.asarray(prior_gradient, dtype=float)
    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(scales, dtype=float)
    size = len(vector)
    if (
        vector.ndim != 1 or size < 2 or hessian.shape != (size, size)
        or total_gradient.shape != (size,) or prior_gradient.shape != (size,)
        or scales.shape != (size,) or len(bounds) != size
        or any(np.any(~np.isfinite(value)) for value in (
            hessian, total_gradient, prior_gradient, vector, scales,
        )) or np.any(scales <= 0)
    ):
        raise ValueError("sensitivity inputs must be aligned finite scaled coordinates")
    if not np.allclose(hessian, hessian.T, rtol=1e-10, atol=1e-10):
        raise ValueError("Fisher matrix must be symmetric")
    free = _free_variables(vector, total_gradient, bounds)
    reduced = hessian[np.ix_(free, free)]
    result = {
        "available": False, "free_mask": free.tolist(),
        "position_response_km_per_unit_precision": None,
        "physical_response_per_unit_precision": None,
        "linearized_zero_precision_position_shift_km": None,
        "condition_number": None, "reason": None,
        "interpretation": (
            "Local complete-data Fisher approximation to dtheta/dlambda at lambda=1. "
            "Bounds and associations are fixed at the source. The zero-precision shift is "
            "a first-order extrapolation, not a refit or calibrated uncertainty."
        ),
    }
    if not np.any(free):
        result["reason"] = "no_free_parameters"
        return result
    eigenvalues = np.linalg.eigvalsh(reduced)
    if eigenvalues[0] <= 0:
        result["reason"] = "nonpositive_curvature"
        return result
    condition = float(eigenvalues[-1] / eigenvalues[0])
    result["condition_number"] = condition
    if condition > 1e12:
        result["reason"] = "ill_conditioned"
        return result
    response = np.zeros(size)
    response[free] = np.linalg.solve(reduced, -prior_gradient[free])
    if np.any(~np.isfinite(response)):
        result["reason"] = "nonfinite_solution"
        return result
    physical = response * scales
    residual = reduced @ response[free] + prior_gradient[free]
    result.update(
        available=True, reason="available",
        position_response_km_per_unit_precision=physical[:2].tolist(),
        physical_response_per_unit_precision=physical.tolist(),
        linearized_zero_precision_position_shift_km=(-physical[:2]).tolist(),
        linear_solve_residual_max_abs=float(np.max(np.abs(residual))),
    )
    return result
