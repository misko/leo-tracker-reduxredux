"""Receiver-specific centered quadratic time-drift localization prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from coherent_fit import frozen_identity_masses
from prediction_plan import SharedPredictionPlan
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import candidate_ladder, frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


CURVATURE_PRIOR_SIGMA_HZ = 250.0
CURVATURE_BOUND_HZ = 1000.0
TIME_SCALE_S = 150.0
SLOPE_BOUND_HZ_S = 50.0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quadratic_time_basis(data):
    reference_time = float(getattr(data, "reference_time_s", TIME_SCALE_S))
    centered_time = np.asarray(data.times, dtype=float) - reference_time
    receiver = np.asarray(data.receiver, dtype=int)
    if centered_time.ndim != 1 or receiver.shape != centered_time.shape:
        raise ValueError("times and receiver must be matching vectors")
    if np.any(~np.isfinite(centered_time)):
        raise ValueError("times must be finite")
    if np.any((receiver < 0) | (receiver > 1)):
        raise ValueError("receiver values must be zero or one")
    normalized = centered_time / TIME_SCALE_S
    basis = normalized**2 - 1.0 / 3.0
    design = np.zeros((len(centered_time), 2))
    design[np.arange(len(centered_time)), receiver] = basis
    return design


def endpoint_slopes(parameters, coefficients_hz):
    parameters = np.asarray(parameters, dtype=float)
    coefficients = np.asarray(coefficients_hz, dtype=float)
    if parameters.ndim != 1 or len(parameters) < 6 or coefficients.shape != (2,):
        raise ValueError("parameters and coefficients have incompatible shapes")
    linear = parameters[[3, 5]]
    curvature_slope = 2.0 * coefficients / TIME_SCALE_S
    return np.column_stack([linear - curvature_slope, linear + curvature_slope])


def _specification(candidate_count, satellites):
    satellites = np.asarray(satellites, dtype=int)
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if len(np.unique(satellites)) != len(satellites):
        raise ValueError("satellites must be unique")
    if np.any(satellites < 0) or np.any(satellites >= candidate_count):
        raise ValueError("satellites contain an invalid candidate index")
    active = np.r_[np.arange(6), 6 + satellites]
    parameter_scales = np.r_[20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, np.ones(len(satellites))]
    coefficient_scales = np.full(2, CURVATURE_PRIOR_SIGMA_HZ)
    scales = np.r_[parameter_scales, coefficient_scales]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
    ]
    bounds += [(-3.0, 3.0)] * len(satellites)
    scaled_coefficient_bound = CURVATURE_BOUND_HZ / CURVATURE_PRIOR_SIGMA_HZ
    bounds += [(-scaled_coefficient_bound, scaled_coefficient_bound)] * 2
    constraint = np.zeros((4, len(scales)))
    curvature_derivative_scale = 2.0 * CURVATURE_PRIOR_SIGMA_HZ / TIME_SCALE_S
    constraint[0, 3] = 10.0
    constraint[0, -2] = -curvature_derivative_scale
    constraint[1, 3] = 10.0
    constraint[1, -2] = curvature_derivative_scale
    constraint[2, 5] = 10.0
    constraint[2, -1] = -curvature_derivative_scale
    constraint[3, 5] = 10.0
    constraint[3, -1] = curvature_derivative_scale
    return active, scales, bounds, constraint


def _constraint_violation(vector, bounds, constraint):
    values = constraint @ np.asarray(vector, dtype=float)
    violation = max(
        0.0,
        float(np.max(values - SLOPE_BOUND_HZ_S)),
        float(np.max(-SLOPE_BOUND_HZ_S - values)),
    )
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None:
            violation = max(violation, lower - vector[index])
        if upper is not None:
            violation = max(violation, vector[index] - upper)
    return float(max(0.0, violation))


def _evaluate_joint(
    vector,
    *,
    data,
    initial_parameters,
    satellites,
    prepared,
    masses,
    design,
    plan,
    active,
    scales,
):
    vector = np.asarray(vector, dtype=float)
    if vector.shape != scales.shape or np.any(~np.isfinite(vector)):
        raise ValueError("joint vector has the wrong shape or non-finite values")
    parameter_count = len(active)
    parameters = np.asarray(initial_parameters, dtype=float).copy()
    parameters[active] = vector[:parameter_count] * scales[:parameter_count]
    coefficients = vector[parameter_count:] * scales[parameter_count:]
    predicted, visible, jacobian = plan.predict(parameters)
    predicted = predicted.reshape(len(data.times), len(satellites))
    visible = visible.reshape(predicted.shape)
    predicted = predicted + (design @ coefficients)[:, None]
    result = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=200.0,
        **masses,
        track_contamination=0.2,
        return_gradient=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    if prediction_gradient.shape != predicted.shape or np.any(~np.isfinite(prediction_gradient)):
        raise FloatingPointError("prediction gradient is invalid")
    physical_gradient = -jacobian.transpose_multiply(prediction_gradient.ravel())
    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum(tau**2))
    physical_gradient[tau_indices] += tau
    coefficient_prior = 0.5 * float(
        np.sum((coefficients / CURVATURE_PRIOR_SIGMA_HZ) ** 2)
    )
    coefficient_gradient = -(design.T @ np.sum(prediction_gradient, axis=1))
    coefficient_gradient += coefficients / CURVATURE_PRIOR_SIGMA_HZ**2
    objective = float(-result["total_log_likelihood"] + tau_prior + coefficient_prior)
    gradient = np.r_[
        physical_gradient[active] * scales[:parameter_count],
        coefficient_gradient * scales[parameter_count:],
    ]
    if not np.isfinite(objective) or np.any(~np.isfinite(gradient)):
        raise FloatingPointError("joint objective or gradient is non-finite")
    diagnostics = dict(result)
    diagnostics.pop("prediction_gradient", None)
    return objective, gradient, parameters, coefficients, diagnostics, tau_prior, coefficient_prior


def fit_quadratic_trial(data, source_trial, prepared, *, budget_s=20.0):
    from scipy.optimize import LinearConstraint, minimize

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    initial_parameters = np.asarray(source_trial["parameters"], dtype=float)
    if initial_parameters.shape != (6 + len(data.numbers),) or np.any(
        ~np.isfinite(initial_parameters)
    ):
        raise ValueError("source parameters do not match the candidate pool")
    active, scales, bounds, constraint = _specification(len(data.numbers), satellites)
    coefficients = np.zeros(2)
    vector = np.r_[initial_parameters[active], coefficients] / scales
    if _constraint_violation(vector, bounds, constraint) > 1e-9:
        raise ValueError("sealed dense start violates the total endpoint slope bound")
    design = quadratic_time_basis(data)
    plan = SharedPredictionPlan(data, satellites)
    masses = source_trial["identity_masses"]
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(candidate, *, check_time=True):
        nonlocal evaluations, best
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("quadratic drift fit budget exhausted")
        evaluations += 1
        state = _evaluate_joint(
            candidate,
            data=data,
            initial_parameters=initial_parameters,
            satellites=satellites,
            prepared=prepared,
            masses=masses,
            design=design,
            plan=plan,
            active=active,
            scales=scales,
        )
        if _constraint_violation(candidate, bounds, constraint) <= 1e-7 and (
            best is None or state[0] < best[0]
        ):
            best = (state[0], np.asarray(candidate, dtype=float).copy())
        return state

    initial_state = evaluate(vector, check_time=False)
    optimizer_success = False
    optimizer_status = None
    message = ""
    iterations = None
    try:
        fitted = minimize(
            lambda candidate: evaluate(candidate)[:2],
            vector,
            method="SLSQP",
            jac=True,
            bounds=bounds,
            constraints=[
                LinearConstraint(
                    constraint,
                    np.full(4, -SLOPE_BOUND_HZ_S),
                    np.full(4, SLOPE_BOUND_HZ_S),
                )
            ],
            options={"maxiter": 500, "ftol": 1e-10},
        )
        optimizer_success = bool(fitted.success)
        optimizer_status = int(fitted.status)
        message = str(fitted.message)
        iterations = int(fitted.nit)
    except TimeoutError as error:
        message = str(error)
    if best is None:
        raise RuntimeError("quadratic drift fit produced no feasible finite state")
    final = evaluate(best[1], check_time=False)
    violation = _constraint_violation(best[1], bounds, constraint)
    slopes = endpoint_slopes(final[2], final[3])
    success = bool(optimizer_success and violation <= 1e-7)
    groups = len(final[4]["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(groups)
    coefficient_dof_penalty = np.log(groups)
    return {
        "parameters": final[2],
        "curvature_coefficients_hz": final[3],
        "endpoint_slopes_hz_s": slopes,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": message,
        "convergence_reason": "slsqp_converged" if success else "slsqp_unresolved",
        "optimizer_success": optimizer_success,
        "optimizer_status": optimizer_status,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final[0],
        "initial_objective": initial_state[0],
        "objective_improvement": float(initial_state[0] - final[0]),
        "selection_score": float(final[0] + entry_penalty + coefficient_dof_penalty),
        "entry_penalty": float(entry_penalty),
        "coefficient_dof_penalty": float(coefficient_dof_penalty),
        "curvature_prior": final[6],
        "tau_prior": final[5],
        "total_log_likelihood": float(final[4]["total_log_likelihood"]),
        "satellite_support": final[4]["satellite_support"],
        "null_support": float(final[4]["null_support"]),
        "track_unknown_responsibility": final[4]["track_unknown_responsibility"],
        "groups": groups,
        "identity_masses": masses,
        "constraint_violation_hz_s": violation,
        "gradient_inf_norm": float(np.max(np.abs(final[1]))),
        "evaluations": evaluations,
        "iterations": iterations,
        "elapsed_s": time.monotonic() - started,
        "best_feasible_finite_preserved": True,
        "gradient_method": "Joint analytic grouped-likelihood VJP with tau and curvature priors",
    }


def fit_quadratic_drift(data, source, *, budget_s=20.0):
    source_fit = source["fit"] if "fit" in source else source
    anchors = source_fit["anchors"]
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    capture_count = len(getattr(data, "child_sessions", [getattr(data, "session_id", None)]))
    ladder = candidate_ladder(
        source_fit["rough"]["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12)),
    )
    if not np.array_equal(ladder[-1][0], full_bank):
        raise ValueError("source full bank differs from its frozen rough ladder")
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    trials = []
    for satellites, _ in ladder:
        matches = [
            trial
            for trial in source_fit["trials"]
            if np.array_equal(np.asarray(trial["satellite_indices"]), satellites)
        ]
        if len(matches) != 1:
            raise ValueError("source must contain exactly one sealed trial per frozen bank")
        source_trial = matches[0]
        masses = frozen_identity_masses(anchors, full_bank, satellites)
        sealed_masses = source_trial["identity_masses"]
        if set(masses) != set(sealed_masses):
            raise ValueError("source identity-mass fields are incomplete")
        for key, value in masses.items():
            if not np.array_equal(np.asarray(value), np.asarray(sealed_masses[key])):
                raise ValueError(f"source {key} differs from frozen identity masses")
        trial = fit_quadratic_trial(data, source_trial, prepared, budget_s=budget_s)
        trial["source_objective"] = source_trial["objective"]
        trial["source_status"] = source_trial["status"]
        trials.append(trial)
    return {
        "rough": source_fit["rough"],
        "anchors": anchors,
        "full_bank": full_bank,
        "trials": trials,
        **select_trials(trials),
        "time_basis": "((time-reference_time_s)/150s)^2 - 1/3",
        "capture_period_s": 300.0,
        "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
        "curvature_bound_hz": CURVATURE_BOUND_HZ,
        "total_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "coefficient_count": 2,
        "bank_branches_independent": True,
        "bank_selection_reevaluated": True,
        "scope": (
            "Truth-free receiver quadratic-time drift prototype. Dense anchors, equal duplicate-"
            "adjusted row masses, candidate banks, identity masses, sigma, tau prior, and each "
            "bank's sealed dense start remain fixed. Two centered curvature coefficients are "
            "regularized and total linear-plus-quadratic slopes are constrained at both fixed "
            "300-second capture endpoints. No RF-dependent correction is present."
        ),
    }


def run_case(source_path, run_id, budget_s):
    source_path = Path(source_path)
    source = json.loads(source_path.read_text())
    if source.get("stage") != "dense_anchor":
        raise ValueError("source must be a sealed dense-anchor fit")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    _validate_source_provenance(source)
    unit = source["unit"]
    if unit["size"] != 1 or unit["unit_id"] not in ("DS10-S01", "DS11-S02"):
        raise ValueError("quadratic drift v1 is restricted to the two frozen pilots")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    sources = {
        path.name: digest(path)
        for path in sorted(ROOT.glob("*.py"))
        if not path.name.startswith("test_")
    }
    bundle = load_module(
        "quadratic_drift_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    started = time.monotonic()
    fitted = fit_quadratic_drift(data, source, budget_s=budget_s)
    receipt = {
        "schema": "multiscan-quadratic-drift-fit/v1",
        "stage": "quadratic_drift",
        "unit": unit,
        "dataset": source["dataset"],
        "run_id": run_id,
        "source_fit": str(source_path),
        "source_fit_sha256": digest(source_path),
        "selection_sha256": source["selection_sha256"],
        "inputs": source["inputs"],
        "source_hashes": sources,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "bank_sizes": [4, 8, 12],
            "budget_s_per_bank": float(budget_s),
            "time_scale_s": TIME_SCALE_S,
            "capture_period_s": 300.0,
            "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
            "curvature_bound_hz": CURVATURE_BOUND_HZ,
            "total_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
            "extra_dof": 2,
            "optimizer": "joint-slsqp-linear-endpoint-constraints",
        },
        "reference_read_before_seal": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    fit_sha256 = digest(fit_path)
    reference = json.loads(
        (ROOT / "scans" / unit["session_ids"][0] / "evaluation.json").read_text()
    )["reference_site"]
    expected = bundle._COMMON.ecef(reference["latitude_deg"], reference["longitude_deg"])
    errors = []
    for trial in fitted["trials"]:
        estimated = bundle._COMMON.ecef(*bundle._COMMON.coordinates(trial["parameters"][:2]))
        errors.append(
            {
                "satellite_count": trial["satellite_count"],
                "objective": trial["objective"],
                "selection_score": trial["selection_score"],
                "success": trial["success"],
                "status": trial["status"],
                "convergence_reason": trial["convergence_reason"],
                "curvature_coefficients_hz": trial["curvature_coefficients_hz"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-quadratic-drift-evaluation/v1",
        "unit_id": unit["unit_id"],
        "fit_sha256": fit_sha256,
        "trial_reference_errors": errors,
        "objective_selected_satellite_count": fitted["score_leader"]["satellite_count"],
        "selection_resolved": fitted["selection_resolved"],
        "eligible_for_cohort": False,
        "scope": "Post-seal reference evaluation only; no reference-derived fitting or selection.",
    }
    (output / "evaluation.json").write_text(json.dumps(serializable(evaluation), indent=2) + "\n")
    return receipt, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-fit", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--budget-s", type=float, default=20.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(args.source_fit, args.run_id, args.budget_s)
    print(
        json.dumps(
            serializable(
                {
                    "unit_id": receipt["unit"]["unit_id"],
                    "fit_sha256": evaluation["fit_sha256"],
                    "trial_reference_errors": evaluation["trial_reference_errors"],
                }
            )
        )
    )


if __name__ == "__main__":
    main()
