"""Opt-in bounded annotation training with an explicit physical call budget."""

from copy import deepcopy

import numpy as np
from scipy.optimize import minimize

from leo.contracts.localization_v5 import annotation_training_policy


def fit(problem, start=(0.0, 0.0), iterations=48):
    """Fit the probe's unchanged residual-square objective and L-BFGS-B policy."""
    policy = deepcopy(annotation_training_policy())
    if iterations != 48:
        raise ValueError("Original 48 position steps required")
    x, lo, hi = (np.asarray(value, float).copy() for value in
                 (start, problem.lower, problem.upper))
    if (x.shape != (2,) or lo.shape != (2,) or hi.shape != (2,)
            or not np.isfinite([x, lo, hi]).all() or np.any(lo >= hi)):
        raise ValueError("Finite two-dimensional start and ordered bounds required")
    x = np.clip(x, lo, hi)
    history = []
    residual_size = None

    class Budget(Exception):
        pass

    def objective(at):
        nonlocal residual_size
        if len(history) >= policy["residual_call_cap"]:
            raise Budget("physical residual call cap reached")
        point = np.asarray(at, float).copy()
        if (point.shape != (2,) or not np.isfinite(point).all()
                or np.any(point < lo) or np.any(point > hi)):
            raise ValueError("Finite bounded two-dimensional evaluation required")
        value = np.asarray(problem.residual(point.copy()), float)
        if value.ndim != 1 or not value.size or not np.isfinite(value).all():
            raise ValueError("Nonempty finite one-dimensional residual required")
        if residual_size is None:
            residual_size = value.size
        elif value.size != residual_size:
            raise ValueError("Invariant residual length required")
        with np.errstate(over="ignore", invalid="ignore"):
            score = float(value @ value)
        if not np.isfinite(score):
            raise ValueError("Finite residual objective required")
        history.append(dict(parameters=point, score=score))
        return score

    stationarity = dict(source="scipy_result.jac", projected_gradient_inf_norm=None,
                        gtol=policy["options"]["gtol"], satisfied=None)
    try:
        result = minimize(objective, x, method="L-BFGS-B",
                          bounds=list(zip(lo, hi, strict=True)),
                          options=deepcopy(policy["options"]))
        x = np.asarray(result.x, float).copy()
        score = float(result.fun)
        if (x.shape != (2,) or not np.isfinite(x).all()
                or np.any(x < lo) or np.any(x > hi) or not np.isfinite(score)):
            raise ValueError("Finite bounded optimizer parameters and score required")
        if not any(np.array_equal(x, row["parameters"]) and score == row["score"]
                   for row in history):
            raise ValueError("Optimizer result must match an evaluated point and score")
        counts = {}
        for key in ("nfev", "njev", "nit"):
            value = result[key]
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
                raise ValueError("Nonnegative integer optimizer counts required")
            counts[key] = int(value)
            if value < 0:
                raise ValueError("Nonnegative integer optimizer counts required")
        if counts["nfev"] != len(history) or counts["njev"] > counts["nfev"]:
            raise ValueError("Optimizer counts must match physical residual evaluations")
        if (not isinstance(result.status, (int, np.integer))
                or isinstance(result.status, (bool, np.bool_))
                or not isinstance(result.success, (bool, np.bool_))):
            raise ValueError("Integer optimizer status and boolean success required")
        gradient = np.asarray(result.jac, float)
        if gradient.shape != (2,) or not np.isfinite(gradient).all():
            raise ValueError("Finite two-dimensional optimizer gradient required")
        with np.errstate(over="ignore"):
            projected = np.where(gradient < 0, np.maximum(gradient, x - hi),
                                 np.minimum(gradient, x - lo))
        norm = float(np.max(np.abs(projected)))
        stationarity.update(projected_gradient_inf_norm=norm,
                            satisfied=norm <= policy["options"]["gtol"])
        scipy_result = dict(counts, success=bool(result.success), status=int(result.status),
                            message=str(result.message))
        stopped = f"scipy_status_{result.status}: {result.message}"
        solution_origin = "scipy_result"
        budget_exhausted = bool(counts["nit"] >= policy["options"]["maxiter"]
                                or counts["nfev"] >= policy["options"]["maxfun"])
    except Budget as exc:
        best = min(history, key=lambda row: row["score"])
        x, score = best["parameters"].copy(), best["score"]
        stopped, scipy_result = str(exc), None
        solution_origin = "lowest evaluated score after physical call cap"
        budget_exhausted = True

    calculated = problem.calculate(x.copy())
    conditional = np.asarray(calculated["conditional_residual_hz"], float)
    keep = np.asarray(problem.keep)
    if (conditional.ndim != 1 or keep.shape != conditional.shape or keep.dtype != np.bool_
            or not keep.any() or not np.isfinite(conditional).all()):
        raise ValueError("Finite conditional residuals and matching nonempty boolean mask required")
    with np.errstate(over="ignore", invalid="ignore"):
        rms = float(np.sqrt(np.mean(conditional[keep] ** 2)))
    metadata = {}
    for key in ("normalization_constant", "negative_twice_elbo"):
        value = np.asarray(calculated[key], float)
        if value.shape != () or not np.isfinite(value):
            raise ValueError("Finite scalar final metadata required")
        metadata[key] = float(value)
    if not np.isfinite(rms):
        raise ValueError("Finite final residual RMS required")
    return dict(parameters=x, score=score, history=history, evaluations=len(history),
                stopped=stopped, optimizer_policy=deepcopy(policy),
                history_kind=policy["history_kind"], scipy_result=scipy_result,
                budget_exhausted=budget_exhausted,
                converged=bool(scipy_result and scipy_result["success"] and not budget_exhausted),
                convergence_kind="scipy-reported success within budget",
                stationarity=stationarity, solution_origin=solution_origin,
                final_metadata_calculate_calls=1, residual_rms_hz=rms,
                active_points=int(keep.sum()), **metadata)


fit.policy = annotation_training_policy()
