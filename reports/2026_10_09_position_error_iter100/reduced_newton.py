"""Bounded reduced-Hessian Newton qualification on the current active face."""

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem

PROBE = 1e-5
DAMPING = (1.0, 0.5, 0.25)
ULPS = 128


def tangent_basis(problem, vector):
    free, scales = problem.free, problem.scales
    rows = list((problem.jacobian(vector) * scales)[:, free][problem.constraints(vector) <= 1e-6])
    z, low, high = (value / scales for value in (vector, problem.lower, problem.upper))
    identity = np.eye(len(free))
    for i, coordinate in enumerate(free):
        if z[coordinate] <= low[coordinate] + 1e-7:
            rows.append(identity[i])
        if z[coordinate] >= high[coordinate] - 1e-7:
            rows.append(-identity[i])
    if rows:
        normals = np.asarray(rows)
        _, singular, vt = np.linalg.svd(normals, full_matrices=True)
        tolerance = np.finfo(float).eps * max(normals.shape) * singular.max(initial=0)
        rank = int(np.sum(singular > tolerance))
        null = vt[rank:].T
    else:
        rank, null = 0, identity
    physical = np.zeros((len(vector), null.shape[1]))
    physical[free] = scales[free, None] * null
    return physical, dict(active_count=len(rows), active_rank=rank, tangent_dimension=null.shape[1])


def polish(
    objective,
    start,
    *,
    maximum_rounds=2,
    maximum_evaluations=100,
    rf_arm="fitted-c",
    fixed_position=True,
    slope_half_width_hz_s=60,
):
    for value, limit in ((maximum_rounds, 2), (maximum_evaluations, 100)):
        if isinstance(value, bool) or int(value) != value or not 1 <= value <= limit:
            raise ValueError("Invalid bounded Newton budget")
    original = np.asarray(start, float).copy()
    problem = _Problem(
        objective,
        original,
        rf_arm=rf_arm,
        fixed_position=fixed_position,
        slope_half_width_hz_s=slope_half_width_hz_s,
    )
    if not problem.feasible(original):
        raise ValueError("Original state is infeasible; do not replace it with helper projection")
    evaluations, trials, accepted, curvature_audits = 0, [], [], []

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
        return float(value), gradient.copy(), problem.stationarity(vector, gradient)

    vector = original.copy()
    value, gradient, kkt = evaluate(vector)
    initial = value
    tolerance = float(ULPS * abs(np.spacing(initial)))
    ceiling = initial + tolerance
    reason = "round-budget"
    for round_index in range(maximum_rounds):
        if kkt <= 0.001:
            reason = "independently-qualified"
            break
        basis, geometry = tangent_basis(problem, vector)
        dimension = basis.shape[1]
        if not dimension:
            reason = "empty-active-face"
            break
        if evaluations + 2 * dimension + 1 > maximum_evaluations:
            reason = "insufficient-budget-for-curvature"
            break

        def trial(candidate, kind, detail, round_index=round_index):
            row = dict(
                round=round_index,
                kind=kind,
                vector=candidate.tolist(),
                feasible=problem.feasible(candidate),
                evaluated=False,
                **detail,
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

        hessian = np.zeros((dimension, dimension))
        failed = False
        for column in range(dimension):
            plus = trial(
                vector + PROBE * basis[:, column], "curvature", dict(column=column, sign=1)
            )
            minus = trial(
                vector - PROBE * basis[:, column], "curvature", dict(column=column, sign=-1)
            )
            if plus is None or minus is None:
                failed = True
                break
            hessian[:, column] = basis.T @ (plus["gradient"] - minus["gradient"]) / (2 * PROBE)
        if failed:
            reason = "no-feasible-central-curvature"
            break
        symmetric = 0.5 * (hessian + hessian.T)
        eigenvalues = np.linalg.eigvalsh(symmetric)
        threshold = np.finfo(float).eps * dimension * np.max(abs(eigenvalues), initial=0)
        curvature_audits.append(
            dict(
                round=round_index,
                hessian=symmetric.tolist(),
                asymmetry_max=float(np.max(abs(hessian - hessian.T))),
                eigenvalues=eigenvalues.tolist(),
                positive_definite_threshold=float(threshold),
                **geometry,
            )
        )
        if not np.isfinite(eigenvalues).all() or eigenvalues.min() <= threshold:
            reason = "reduced-hessian-not-positive-definite"
            break
        reduced_gradient = basis.T @ gradient
        reduced_step = -np.linalg.solve(symmetric, reduced_gradient)
        physical_step = basis @ reduced_step
        candidates = []
        for damping in DAMPING:
            candidate = trial(
                vector + damping * physical_step,
                "newton",
                dict(
                    damping=damping,
                    reduced_step=reduced_step.tolist(),
                    physical_step=physical_step.tolist(),
                ),
            )
            if candidate is not None and candidate["objective"] <= ceiling:
                candidates.append(candidate)
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
            )
        )
        vector, value, gradient, kkt = (
            chosen[key] for key in ("vector", "objective", "gradient", "stationarity")
        )
    if kkt <= 0.001:
        reason = "independently-qualified"
    elif evaluations >= maximum_evaluations:
        reason = "evaluation-budget"
    assert value <= ceiling and evaluations <= maximum_evaluations
    return dict(
        vector=vector,
        objective=value,
        initial_objective=initial,
        initial_vector=original,
        gradient=gradient,
        stationarity=kkt,
        converged=kkt <= 0.001,
        stop_reason=reason,
        evaluations=evaluations,
        rounds=len(accepted),
        trials=trials,
        accepted=accepted,
        curvature_audits=curvature_audits,
        objective_ceiling=ceiling,
        objective_tolerance=tolerance,
        helper_start_delta=problem.start - original,
        physical_constraints_minimum=float(problem.constraints(vector).min()),
        fixed_position=fixed_position,
        rf_arm=rf_arm,
        maximum_rounds=maximum_rounds,
        maximum_evaluations=maximum_evaluations,
    )
