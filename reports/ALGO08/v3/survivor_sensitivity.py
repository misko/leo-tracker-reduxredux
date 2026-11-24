"""Measure local endpoint sensitivity after a zero-reference phase refresh."""

from time import perf_counter, process_time

import numpy as np


MAX_MOVE_KM = .010
VERIFY_MOVE_KM = .001
MAX_INFORMATION_CONDITION = 1e6


def endpoint_step(problem, point, forward_points):
    lower, upper = problem.lower, problem.upper
    if point.shape != (2,) or not np.isfinite(point).all() or np.any(point <= lower) or np.any(point >= upper):
        return dict(reason="nonfinite_or_boundary_warm_endpoint", evaluations=0)
    r = problem.residual(point)
    columns = [(problem.residual(nearby) - r) / separation
               for _, nearby, separation in forward_points(point, lower, upper, .001)]
    jacobian = np.column_stack(columns)
    gram = jacobian.T @ jacobian
    if not np.isfinite(gram).all() or not np.isfinite(r).all():
        return dict(reason="nonfinite_linearization", evaluations=3)
    eigenvalues = np.linalg.eigvalsh(gram)
    if eigenvalues[0] <= 0 or eigenvalues[1] > MAX_INFORMATION_CONDITION * eigenvalues[0]:
        return dict(reason="ill_conditioned_horizontal_information", evaluations=3)
    normal = gram + 1e-8 * np.diag(np.maximum(np.diag(gram), 1e-6))
    delta = np.linalg.solve(normal, -(jacobian.T @ r))
    if not np.isfinite(delta).all():
        return dict(reason="nonfinite_predicted_step", evaluations=3)
    predicted = point + delta
    movement = float(np.linalg.norm(delta))
    evidence = dict(information_eigenvalues=eigenvalues, movement_km=movement, evaluations=3)
    if np.any(predicted < lower) or np.any(predicted > upper):
        return dict(evidence, reason="outside_predicted_step")
    if movement > MAX_MOVE_KM:
        return dict(evidence, reason="predicted_step_over_10_m")
    if movement >= VERIFY_MOVE_KM:
        after = problem.residual(predicted)
        improvement = float((r - after) @ (r + after))
        evidence.update(evaluations=4)
        if not np.isfinite(improvement) or improvement <= 0:
            return dict(evidence, reason="exact_objective_did_not_improve")
        evidence["exact_objective_decrease"] = improvement
    return dict(evidence, reason=None)


def cold_reference_step(candidate, signed_means, arm, warm):
    from leo.analysis.localization_v3 import event_position as event
    from tools.pipeline_eval.variants.compact_cavity_optimizer import _forward_points

    scan, node, keep, powers, model, entries = (candidate[k] for k in (
        "scan", "node", "keep", "powers", "model", "entries"))

    def model_at(reference):
        problem = event.make_event_problem(scan, node, keep, arm, reference, powers, signed_means, model, [])
        return event.attach_event_predictive(problem, entries, powers)

    point = np.asarray(warm["endpoint_east_north_km"])
    zero = model_at(np.zeros_like(signed_means))
    phases = zero.state(point)["phases"][zero.labels]
    if not np.isfinite(phases).all():
        return dict(reason="nonfinite_zero_reference_phase", evaluations=1)
    reference = np.clip(phases, -15., 15.)
    step = endpoint_step(model_at(reference), point, _forward_points)
    return dict(step, evaluations=step["evaluations"] + 1,
                phase_reference_difference_s=float(np.max(abs(reference - warm["phase_reference"]))))


def pair(candidate, means, audit):
    from leo.analysis.localization_v3.history_policy import pair_passes
    from lighter_joint_estimator import warm_arm
    from named_survivor_fit import ARMS

    def clocks(start):
        return dict(cpu_s=process_time() - start[0], elapsed_s=perf_counter() - start[1])

    errors = (AssertionError, ValueError, np.linalg.LinAlgError)
    results, warm_reasons, stress = {}, {}, {}
    start = process_time(), perf_counter()
    for arm in ARMS:
        try:
            warm, reason = warm_arm(candidate, means, arm)
        except errors as exc:
            warm, reason = None, f"{type(exc).__name__}: {exc}"
        warm_reasons[arm] = reason
        if warm is not None:
            results[arm] = warm
    warm_passed = len(results) == len(ARMS) and pair_passes(
        results, include_linear=True, half_width_km=candidate["scan"].search_region.half_width_km)
    audit.update(warm_passed=bool(warm_passed), warm_reasons=warm_reasons, warm_clocks=clocks(start))
    start = process_time(), perf_counter()
    if warm_passed:
        for arm in ARMS:
            try:
                stress[arm] = cold_reference_step(candidate, means, arm, results[arm])
            except errors as exc:
                stress[arm] = dict(reason=f"{type(exc).__name__}: {exc}")
    accepted = warm_passed and all(row["reason"] is None for row in stress.values())
    audit.update(accepted=bool(accepted), stress=stress, stress_clocks=clocks(start))
    return results
