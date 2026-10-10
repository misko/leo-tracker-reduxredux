"""One exact-score-checked receiver-clock block step; no recording loader."""

import runpy
from pathlib import Path

import numpy as np

LINEAR = runpy.run_path(
    str(
        Path(__file__).resolve().parent.parent
        / "2026_10_09_position_error_iter91/linear_nuisance.py"
    )
)


def step(model, vector, clock, arm):
    """Freeze geometry/satellite terms; return original state on rejected step.

    This is a block update, never a claim of full nonlinear convergence. Two
    exact model evaluations suffice; no line search, retries or hidden fits.
    """
    vector, clock = np.asarray(vector, float).copy(), np.asarray(clock, float).copy()
    if (
        vector.shape != (model.size,)
        or clock.shape != model.initial_clock.shape
        or not np.isfinite(vector).all()
        or not np.isfinite(clock).all()
        or arm not in ("fitted-c", "zero-c")
        or not 0 < model.score.sigma_hz <= 1000
        or (arm == "zero-c" and (vector[6] != 0 or np.any(clock[-2:] != 0)))
        or (model.fixed_rf_drift and np.any(clock[-2:] != 0))
    ):
        raise ValueError("Invalid physical state, RF locks, or narrow-Gaussian model")
    lower, upper = LINEAR["receiver_clock_bounds"](
        clock, model.smooth_clock_count, arm, fixed_rf=model.fixed_rf_drift
    )
    if np.any(clock < lower) or np.any(clock > upper):
        raise ValueError("Infeasible receiver-clock start")
    before, _, _, terms = model.evaluate_joint(vector.copy(), clock.copy())
    if not np.isfinite(before):
        raise ValueError("Nonfinite original exact objective")
    collapsed = LINEAR["collapse_mixture"](
        terms.residual_hz, terms.responsibilities, model.score.sigma_hz
    )
    solved = LINEAR["solve_nuisance_delta"](
        model.clock_design,
        collapsed["residual_hz"],
        collapsed["weights"],
        clock,
        model.precision,
        lower,
        upper,
        constant=collapsed["constant"],
    )
    result = dict(
        vector=vector,
        clock_coefficients=clock.copy(),
        accepted=False,
        objective_before=float(before),
        objective_after=float(before),
        exact_evaluations=1,
        quadratic=solved,
        scope="Receiver block only; nonlinear qualification not evaluated",
    )
    if not solved["qualified"]:
        result["reason"] = "quadratic-unqualified"
        return result
    result["exact_evaluations"] += 1
    try:
        after = float(model.evaluate_joint(vector.copy(), solved["coefficients"].copy())[0])
    except Exception as exc:
        result.update(reason="exact-refresh-failed", error=repr(exc))
        return result
    result["trial_objective"] = after if np.isfinite(after) else None
    if not np.isfinite(after) or after > before:
        result["reason"] = "exact-score-rejected"
        return result
    result.update(
        accepted=True,
        reason="exact-score-nonincreasing",
        objective_after=after,
        clock_coefficients=solved["coefficients"].copy(),
    )
    return result
