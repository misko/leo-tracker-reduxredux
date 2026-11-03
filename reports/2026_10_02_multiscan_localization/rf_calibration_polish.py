"""Joint analytic polish for sealed receiver RF-calibration pilot fits."""

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
from rf_calibration_fit import (
    COEFFICIENT_BOUND_HZ_GHZ,
    COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
    receiver_rf_design,
)
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import frozen_row_weights, select_trials
from track_likelihood import prepare_track_grouped_likelihood


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _specification(candidate_count, satellites):
    satellites = np.asarray(satellites, dtype=int)
    active = np.r_[np.arange(6), 6 + satellites]
    parameter_scales = np.r_[20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, np.ones(len(satellites))]
    coefficient_scales = np.full(2, COEFFICIENT_PRIOR_SIGMA_HZ_GHZ)
    scales = np.r_[parameter_scales, coefficient_scales]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-5.0, 5.0),
        (None, None),
        (-5.0, 5.0),
    ]
    bounds += [(-3.0, 3.0)] * len(satellites)
    coefficient_scaled_bound = COEFFICIENT_BOUND_HZ_GHZ / COEFFICIENT_PRIOR_SIGMA_HZ_GHZ
    bounds += [(-coefficient_scaled_bound, coefficient_scaled_bound)] * 2
    if np.any(satellites < 0) or np.any(satellites >= candidate_count):
        raise ValueError("satellites contain an invalid candidate index")
    if len(np.unique(satellites)) != len(satellites):
        raise ValueError("satellites must be unique")
    return active, scales, bounds


def _projected_gradient(vector, gradient, bounds):
    projected = np.asarray(gradient, dtype=float).copy()
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and vector[index] <= lower and gradient[index] > 0:
            projected[index] = 0.0
        if upper is not None and vector[index] >= upper and gradient[index] < 0:
            projected[index] = 0.0
    return projected


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
    parameters = np.asarray(initial_parameters, dtype=float).copy()
    parameter_count = len(active)
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
        np.sum((coefficients / COEFFICIENT_PRIOR_SIGMA_HZ_GHZ) ** 2)
    )
    coefficient_gradient = -(design.T @ np.sum(prediction_gradient, axis=1))
    coefficient_gradient += coefficients / COEFFICIENT_PRIOR_SIGMA_HZ_GHZ**2
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


