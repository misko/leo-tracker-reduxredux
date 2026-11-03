"""Joint finite-set localization with receiver-specific RF-slope corrections."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-tau-profile-v1"
RUN_ID = "finite-set-rf-fit-v1"
SOURCE_SCHEMA = "finite-set-tau-profile/v1"
SCHEMA = "finite-set-rf-fit/v1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
DIAGNOSTIC = ROOT / "finite-set-rf-score-all32-v1.json"
RF_PRIOR_SIGMA_HZ_GHZ = 250.0
RF_BOUND_HZ_GHZ = 1000.0
SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
SLOPE_BOUND_HZ_S = 50.0
STATIONARITY_THRESHOLD = 1e-4
NEW_NUMERICAL_DEPENDENCIES = (
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
    "rough_smoke.py",
    "alias_family_joint.py",
)


def receiver_rf_design(data):
    """Return midpoint-centered receiver RF columns in GHz."""

    receiver = np.asarray(data.receiver, dtype=int)
    rf = np.asarray(data.rf, dtype=float)
    group = np.asarray(data.group)
    if receiver.ndim != 1 or rf.shape != receiver.shape or group.shape != receiver.shape:
        raise ValueError("receiver, RF, and group vectors must align")
    if len(receiver) == 0 or np.any(~np.isfinite(rf)):
        raise ValueError("RF observations must be nonempty and finite")
    if np.any((receiver < 0) | (receiver > 1)):
        raise ValueError("receiver values must be zero or one")
    for value in np.unique(group):
        rows = group == value
        if len(np.unique(receiver[rows])) != 1 or len(np.unique(rf[rows])) != 1:
            raise ValueError("each finite-set group must have one receiver and RF")
    centers = np.empty(2)
    spans = []
    design = np.zeros((len(receiver), 2))
    for index in (0, 1):
        rows = receiver == index
        if not np.any(rows):
            raise ValueError(f"RX{index} has no RF observations")
        minimum = float(np.min(rf[rows]))
        maximum = float(np.max(rf[rows]))
        centers[index] = 0.5 * (minimum + maximum)
        design[rows, index] = (rf[rows] - centers[index]) / 1e9
        spans.append(
            {
                "receiver": index,
                "minimum_rf_hz": minimum,
                "maximum_rf_hz": maximum,
                "center_rf_hz": float(centers[index]),
                "span_ghz": (maximum - minimum) / 1e9,
            }
        )
    return design, centers, spans


def optimization_specification(candidate_count, satellites):
    """Return active ordering, scales, and scaled L-BFGS-B bounds."""

    satellites = np.asarray(satellites, dtype=int)
    if (
        satellites.ndim != 1
        or len(satellites) == 0
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
        or len(np.unique(satellites)) != len(satellites)
    ):
        raise ValueError("satellite bank must contain unique valid candidate indices")
    active = np.r_[np.arange(6), 6 + satellites]
    physical_scales = np.r_[20.0, 20.0, 1000.0, 10.0, 1000.0, 10.0, np.ones(len(satellites))]
    scales = np.r_[physical_scales, np.full(2, RF_PRIOR_SIGMA_HZ_GHZ)]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
    ]
    bounds.extend([(-TAU_BOUND_S, TAU_BOUND_S)] * len(satellites))
    scaled_rf_bound = RF_BOUND_HZ_GHZ / RF_PRIOR_SIGMA_HZ_GHZ
    bounds.extend([(-scaled_rf_bound, scaled_rf_bound)] * 2)
    return active, scales, bounds


def projected_gradient(vector, gradient, bounds):
    vector = np.asarray(vector, dtype=float)
    result = np.asarray(gradient, dtype=float).copy()
    if vector.shape != result.shape or len(bounds) != len(vector):
        raise ValueError("projected-gradient inputs do not align")
    for index, (lower, upper) in enumerate(bounds):
        if lower is not None and vector[index] <= lower + 1e-12 and result[index] > 0:
            result[index] = 0.0
        if upper is not None and vector[index] >= upper - 1e-12 and result[index] < 0:
            result[index] = 0.0
    return result


def evaluate_joint_objective(
    vector,
    *,
    data,
    source_parameters,
    satellites,
    likelihood,
    plan,
    design,
    active,
    scales,
):
    """Evaluate the scaled joint objective and exact analytic gradient."""

    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(scales, dtype=float)
    if vector.shape != scales.shape or np.any(~np.isfinite(vector)):
        raise ValueError("joint optimization vector is invalid")
    source_parameters = np.asarray(source_parameters, dtype=float)
    parameters = source_parameters.copy()
    physical_count = len(active)
    parameters[active] = vector[:physical_count] * scales[:physical_count]
    coefficients = vector[physical_count:] * scales[physical_count:]
    predicted, visible, jacobian = plan.predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = np.asarray(predicted, dtype=float).reshape(shape)
    visible = np.asarray(visible, dtype=bool).reshape(shape)
    corrected = predicted + (np.asarray(design) @ coefficients)[:, None]
    result = likelihood.evaluate(
        corrected,
        visible,
        sigma_hz=SIGMA_HZ,
        satellite_weights=np.ones(len(satellites)),
        background_mass=0.2,
        return_gradient=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    if prediction_gradient.shape != shape or np.any(~np.isfinite(prediction_gradient)):
        raise FloatingPointError("finite-set prediction gradient is invalid")
    physical_gradient = -np.asarray(
        jacobian.transpose_multiply(prediction_gradient.ravel()), dtype=float
    )
    if physical_gradient.shape != parameters.shape:
        raise ValueError("prediction Jacobian returned the wrong parameter gradient shape")
    tau_indices = 6 + np.asarray(satellites, dtype=int)
    tau = parameters[tau_indices]
    physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    row_gradient = np.sum(prediction_gradient, axis=1)
    coefficient_gradient = -(np.asarray(design).T @ row_gradient)
    coefficient_gradient += coefficients / RF_PRIOR_SIGMA_HZ_GHZ**2
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    coefficient_prior = 0.5 * float(
        np.sum((coefficients / RF_PRIOR_SIGMA_HZ_GHZ) ** 2)
    )
    objective = float(-result["total_log_likelihood"] + tau_prior + coefficient_prior)
    gradient = np.r_[
        physical_gradient[active] * scales[:physical_count],
        coefficient_gradient * scales[physical_count:],
    ]
    if not np.isfinite(objective) or np.any(~np.isfinite(gradient)):
        raise FloatingPointError("joint RF objective or gradient is non-finite")
    diagnostics = dict(result)
    diagnostics.pop("prediction_gradient", None)
    return {
        "objective": objective,
        "gradient": gradient,
        "parameters": parameters,
        "coefficients_hz_ghz": coefficients,
        "tau_prior": tau_prior,
        "coefficient_prior": coefficient_prior,
        "likelihood": diagnostics,
    }


def model_penalties(group_count, satellite_count):
    if group_count <= 1 or satellite_count <= 0:
        raise ValueError("penalty counts must be positive, with at least two groups")
    source = 0.5 * satellite_count * np.log(group_count)
    rf = 0.5 * 2 * np.log(group_count)
    return {
        "source_entry_penalty": float(source),
        "rf_extra_parameter_count": 2,
        "rf_dof_penalty": float(rf),
        "total_entry_penalty": float(source + rf),
    }


def fit_rf_trial(
    data,
    source_trial,
    full_bank_count,
    likelihood,
    design,
    *,
    budget_s=20.0,
    plan_factory=SharedPredictionPlan,
    minimize_fn=None,
):
    """Jointly optimize one frozen bank while preserving its zero-RF incumbent."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    parameters = np.asarray(source_trial["parameters"], dtype=float)
    if parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(parameters)):
        raise ValueError("source parameters do not match the candidate pool")
    if full_bank_count < len(satellites):
        raise ValueError("full bank cannot be smaller than the fitted bank")
    active, scales, bounds = optimization_specification(len(data.numbers), satellites)
    vector = np.r_[parameters[active], np.zeros(2)] / scales
    plan = plan_factory(data, satellites)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(candidate, *, check_time=True):
        nonlocal evaluations, best
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("joint RF-fit budget exhausted")
        evaluations += 1
        state = evaluate_joint_objective(
            candidate,
            data=data,
            source_parameters=parameters,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
            design=design,
            active=active,
            scales=scales,
        )
        if best is None or state["objective"] < best[0]:
            best = (state["objective"], np.asarray(candidate, dtype=float).copy())
        return state

    initial = evaluate(vector, check_time=False)
    if not np.isclose(initial["objective"], source_trial["objective"], rtol=0, atol=1e-6):
        raise ValueError("zero-RF state does not reproduce sealed source objective")
    optimizer_success = False
    optimizer_status = None
    optimizer_message = ""
    iterations = None
    terminal_vector = None
    timed_out = False
    if minimize_fn is None:
        from scipy.optimize import minimize as minimize_fn
    try:
        fitted = minimize_fn(
            lambda candidate: (
                lambda state: (state["objective"], state["gradient"])
            )(evaluate(candidate)),
            vector,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 1000, "maxfun": 2000, "ftol": 1e-12, "gtol": 1e-7},
        )
        optimizer_success = bool(fitted.success)
        optimizer_status = int(fitted.status)
        optimizer_message = str(fitted.message)
        iterations = int(fitted.nit)
        terminal_vector = np.asarray(fitted.x, dtype=float)
    except TimeoutError as error:
        timed_out = True
        optimizer_message = str(error)
    final_vector = best[1]
    final = evaluate(final_vector, check_time=False)
    projected = projected_gradient(final_vector, final["gradient"], bounds)
    projected_norm = float(np.max(np.abs(projected)))
    best_is_terminal = bool(
        terminal_vector is not None
        and np.allclose(final_vector, terminal_vector, rtol=0, atol=1e-12)
    )
    stationary = projected_norm <= STATIONARITY_THRESHOLD
    success = bool(stationary and best_is_terminal and optimizer_success)
    if success:
        reason = "joint_projected_gradient"
    elif timed_out:
        reason = "budget_exhausted"
    elif not best_is_terminal:
        reason = "retained_best_not_optimizer_terminal"
    elif optimizer_success and not stationary:
        reason = "solver_success_without_projected_stationarity"
    else:
        reason = "joint_stationarity_unresolved"
    groups = len(final["likelihood"]["group_values"])
    penalties = model_penalties(groups, len(satellites))
    if not np.isclose(
        source_trial["entry_penalty"], penalties["source_entry_penalty"], rtol=0, atol=1e-9
    ):
        raise ValueError("source entry penalty differs from the frozen bank penalty")
    likelihood_result = final["likelihood"]
    return {
        "parameters": final["parameters"],
        "coefficients_hz_ghz": final["coefficients_hz_ghz"],
        "coefficients_ppm": final["coefficients_hz_ghz"] * 0.001,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "success": success,
        "status": "converged" if success else "nonconverged",
        "convergence_reason": reason,
        "optimizer_success": optimizer_success,
        "optimizer_status": optimizer_status,
        "optimizer_message": optimizer_message,
        "best_is_optimizer_terminal": best_is_terminal,
        "objective": final["objective"],
        "initial_objective": initial["objective"],
        "source_objective": float(source_trial["objective"]),
        "objective_improvement": float(initial["objective"] - final["objective"]),
        "selection_score": float(final["objective"] + penalties["total_entry_penalty"]),
        **penalties,
        "tau_prior": final["tau_prior"],
        "coefficient_prior": final["coefficient_prior"],
        "total_log_likelihood": float(likelihood_result["total_log_likelihood"]),
        "satellite_support": likelihood_result["satellite_support"],
        "null_support": float(likelihood_result["null_support"]),
        "groups": groups,
        "full_bank_count": int(full_bank_count),
        "per_satellite_detection_probability": float(0.8 / full_bank_count),
        "projected_gradient_inf_norm": projected_norm,
        "stationarity_threshold": STATIONARITY_THRESHOLD,
        "scaled_step_inf_norm": float(np.max(np.abs(final_vector - vector))),
        "evaluations": evaluations,
        "iterations": iterations,
        "elapsed_s": time.monotonic() - started,
        "best_finite_preserved": True,
        "source_incumbent_retained_under_expanded_objective": True,
        "gradient_method": "Analytic finite-set likelihood, orbit VJP, and receiver RF design",
    }


