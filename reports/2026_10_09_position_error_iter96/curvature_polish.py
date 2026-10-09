"""Roundoff-bounded scalar Newton qualification; no reference inputs."""

import sys
from pathlib import Path

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_09_position_error_iter94"))
from coordinate_polish import projected_gradient  # noqa: E402

PROBE = 1e-5
DAMPING = (1.0, 0.5, 0.25)
ULPS = 128


def polish(
    objective,
    start,
    *,
    maximum_rounds=10,
    maximum_evaluations=100,
    rf_arm="fitted-c",
    fixed_position=True,
    slope_half_width_hz_s=60,
):
    """Refine KKT without treating sub-roundoff objective changes as meaningful.

    Every accepted state stays below initial objective plus one fixed128ULP bound.
    Among objective-equivalent candidates use full independent KKT, then objective.
    No relaxation of the0.001 qualification gate or cumulative score tolerance.
    """
    for value, upper, name in (
        (maximum_rounds, 10, "maximum_rounds"),
        (maximum_evaluations, 100, "maximum_evaluations"),
    ):
        if isinstance(value, bool) or int(value) != value or not 1 <= value <= upper:
            raise ValueError(f"{name} must be an integer in [1,{upper}]")
    original = np.asarray(start, float)
    problem = _Problem(
        objective,
        original,
        rf_arm=rf_arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=slope_half_width_hz_s,
    )
    if not problem.feasible(original):
        raise ValueError("Start must satisfy unchanged physical constraints and RF locks")
    evaluations, trials, accepted = 0, [], []

    def evaluate(vector):
        nonlocal evaluations
        evaluations += 1
        value, gradient, _ = objective.evaluate(vector)
        gradient = np.asarray(gradient, float)
        if (
            not np.isfinite(value)
            or gradient.shape != vector.shape
            or not np.isfinite(gradient).all()
        ):
            raise ValueError("Exact objective and gradient must be finite")
        return float(value), gradient.copy(), problem.stationarity(vector, gradient)

    vector = original.copy()
    value, gradient, kkt = evaluate(vector)
    initial_value = value
    tolerance = float(ULPS * abs(np.spacing(initial_value)))
    ceiling = initial_value + tolerance
    reason = "round-budget"

    def trial(candidate, round_index, coordinate, scaled_step, kind, damping=None):
        row = dict(
            round=round_index,
            coordinate=coordinate,
            scaled_step=float(scaled_step),
            kind=kind,
            damping=damping,
            vector=candidate.tolist(),
            feasible=problem.feasible(candidate),
            evaluated=False,
            objective=None,
            stationarity=None,
        )
        trials.append(row)
        if not row["feasible"]:
            row["reason"] = "outside unchanged physical constraints"
            return None
        if evaluations >= maximum_evaluations:
            row["reason"] = "evaluation budget"
            return None
        try:
            candidate_value, candidate_gradient, candidate_kkt = evaluate(candidate)
            row.update(
                evaluated=True,
                objective=candidate_value,
                gradient=candidate_gradient.tolist(),
                stationarity=candidate_kkt,
                within_initial_score_ceiling=candidate_value <= ceiling,
            )
            return dict(
                vector=candidate,
                objective=candidate_value,
                gradient=candidate_gradient,
                stationarity=candidate_kkt,
                trial_index=len(trials) - 1,
            )
        except Exception as error:
            row.update(evaluated=True, error=repr(error), reason="objective evaluation failed")
            return None

    for round_index in range(maximum_rounds):
        if kkt <= 0.001:
            reason = "independently-qualified"
            break
        if evaluations >= maximum_evaluations:
            reason = "evaluation-budget"
            break
        projected = projected_gradient(problem, vector, gradient)
        np.testing.assert_allclose(np.max(abs(projected), initial=0), kkt, atol=1e-12, rtol=1e-12)
        coordinate = int(problem.free[int(np.argmax(abs(projected)))])
        raw = float(gradient[coordinate] * problem.scales[coordinate])
        probes = {}
        for sign in (1, -1):
            candidate = vector.copy()
            candidate[coordinate] += sign * PROBE * problem.scales[coordinate]
            probes[sign] = trial(candidate, round_index, coordinate, sign * PROBE, "curvature")
        plus, minus = probes[1], probes[-1]
        if plus is not None and minus is not None:
            curvature = float(
                (plus["gradient"][coordinate] - minus["gradient"][coordinate])
                * problem.scales[coordinate]
                / (2 * PROBE)
            )
            method = "central-gradient-difference"
        elif plus is not None:
            curvature = float(
                (plus["gradient"][coordinate] * problem.scales[coordinate] - raw) / PROBE
            )
            method = "forward-gradient-difference"
        elif minus is not None:
            curvature = float(
                (raw - minus["gradient"][coordinate] * problem.scales[coordinate]) / PROBE
            )
            method = "backward-gradient-difference"
        else:
            reason = (
                "evaluation-budget"
                if evaluations >= maximum_evaluations
                else "no-feasible-curvature-probe"
            )
            break
        if not np.isfinite(curvature) or curvature <= 0:
            reason = "nonpositive-or-nonfinite-curvature"
            break
        step = -raw / curvature
        candidates = []
        for damping in DAMPING:
            candidate = vector.copy()
            candidate[coordinate] += damping * step * problem.scales[coordinate]
            result = trial(candidate, round_index, coordinate, damping * step, "newton", damping)
            trials[-1].update(
                raw_scaled_derivative=raw,
                curvature=curvature,
                curvature_method=method,
                newton_step=step,
            )
            if result is not None and result["objective"] <= ceiling:
                candidates.append(result)
        # Objective has priority outside numeric equivalence; within it choose KKT.
        pool = [
            dict(
                vector=vector, objective=value, gradient=gradient, stationarity=kkt, trial_index=-1
            ),
            *candidates,
        ]
        best_score = min(row["objective"] for row in pool)
        equivalent = [row for row in pool if row["objective"] <= best_score + tolerance]
        chosen = min(
            equivalent, key=lambda row: (row["stationarity"], row["objective"], row["trial_index"])
        )
        if chosen["trial_index"] < 0 or chosen["stationarity"] >= kkt:
            reason = (
                "evaluation-budget"
                if evaluations >= maximum_evaluations
                else "no-kkt-improving-admissible-step"
            )
            break
        accepted.append(
            dict(
                round=round_index,
                trial_index=chosen["trial_index"],
                before_objective=value,
                after_objective=chosen["objective"],
                before_stationarity=kkt,
                after_stationarity=chosen["stationarity"],
                coordinate=coordinate,
                curvature=curvature,
                curvature_method=method,
            )
        )
        vector, value, gradient, kkt = (
            chosen[k] for k in ("vector", "objective", "gradient", "stationarity")
        )
        vector, gradient = vector.copy(), gradient.copy()
    if kkt <= 0.001:
        reason = "independently-qualified"
    elif evaluations >= maximum_evaluations:
        reason = "evaluation-budget"
    assert value <= ceiling
    return dict(
        vector=vector,
        objective=value,
        initial_objective=initial_value,
        initial_vector=original.copy(),
        objective_tolerance=tolerance,
        objective_ceiling=ceiling,
        gradient=gradient,
        stationarity=kkt,
        converged=kkt <= 0.001,
        stop_reason=reason,
        evaluations=evaluations,
        rounds=len(accepted),
        trials=trials,
        accepted=accepted,
        helper_start_delta=problem.start - original,
        physical_constraints_minimum=float(problem.constraints(vector).min()),
        maximum_rounds=maximum_rounds,
        maximum_evaluations=maximum_evaluations,
        probe=PROBE,
        damping=list(DAMPING),
        tolerance_ulps=ULPS,
        fixed_position=fixed_position,
        rf_arm=rf_arm,
    )
