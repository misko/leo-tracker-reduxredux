"""Small active-face scalar Newton polish with unchanged physical KKT acceptance."""

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem

PROBE = 1e-5
DAMPING = (1.0, 0.5, 0.25)
ULPS = 128


def tangent_direction(problem, vector, gradient):
    """Project onto the nullspace of the same active normals used by the KKT gate.

    This deliberately stays on all currently active faces. It cannot release a
    wrongly active constraint: full KKT, rather than reduced stationarity, still
    decides qualification. Fixed variables are absent from this scaled space.
    """
    free, scales = problem.free, problem.scales
    scaled_gradient = (gradient * scales)[free]
    jacobian = (problem.jacobian(vector) * scales)[:, free]
    normals = list(jacobian[problem.constraints(vector) <= 1e-6])
    scaled, lower, upper = (array / scales for array in (vector, problem.lower, problem.upper))
    eye = np.eye(len(free))
    for index, coordinate in enumerate(free):
        if scaled[coordinate] <= lower[coordinate] + 1e-7:
            normals.append(eye[index])
        if scaled[coordinate] >= upper[coordinate] - 1e-7:
            normals.append(-eye[index])
    if normals:
        matrix = np.asarray(normals)
        _, singular, vt = np.linalg.svd(matrix, full_matrices=True)
        tolerance = np.finfo(float).eps * max(matrix.shape) * singular.max(initial=0)
        rank = int(np.sum(singular > tolerance))
        null = vt[rank:].T
        projected = null @ (null.T @ scaled_gradient)
    else:
        rank, projected = 0, scaled_gradient.copy()
    norm = float(np.linalg.norm(projected))
    direction = np.zeros_like(vector)
    if norm > 0:
        direction[free] = -projected / norm * scales[free]
    return direction, dict(
        active_count=len(normals),
        active_rank=rank,
        tangent_dimension=len(free) - rank,
        tangent_gradient_norm=norm,
        directional_derivative=float(gradient @ direction),
    )


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
    """Use a single deterministic tangent direction each round; no position seeds."""
    for value, limit in ((maximum_rounds, 10), (maximum_evaluations, 100)):
        if isinstance(value, bool) or int(value) != value or not 1 <= value <= limit:
            raise ValueError("Invalid bounded polish budget")
    original = np.asarray(start, float).copy()
    problem = _Problem(
        objective,
        original,
        rf_arm=rf_arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=slope_half_width_hz_s,
    )
    if not problem.feasible(original):
        raise ValueError("Original state is infeasible; helper projection is not a new seed")
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
            raise ValueError("Nonfinite or malformed objective gradient")
        return float(value), gradient, problem.stationarity(vector, gradient)

    vector = original.copy()
    value, gradient, kkt = evaluate(vector)
    initial_value = value
    tolerance = float(ULPS * abs(np.spacing(value)))
    ceiling = value + tolerance
    reason = "round-budget"
    for round_index in range(maximum_rounds):
        if kkt <= 0.001:
            reason = "independently-qualified"
            break
        if evaluations >= maximum_evaluations:
            reason = "evaluation-budget"
            break
        direction, geometry = tangent_direction(problem, vector, gradient)
        derivative = geometry["directional_derivative"]
        if not np.isfinite(derivative) or derivative >= 0:
            reason = "no-descending-active-face-direction"
            break

        def trial(
            step,
            kind,
            vector=vector,
            direction=direction,
            round_index=round_index,
            geometry=geometry,
        ):
            candidate = vector + step * direction
            row = dict(
                round=round_index,
                kind=kind,
                scaled_step=float(step),
                vector=candidate.tolist(),
                feasible=problem.feasible(candidate),
                evaluated=False,
                geometry=geometry,
                direction=direction.tolist(),
            )
            trials.append(row)
            if not row["feasible"] or evaluations >= maximum_evaluations:
                return None
            try:
                result = evaluate(candidate)
            except Exception as error:
                row.update(evaluated=True, error=repr(error))
                return None
            row.update(
                evaluated=True,
                objective=result[0],
                gradient=result[1].tolist(),
                stationarity=result[2],
                within_initial_score_ceiling=result[0] <= ceiling,
            )
            return dict(
                vector=candidate,
                objective=result[0],
                gradient=result[1],
                stationarity=result[2],
                trial_index=len(trials) - 1,
            )

        plus, minus = trial(PROBE, "curvature"), trial(-PROBE, "curvature")
        if plus is not None and minus is not None:
            curvature = float((plus["gradient"] - minus["gradient"]) @ direction / (2 * PROBE))
            method = "central-directional-gradient"
        elif plus is not None:
            curvature = float((plus["gradient"] - gradient) @ direction / PROBE)
            method = "forward-directional-gradient"
        elif minus is not None:
            curvature = float((gradient - minus["gradient"]) @ direction / PROBE)
            method = "backward-directional-gradient"
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
        step = -derivative / curvature
        candidates = []
        for damping in DAMPING:
            candidate = trial(step * damping, "newton")
            trials[-1].update(curvature=curvature, curvature_method=method, damping=damping)
            if candidate is not None and candidate["objective"] <= ceiling:
                candidates.append(candidate)
        current = dict(
            vector=vector, objective=value, gradient=gradient, stationarity=kkt, trial_index=-1
        )
        pool = [current, *candidates]
        best_score = min(row["objective"] for row in pool)
        equivalent = [row for row in pool if row["objective"] <= best_score + tolerance]
        chosen = min(
            equivalent, key=lambda row: (row["stationarity"], row["objective"], row["trial_index"])
        )
        if chosen["trial_index"] < 0 or chosen["stationarity"] >= kkt:
            reason = "no-kkt-improving-admissible-step"
            break
        accepted.append(
            dict(
                round=round_index,
                trial_index=chosen["trial_index"],
                before_objective=value,
                after_objective=chosen["objective"],
                before_stationarity=kkt,
                after_stationarity=chosen["stationarity"],
                curvature=curvature,
                **geometry,
            )
        )
        vector, value, gradient, kkt = (
            chosen[key] for key in ("vector", "objective", "gradient", "stationarity")
        )
    if kkt <= 0.001:
        reason = "independently-qualified"
    elif evaluations >= maximum_evaluations:
        reason = "evaluation-budget"
    assert value <= ceiling
    return dict(
        vector=vector,
        objective=value,
        initial_objective=initial_value,
        initial_vector=original,
        gradient=gradient,
        stationarity=kkt,
        converged=kkt <= 0.001,
        stop_reason=reason,
        evaluations=evaluations,
        rounds=len(accepted),
        trials=trials,
        accepted=accepted,
        objective_ceiling=ceiling,
        objective_tolerance=tolerance,
        helper_start_delta=problem.start - original,
        physical_constraints_minimum=float(problem.constraints(vector).min()),
        fixed_position=fixed_position,
        rf_arm=rf_arm,
        maximum_rounds=maximum_rounds,
        maximum_evaluations=maximum_evaluations,
    )