def fit_rf_branches(data, source_fit, *, budget_s_per_bank=20.0, minimize_fn=None):
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    if len(full_bank) == 0 or len(np.unique(full_bank)) != len(full_bank):
        raise ValueError("source full bank must be nonempty and unique")
    design, centers, spans = receiver_rf_design(data)
    trials = []
    for source_trial in source_fit["trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        likelihood = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
        trials.append(
            fit_rf_trial(
                data,
                source_trial,
                len(full_bank),
                likelihood,
                design,
                budget_s=budget_s_per_bank,
                minimize_fn=minimize_fn,
            )
        )
    selection = select_trials(trials)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "selection": selection,
        "rf_centers_hz": centers,
        "rf_spans": spans,
        "rf_formula": "c_rx * (rf_hz - midpoint_rx_hz) / 1e9",
        "coefficient_prior_sigma_hz_ghz": RF_PRIOR_SIGMA_HZ_GHZ,
        "coefficient_bound_hz_ghz": RF_BOUND_HZ_GHZ,
        "coefficient_count": 2,
        "sigma_hz": SIGMA_HZ,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "source_bank_order_preserved": True,
        "scope": (
            "Joint finite-set localization and two receiver RF slopes from each sealed timing-"
            "profile bank. Candidate banks, alias families, probabilities, clutter rate, sigma, "
            "tau prior, and physical bounds stay frozen. The RF prior is a predeclared heuristic, "
            "not calibrated from these fits. No reference coordinates enter fitting or selection."
        ),
    }


