"""Known-site restart experiment; diagnostic only, not a blind localization result."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from joint_inputs import _coordinates, _ecef
from oracle_position_diagnostic import reference_coordinates
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective
from rough_smoke import serializable
from soft_solvers import _project_bounds, _scaled_projected_gradient
from timing_model import DeadlineReached

STAGE_BUDGET_S = 30.
VARIANTS = ("baseline-profiled", "baseline-seed", "common-rf-profiled")


def projected_gradient(vector, gradient, bounds, scale):
    projected, free = _scaled_projected_gradient(vector, gradient, bounds, scale)
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and upper is not None and lower == upper:
            projected[index] = 0.
            free[index] = False
    return projected, free


def optimize(objective, start, bounds, *, budget_s=STAGE_BUDGET_S):
    if not 0 < budget_s <= STAGE_BUDGET_S:
        raise ValueError("stage budget must be in (0,30]")
    started = time.monotonic()
    objective.base.deadline = started + budget_s
    objective.best = None
    current = _project_bounds(np.asarray(start, dtype=float), bounds)
    value, gradient = objective.evaluate(current)
    trace = []
    damping = 1e-6
    status = "iteration_limit"
    for iteration in range(400):
        try:
            objective.base.check_deadline()
            projected, free = projected_gradient(current, gradient, bounds, objective.scale)
            norm = float(np.max(np.abs(projected)))
            trace.append({"iteration": iteration, "objective": value,
                          "gradient_norm": norm, "position_km": current[:2].copy(),
                          "elapsed_s": time.monotonic() - started})
            if norm <= 1e-3:
                status = "projected_gradient_converged"
                break
            hessian = objective.curvature(current)
            scaled = objective.scale[:, None] * hessian * objective.scale[None, :]
            diagonal_scale = max(1., float(np.max(np.diag(scaled))))
            accepted = False
            for _attempt in range(7):
                direction = np.zeros_like(current)
                direction[free] = np.linalg.solve(
                    scaled[np.ix_(free, free)]
                    + damping * diagonal_scale * np.eye(np.sum(free)), -projected[free])
                direction *= objective.scale
                for fraction in 2. ** -np.arange(12):
                    candidate = _project_bounds(current + fraction * direction, bounds)
                    derivative = float(gradient @ (candidate - current))
                    if derivative >= 0 or not objective.base.state(
                            candidate[:objective.size])["ephemeris_valid"]:
                        continue
                    candidate_value, candidate_gradient = objective.evaluate(candidate)
                    if candidate_value <= value + 1e-4 * derivative:
                        current, value, gradient = candidate, candidate_value, candidate_gradient
                        accepted = True
                        break
                if accepted:
                    damping = max(1e-12, damping / 10)
                    break
                damping *= 10
            if not accepted:
                status = "no_descent_step"
                break
        except DeadlineReached:
            status = "time_limit"
            break
    if objective.best["objective"] < value - 1e-8:
        current = objective.best["vector"]
    objective.base.deadline = float("inf")
    value, gradient = objective.evaluate(current)
    projected, _ = projected_gradient(current, gradient, bounds, objective.scale)
    norm = float(np.max(np.abs(projected)))
    success = norm <= 1e-3
    if success:
        status = "projected_gradient_converged"
    elif status == "projected_gradient_converged":
        status = "retained_state_not_converged"
    trace.append({"iteration": len(trace), "objective": value, "gradient_norm": norm,
                  "position_km": current[:2].copy(), "elapsed_s": time.monotonic() - started})
    return {"vector": current.copy(), "objective": value, "gradient": gradient,
            "success": bool(success), "status": status, "projected_gradient_inf_norm": norm,
            "trace": trace, "elapsed_s": time.monotonic() - started, "budget_s": budget_s}


def descent_audit(objective, vector):
    objective.base.deadline = float("inf")
    value, gradient = objective.evaluate(vector)
    position_gradient = gradient[:2]
    norm = float(np.linalg.norm(position_gradient))
    differences = []
    for axis in (0, 1):
        delta = np.zeros_like(vector)
        delta[axis] = .001
        upper = objective.evaluate(vector + delta)[0]
        lower = objective.evaluate(vector - delta)[0]
        differences.append((upper - lower) / .002)
    steps = []
    if norm > 0:
        direction = -position_gradient / norm
        for distance in (.0001, .001, .01):
            candidate = vector.copy()
            candidate[:2] += distance * direction
            candidate_value, _ = objective.evaluate(candidate)
            steps.append({"step_m": distance * 1000,
                          "loss_change": candidate_value - value})
    return {"objective": value, "gradient_per_km": position_gradient,
            "central_difference_gradient_per_km": differences,
            "fixed_nuisance_downhill_steps": steps,
            "scope": "Only position moves; nuisance parameters stay fixed at the profiled state. "
                     "A strictly negative change disproves local minimality of this joint state."}


def run_case(cell):
    session, variant = cell
    if variant not in VARIANTS:
        raise ValueError("unknown restart variant")
    output = ROOT / "truth-start-diagnostic" / f"{session}-{variant}.json"
    if output.exists():
        raise FileExistsError(output)
    paths = {"seed": ROOT / "scans" / session / "seed.json",
             "reference": ROOT / "scans" / session / "evaluation.json",
             "profile": ROOT / "profile-path-diagnostic" / f"{session}.json",
             "parent": ROOT / "runs-continuation" / session / "medium" / "fit.json",
             "rf_parent": ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"}
    records = {key: json.loads(path.read_text()) for key, path in paths.items()}
    inherited = {}
    for record in records.values():
        if "source_hashes" in record:
            assert_snapshot_unchanged(record["source_hashes"])
            inherited.update(record["source_hashes"])
    hashes = {**inherited, **snapshot_files([__file__, *paths.values()])}
    reference = records["reference"]["reference_site"]
    true_position = reference_coordinates(reference["latitude_deg"], reference["longitude_deg"])
    truth_ecef = _ecef(reference["latitude_deg"], reference["longitude_deg"])
    _, data = load_scan(session)
    satellites = np.asarray(records["seed"]["satellites"], dtype=int)
    common_rf = variant == "common-rf-profiled"
    if common_rf:
        parent = records["rf_parent"]["fit"]
        initial = np.asarray(parent["parameters"])
    elif variant == "baseline-profiled":
        parent = records["parent"]["fit"]
        initial = np.asarray(records["profile"]["stations"][-1]["parameters"])
    else:
        parent = records["parent"]["fit"]
        initial = np.asarray(records["seed"]["initial"])
        initial[:2] = true_position
    objective = CalibrationObjective(data, initial, satellites, False, STAGE_BUDGET_S)
    bounds = list(objective.bounds)
    if not common_rf:
        bounds[-1] = (0., 0.)
    current = objective.initial.copy()
    if common_rf:
        current[-1] = parent["rf_coefficient_hz_per_ghz"][0]
    phases = []
    positions = ([current[:2] + fraction * (true_position - current[:2])
                  for fraction in (.25, .5, .75, 1.)] if common_rf else [true_position])
    for position in positions:
        fixed_bounds = list(bounds)
        fixed_bounds[:2] = [(coordinate, coordinate) for coordinate in position]
        current[:2] = position
        fitted = optimize(objective, current, fixed_bounds)
        current = fitted["vector"].copy()
        np.testing.assert_array_equal(current[:2], position)
        phases.append(fitted)
    np.testing.assert_allclose(current[:2], true_position, rtol=0, atol=1e-12)
    start = current.copy()
    audit = descent_audit(objective, start)
    fitted = optimize(objective, start, bounds)
    final_vector = fitted["vector"]
    state = objective.base.state(final_vector[:objective.size])
    final_position = _ecef(*_coordinates(final_vector[:2]))
    parent_position = _ecef(*_coordinates(np.asarray(parent["parameters"])[:2]))
    result = {"schema": "ds13-truth-start-diagnostic/v1", "session": session,
              "variant": variant, "source_hashes": hashes, "reference_used_for_fitting": True,
              "parameters": state["parameters"], "true_position_km": true_position,
              "rf_coefficient_hz_per_ghz": final_vector[objective.size:],
              "nuisance_profile_phases": phases, "start_vector": start,
              "start_audit": audit, "fit": fitted,
              "final_error_km": float(np.linalg.norm(final_position - truth_ecef)),
              "distance_to_previous_solution_km": float(np.linalg.norm(
                  final_position - parent_position)),
              "loss_decrease_from_truth": audit["objective"] - fitted["objective"],
              "previous_solution_objective": parent["objective"],
              "scope": "Known-position diagnostic with all original observations and priors. "
                       "Baseline fixes RF coefficient to zero. Common-RF profiles position in "
                       "four gradual steps before release. No global-optimality certificate; "
                       "other nuisance/association basins at the known site remain possible."}
    assert_snapshot_unchanged(hashes)
    output.parent.mkdir(exist_ok=True)
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "variant": variant, "final_error_km": result["final_error_km"],
            "loss_decrease": result["loss_decrease_from_truth"], "success": fitted["success"],
            "gradient_at_truth": audit["gradient_per_km"].tolist(),
            "distance_to_previous_km": result["distance_to_previous_solution_km"]}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for row in executor.map(run_case, [(session, variant) for variant in VARIANTS
                                          for session in sessions]):
            print(json.dumps(row), flush=True)