def polish_joint(data, source_trial, prepared, design, *, budget_s=30.0):
    """Jointly polish base localization nuisances and two RF coefficients."""

    from scipy.optimize import minimize

    if not np.isfinite(budget_s) or not 0 < budget_s <= 30:
        raise ValueError("budget_s must lie in (0, 30]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    initial_parameters = np.asarray(source_trial["parameters"], dtype=float)
    initial_coefficients = np.asarray(source_trial["coefficients_hz_ghz"], dtype=float)
    candidate_count = len(data.numbers)
    if initial_parameters.shape != (6 + candidate_count,):
        raise ValueError("source parameters do not match the candidate pool")
    if initial_coefficients.shape != (2,) or np.any(~np.isfinite(initial_coefficients)):
        raise ValueError("source RF coefficients must contain two finite values")
    active, scales, bounds = _specification(candidate_count, satellites)
    vector = np.r_[initial_parameters[active], initial_coefficients] / scales
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None:
            vector[index] = max(vector[index], lower)
        if upper is not None:
            vector[index] = min(vector[index], upper)
    plan = SharedPredictionPlan(data, satellites)
    masses = source_trial["identity_masses"]
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(candidate, *, check_time=True):
        nonlocal evaluations, best
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("joint RF-calibration polish budget exhausted")
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
        if best is None or state[0] < best[0]:
            best = (state[0], np.asarray(candidate, dtype=float).copy())
        return state

    initial_state = evaluate(vector, check_time=False)
    initial_projected = _projected_gradient(vector, initial_state[1], bounds)
    optimizer_success = False
    optimizer_status = None
    message = ""
    iterations = None
    try:
        fitted = minimize(
            lambda candidate: evaluate(candidate)[:2],
            vector,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 1000, "maxfun": 2000, "ftol": 1e-12, "gtol": 1e-5},
        )
        optimizer_success = bool(fitted.success)
        optimizer_status = int(fitted.status)
        message = str(fitted.message)
        iterations = int(fitted.nit)
    except TimeoutError as error:
        message = str(error)
    final = evaluate(best[1], check_time=False)
    projected = _projected_gradient(best[1], final[1], bounds)
    projected_norm = float(np.max(np.abs(projected)))
    stationarity_resolved = bool(optimizer_success and projected_norm <= 1e-4)
    groups = len(final[4]["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(groups)
    coefficient_dof_penalty = np.log(groups)
    return {
        "parameters": final[2],
        "coefficients_hz_ghz": final[3],
        "coefficients_ppm": final[3] * 0.001,
        "success": stationarity_resolved,
        "status": "converged" if stationarity_resolved else "nonconverged",
        "message": message,
        "convergence_reason": "joint_projected_gradient"
        if stationarity_resolved
        else "joint_stationarity_unresolved",
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
        "coefficient_prior": final[6],
        "tau_prior": final[5],
        "total_log_likelihood": float(final[4]["total_log_likelihood"]),
        "satellite_support": final[4]["satellite_support"],
        "null_support": float(final[4]["null_support"]),
        "track_unknown_responsibility": final[4]["track_unknown_responsibility"],
        "groups": groups,
        "identity_masses": masses,
        "initial_projected_gradient_inf_norm": float(
            np.max(np.abs(initial_projected))
        ),
        "projected_gradient_inf_norm": projected_norm,
        "stationarity_threshold": 1e-4,
        "scaled_step_inf_norm": float(np.max(np.abs(best[1] - vector))),
        "evaluations": evaluations,
        "iterations": iterations,
        "elapsed_s": time.monotonic() - started,
        "best_finite_preserved": True,
        "gradient_method": "Joint analytic grouped-likelihood VJP with tau and RF priors",
    }


def fit_rf_calibration_polish(data, source, *, bank_budget_s=30.0):
    source_fit = source["fit"] if "fit" in source else source
    anchors = source_fit["anchors"]
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    prepared = prepare_track_grouped_likelihood(
        data.measured,
        data.group,
        row_weights=frozen_row_weights(data),
        anchors=[anchor["groups"] for anchor in anchors],
    )
    centers = np.asarray(source_fit["rf_centers_hz"], dtype=float)
    design = receiver_rf_design(data, centers)
    trials = []
    for source_trial in source_fit["trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        regenerated = frozen_identity_masses(anchors, full_bank, satellites)
        sealed = source_trial["identity_masses"]
        if set(regenerated) != set(sealed):
            raise ValueError("source identity-mass fields are incomplete")
        for key, value in regenerated.items():
            if not np.array_equal(np.asarray(value), np.asarray(sealed[key])):
                raise ValueError(f"source {key} differs from frozen identity masses")
        trials.append(
            polish_joint(data, source_trial, prepared, design, budget_s=bank_budget_s)
        )
    return {
        "rough": source_fit["rough"],
        "anchors": anchors,
        "full_bank": full_bank,
        "rf_centers_hz": centers,
        "coefficient_prior_sigma_hz_ghz": COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
        "coefficient_bound_hz_ghz": COEFFICIENT_BOUND_HZ_GHZ,
        "coefficient_count": 2,
        "trials": trials,
        **select_trials(trials),
        "scope": (
            "Joint analytic polish of sealed RF-calibration-v1 states. Candidate banks, "
            "anchors, identity masses, rows, RF centers, and starts remain frozen. No "
            "reference coordinates enter fitting or model selection."
        ),
    }


def run_case(source_path, run_id, bank_budget_s):
    source_path = Path(source_path)
    source = json.loads(source_path.read_text())
    if source.get("stage") != "rf_calibration":
        raise ValueError("source must be a sealed RF-calibration fit")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    _validate_source_provenance(source)
    unit = source["unit"]
    if unit["size"] != 1 or unit["unit_id"] not in ("DS10-S01", "DS11-S02"):
        raise ValueError("RF calibration polish v1 is restricted to the two frozen pilots")
    output = ROOT / "runs" / run_id / unit["unit_id"]
    output.mkdir(parents=True, exist_ok=False)
    bundle = load_module(
        "rf_calibration_polish_bundle", ROOT.parent / "2026_10_02_localization_benchmark/bundle.py"
    )
    data = bundle.Data(ROOT / "scans" / unit["session_ids"][0])
    started = time.monotonic()
    fitted = fit_rf_calibration_polish(data, source, bank_budget_s=bank_budget_s)
    receipt = {
        "schema": "multiscan-rf-calibration-polish-fit/v1",
        "stage": "rf_calibration_polish",
        "unit": unit,
        "dataset": source["dataset"],
        "run_id": run_id,
        "source_fit": str(source_path),
        "source_fit_sha256": digest(source_path),
        "selection_sha256": source["selection_sha256"],
        "inputs": source["inputs"],
        "source_hashes": {
            path.name: digest(path)
            for path in sorted(ROOT.glob("*.py"))
            if not path.name.startswith("test_")
        },
        "configuration": {
            "bank_budget_s": float(bank_budget_s),
            "sigma_hz": 200.0,
            "coefficient_prior_sigma_hz_ghz": COEFFICIENT_PRIOR_SIGMA_HZ_GHZ,
            "coefficient_bound_hz_ghz": COEFFICIENT_BOUND_HZ_GHZ,
            "extra_dof": 2,
            "optimizer": "joint-l-bfgs-b",
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
                "projected_gradient_inf_norm": trial["projected_gradient_inf_norm"],
                "coefficients_hz_ghz": trial["coefficients_hz_ghz"],
                "reference_error_km": float(np.linalg.norm(estimated - expected)),
            }
        )
    evaluation = {
        "schema": "multiscan-rf-calibration-polish-evaluation/v1",
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
    parser.add_argument("--bank-budget-s", type=float, default=30.0)
    args = parser.parse_args()
    receipt, evaluation = run_case(args.source_fit, args.run_id, args.bank_budget_s)
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