def validate_source_record(source, unit_id):
    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("run_id") != SOURCE_RUN
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("dataset") != unit_id[:4]
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be the sealed truth-free timing-profile pilot")
    fit = source.get("fit", {})
    trials = fit.get("trials")
    full_bank = fit.get("full_bank")
    if not isinstance(trials, list) or len(trials) != 5 or not isinstance(full_bank, list):
        raise ValueError("source must contain the frozen five-bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in trials]
    if any(not bank for bank in banks) or len(set(banks)) != 5 or tuple(full_bank) not in banks:
        raise ValueError("source bank ladder is incomplete or duplicated")
    if any(trial.get("success") is not True for trial in trials):
        raise ValueError("every source timing-profile bank must be converged")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source lacks numerical and input hashes")
    return source


def expected_loader_hashes(source):
    unit = source["unit"]
    hashes = source["source_hashes"]
    exports = ROOT / "runs" / "alias-family-cohort-v1"
    expected = [ROOT / "selection.json", exports / "manifest.json"]
    export_root = exports.resolve()
    for session in unit["session_ids"]:
        receipts = [
            Path(path)
            for path in hashes
            if Path(path).parent == export_root and session in Path(path).name
        ]
        if len(receipts) != 1:
            raise ValueError(f"source must bind one alias-family receipt for {session}")
        expected.extend(
            [
                receipts[0],
                ROOT / "scans" / session / "bundle.json",
                ROOT / "scans" / session / "bundle.npz",
            ]
        )
    result = {}
    for path in expected:
        key = str(path.resolve())
        if key not in hashes:
            raise ValueError(f"source does not bind loader input {key}")
        result[key] = hashes[key]
    return result


def validate_diagnostic(diagnostic, diagnostic_path, source, source_path, unit_id):
    truth_free_fields = ("reference_accessed", "evaluation_artifact_accessed", "fit_performed")
    if (
        diagnostic.get("schema") != "finite-set-rf-zero-score/v1"
        or diagnostic.get("sealed") is not True
        or diagnostic.get("failed_unit_count") != 0
        or any(diagnostic.get("provenance", {}).get(field) is not False
               for field in truth_free_fields)
    ):
        raise ValueError("RF diagnostic is not the sealed all-unit score receipt")
    configuration = diagnostic.get("configuration", {})
    if (
        configuration.get("sigma_hz") != SIGMA_HZ
        or configuration.get("coefficient_prior_sigma_hz_per_ghz")
        != RF_PRIOR_SIGMA_HZ_GHZ
        or configuration.get("rf_center_policy")
        != "midpoint of observed RF span independently per receiver/unit"
    ):
        raise ValueError("RF diagnostic configuration differs from this prototype")
    matches = [row for row in diagnostic.get("units", []) if row.get("unit_id") == unit_id]
    if len(matches) != 1 or matches[0].get("status") != "complete":
        raise ValueError("RF diagnostic does not contain one complete unit row")
    row = matches[0]
    if any(row.get("provenance", {}).get(field) is not False for field in truth_free_fields):
        raise ValueError("RF diagnostic unit is not truth-free")
    if (
        row.get("profile_fit_sha256") != digest(source_path)
        or row.get("profile_source_fit_sha256") != source.get("source_fit_sha256")
        or row.get("sealed_profile_source_hashes") != source.get("source_hashes")
        or row.get("input_sha256_pre") != row.get("input_sha256_post")
        or not row.get("source_sha256_pre")
        or row.get("source_sha256_pre") != row.get("source_sha256_post")
    ):
        raise ValueError("RF diagnostic does not bind the sealed source and inputs")
    return {
        "path": str(Path(diagnostic_path).resolve()),
        "sha256": digest(diagnostic_path),
        "unit_row": row,
    }


def validate_geometry_binding(source, data):
    grouped_path = (
        ROOT
        / "runs"
        / "finite-set-grouped-cohort-v1"
        / source["unit"]["unit_id"]
        / "fit.json"
    )
    key = str(grouped_path.resolve())
    if source["source_hashes"].get(key) != source.get("source_fit_sha256"):
        raise ValueError("source does not inherit its grouped-cohort fit exactly")
    grouped = json.loads(grouped_path.read_text())
    actual = serializable(data.geometry_receipt)
    if actual != grouped.get("fit", {}).get("grouped_geometry"):
        raise ValueError("reconstructed geometry differs from sealed grouped source")
    return actual, grouped_path


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    source_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
    started = time.monotonic()
    snapshot = None
    try:
        source = validate_source_record(json.loads(source_path.read_text()), unit_id)
        assert_snapshot_unchanged(source["source_hashes"])
        diagnostic_binding = validate_diagnostic(
            json.loads(DIAGNOSTIC.read_text()), DIAGNOSTIC, source, source_path, unit_id
        )
        expected_inputs = expected_loader_hashes(source)
        manifest_path = ROOT / "runs" / "alias-family-cohort-v1" / "manifest.json"
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            manifest_path.parent,
            expected_manifest_sha256=expected_inputs[str(manifest_path.resolve())],
        )
        bound_inputs = snapshot_files(input_paths)
        if bound_inputs != expected_inputs:
            raise ValueError("reconstructed loader inputs differ from sealed source")
        geometry, grouped_path = validate_geometry_binding(source, data)
        paths = [*source["source_hashes"], source_path, grouped_path, DIAGNOSTIC, Path(__file__)]
        paths.extend(ROOT / name for name in NEW_NUMERICAL_DEPENDENCIES)
        paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_rf_branches(data, source["fit"], budget_s_per_bank=20.0)
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        output.mkdir(parents=True, exist_ok=False)
        failure = {
            "schema": SCHEMA,
            "run_id": RUN_ID,
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "source_hashes": snapshot,
            "reference_read_before_seal": False,
            "evaluation_written": False,
            "sealed": True,
            "sealed_utc": datetime.now(UTC).isoformat(),
        }
        with (output / "failure.json").open("x") as stream:
            json.dump(failure, stream, indent=2, allow_nan=False)
        raise
    result = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "unit": source["unit"],
        "dataset": source["dataset"],
        "source_run_id": SOURCE_RUN,
        "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot,
        "inherited_source_hashes": source["source_hashes"],
        "bound_input_hashes": bound_inputs,
        "geometry_receipt": geometry,
        "rf_diagnostic_binding": diagnostic_binding,
        "limits": {"budget_s_per_bank": 20.0, "numerical_threads": 1},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "fit": fitted,
        "elapsed_s": time.monotonic() - started,
        "sealed": True,
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    with fit_path.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(fit_path), "sha256": digest(fit_path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=SUPPORTED_UNITS)
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id)))
