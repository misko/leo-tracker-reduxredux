"""Paired local DS7 refits with an optional shared native frequency slope."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def fit(evaluator, warm, free_slope, receipt=lambda row: None):
    dimension = 4 if free_slope else 3
    bounds = [(-12, 12), (-12, 12), (-5, 5)] + ([(-20, 20)] if free_slope else [])
    runs = []

    def objective(point):
        x = np.r_[point, 0.0] if not free_slope else point
        value = evaluator(x)
        return -value["score"], -value["gradient"][:dimension]

    for delta in (0.0, -0.25, 0.25):
        start = np.r_[warm[:2], np.clip(warm[2] + delta, -5, 5)]
        if free_slope:
            start = np.r_[start, 0.0]
        result = minimize(
            objective,
            start,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 100, "maxfun": 180, "ftol": 1e-10, "gtol": 1e-5, "maxls": 30},
        )
        boundary = any(
            min(abs(v - low), abs(v - high)) < 1e-3
            for v, (low, high) in zip(result.x, bounds, strict=True)
        )
        row = {
            "timing_start_delta_s": delta,
            "start": start.tolist(),
            "x": result.x.tolist(),
            "training_log_score": -float(result.fun),
            "gradient": (-result.jac).tolist(),
            "success": bool(result.success),
            "message": str(result.message),
            "boundary_hit": boundary,
            "qualified": bool(
                result.success and not boundary and np.max(np.abs(result.jac)) <= 0.01
            ),
            "iterations": int(result.nit),
            "evaluations": int(result.nfev),
        }
        runs.append(row)
        receipt(row)
    successful = [r for r in runs if r["success"]]
    return {
        "free_slope": free_slope,
        "starts": runs,
        "selected": max(successful, key=lambda r: r["training_log_score"]) if successful else None,
    }
