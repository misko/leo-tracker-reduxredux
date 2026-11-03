"""Complete-data/Fisher Gauss-Newton continuation for sealed RF fits."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_rf_fit import (
    RF_BOUND_HZ_GHZ,
    RF_PRIOR_SIGMA_HZ_GHZ,
    SIGMA_HZ,
    SLOPE_BOUND_HZ_S,
    TAU_BOUND_S,
    TAU_SIGMA_S,
    evaluate_joint_objective,
    model_penalties,
    optimization_specification,
    receiver_rf_design,
)
from gauss_newton import (
    _free_variables,
    _newton_stationarity,
    _project,
    _projected_gradient,
)
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-rf-fit-v1"
RUN_ID = "finite-set-rf-gn-v1"
SOURCE_SCHEMA = "finite-set-rf-fit/v1"
SCHEMA = "finite-set-rf-gn/v1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
NUMERICAL_DEPENDENCIES = (
    "finite_set_rf_fit.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
    "rough_smoke.py",
    "alias_family_joint.py",
)


@dataclass(frozen=True)
class RFFisherState:
    vector: np.ndarray
    parameters: np.ndarray
    coefficients_hz_ghz: np.ndarray
    objective: float
    gradient: np.ndarray
    hessian: np.ndarray
    likelihood: dict
    tau_prior: float
    coefficient_prior: float


def rf_trial_specification(data, source_trial):
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    parameters = np.asarray(source_trial["parameters"], dtype=float)
    coefficients = np.asarray(source_trial["coefficients_hz_ghz"], dtype=float)
    if parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(parameters)):
        raise ValueError("source parameters do not match the candidate pool")
    if coefficients.shape != (2,) or np.any(~np.isfinite(coefficients)):
        raise ValueError("source RF coefficients must contain two finite values")
    active, scales, bounds = optimization_specification(len(data.numbers), satellites)
    vector = np.r_[parameters[active], coefficients] / scales
    projected = _project(vector, bounds)
    if not np.array_equal(projected, vector):
        raise ValueError("source RF state lies outside the frozen bounds")
    return {
        "satellites": satellites,
        "initial_parameters": parameters.copy(),
        "initial_coefficients_hz_ghz": coefficients.copy(),
        "active": active,
        "scales": scales,
        "bounds": bounds,
        "vector": vector,
    }


def _physical_parameters(vector, specification):
    physical_count = len(specification["active"])
    parameters = specification["initial_parameters"].copy()
    parameters[specification["active"]] = (
        np.asarray(vector[:physical_count]) * specification["scales"][:physical_count]
    )
    return parameters


def _rf_cross_block(jacobian, precision, design):
    precision = np.asarray(precision, dtype=float)
    design = np.asarray(design, dtype=float)
    if precision.ndim != 2 or design.shape != (precision.shape[0], 2):
        raise ValueError("prediction precision and RF design do not align")
    columns = []
    for column in range(2):
        weights = precision * design[:, column, None]
        columns.append(jacobian.transpose_multiply(weights.ravel()))
    return np.column_stack(columns)


def evaluate_rf_fisher_state(
    vector,
    *,
    data,
    specification,
    likelihood,
    plan,
    design,
):
    """Evaluate the RF objective, analytic gradient, and complete-data Fisher matrix."""

    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(specification["scales"], dtype=float)
    if vector.shape != scales.shape or np.any(~np.isfinite(vector)):
        raise ValueError("RF continuation vector has the wrong shape or non-finite values")
    active = specification["active"]
    satellites = specification["satellites"]
    physical_count = len(active)
    parameters = _physical_parameters(vector, specification)
    coefficients = vector[physical_count:] * scales[physical_count:]
    predicted, visible, jacobian = plan.predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = np.asarray(predicted, dtype=float).reshape(shape)
    visible = np.asarray(visible, dtype=bool).reshape(shape)
    predicted = predicted + (np.asarray(design, dtype=float) @ coefficients)[:, None]
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=SIGMA_HZ,
        satellite_weights=np.ones(len(satellites)),
        background_mass=0.2,
        return_gradient=True,
        return_precision=True,
    )
    prediction_gradient = np.asarray(result["prediction_gradient"], dtype=float)
    prediction_precision = np.asarray(result["prediction_precision"], dtype=float)
    if prediction_gradient.shape != shape or prediction_precision.shape != shape:
        raise ValueError("finite-set derivatives must match the prediction matrix")
    if np.any(~np.isfinite(prediction_gradient)) or np.any(~np.isfinite(prediction_precision)):
        raise FloatingPointError("finite-set derivatives must be finite")
    if np.any(prediction_precision < 0):
        raise ValueError("prediction precision must be nonnegative")

    full_size = 6 + len(data.numbers)
    physical_gradient = -np.asarray(
        jacobian.transpose_multiply(prediction_gradient.ravel()), dtype=float
    )
    physical_hessian = np.asarray(
        jacobian.normal_matrix(prediction_precision.ravel()), dtype=float
    )
    if physical_gradient.shape != (full_size,):
        raise ValueError("prediction Jacobian gradient has the wrong shape")
    if physical_hessian.shape != (full_size, full_size):
        raise ValueError("prediction Jacobian normal matrix has the wrong shape")

    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    physical_hessian[tau_indices, tau_indices] += 1.0 / TAU_SIGMA_S**2
    row_gradient = np.sum(prediction_gradient, axis=1)
    coefficient_gradient = -(np.asarray(design).T @ row_gradient)
    coefficient_gradient += coefficients / RF_PRIOR_SIGMA_HZ_GHZ**2
    coefficient_prior = 0.5 * float(
        np.sum((coefficients / RF_PRIOR_SIGMA_HZ_GHZ) ** 2)
    )

    cross = _rf_cross_block(jacobian, prediction_precision, design)
    row_precision = np.sum(prediction_precision, axis=1)
    coefficient_hessian = np.asarray(design).T @ (
        row_precision[:, None] * np.asarray(design)
    )
    coefficient_hessian += np.eye(2) / RF_PRIOR_SIGMA_HZ_GHZ**2
    unscaled_hessian = np.block(
        [
            [physical_hessian[np.ix_(active, active)], cross[active]],
            [cross[active].T, coefficient_hessian],
        ]
    )
    unscaled_gradient = np.r_[physical_gradient[active], coefficient_gradient]
    gradient = unscaled_gradient * scales
    hessian = unscaled_hessian * scales[:, None] * scales[None, :]
    hessian = 0.5 * (hessian + hessian.T)
    objective = float(-result["total_log_likelihood"] + tau_prior + coefficient_prior)
    if (
        not np.isfinite(objective)
        or np.any(~np.isfinite(gradient))
        or np.any(~np.isfinite(hessian))
    ):
        raise FloatingPointError("RF continuation objective derivatives must be finite")
    diagnostics = dict(result)
    diagnostics.pop("prediction_gradient", None)
    diagnostics.pop("prediction_precision", None)
    return RFFisherState(
        vector=vector.copy(),
        parameters=parameters,
        coefficients_hz_ghz=coefficients,
        objective=objective,
        gradient=gradient,
        hessian=hessian,
        likelihood=diagnostics,
        tau_prior=tau_prior,
        coefficient_prior=coefficient_prior,
    )


def _verify_frozen_source_state(
    state,
    *,
    data,
    specification,
    likelihood,
    plan,
    design,
    source_trial,
):
    frozen = evaluate_joint_objective(
        specification["vector"],
        data=data,
        source_parameters=specification["initial_parameters"],
        satellites=specification["satellites"],
        likelihood=likelihood,
        plan=plan,
        design=design,
        active=specification["active"],
        scales=specification["scales"],
    )
    objective_delta = float(state.objective - frozen["objective"])
    gradient_delta = float(np.max(np.abs(state.gradient - frozen["gradient"])))
    if not np.isclose(state.objective, source_trial["objective"], rtol=0, atol=1e-6):
        raise ValueError("RF GN seed does not reproduce sealed source objective")
    if abs(objective_delta) > 1e-10 or gradient_delta > 1e-10:
        raise ValueError("RF GN seed does not reproduce the frozen RF evaluator")
    return {
        "sealed_source_objective_delta": float(state.objective - source_trial["objective"]),
        "frozen_evaluator_objective_delta": objective_delta,
        "frozen_evaluator_gradient_max_abs_delta": gradient_delta,
    }


def fit_rf_gauss_newton_trial(
    data,
    source_trial,
    likelihood,
    design,
    *,
    budget_s=20.0,
    plan_factory=SharedPredictionPlan,
):
    """Continue one sealed RF bank with bounded Fisher Gauss-Newton."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= 20:
        raise ValueError("budget_s must lie in (0, 20]")
    specification = rf_trial_specification(data, source_trial)
    satellites = specification["satellites"]
    bounds = specification["bounds"]
    plan = plan_factory(data, satellites)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(vector, *, check_time=True):
        nonlocal best, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("finite-set RF GN budget exhausted")
        state = evaluate_rf_fisher_state(
            vector,
            data=data,
            specification=specification,
            likelihood=likelihood,
            plan=plan,
            design=design,
        )
        evaluations += 1
        if best is None or state.objective < best.objective:
            best = state
        return state

    vector = _project(specification["vector"], bounds)
    current = evaluate(vector, check_time=False)
    source_reproduction = _verify_frozen_source_state(
        current,
        data=data,
        specification=specification,
        likelihood=likelihood,
        plan=plan,
        design=design,
        source_trial=source_trial,
    )
    initial_objective = current.objective
    positive_diagonal = np.diag(current.hessian)
    positive_diagonal = positive_diagonal[positive_diagonal > 0]
    damping = max(
        1e-6,
        1e-3 * (float(np.median(positive_diagonal)) if len(positive_diagonal) else 1.0),
    )
    iterations = 0
    accepted_steps = 0
    rejected_steps = 0
    last_accepted_step_inf_norm = None
    last_accepted_loss_decrease = None
    success = False
    reason = "iteration_limit"

    try:
        while iterations < 200:
            if time.monotonic() > deadline:
                raise TimeoutError("finite-set RF GN budget exhausted")
            projected = _projected_gradient(current.vector, current.gradient, bounds)
            if np.max(np.abs(projected)) <= 1e-4:
                success = True
                reason = "projected_gradient"
                break
            free = _free_variables(current.vector, current.gradient, bounds)
            stationarity = _newton_stationarity(
                current.objective,
                current.gradient,
                current.hessian,
                free,
                damping,
            )
            if stationarity["low_damping_positive_newton_converged"]:
                success = True
                reason = "low_damping_positive_newton_decrement"
                break
            iterations += 1
            system = current.hessian[np.ix_(free, free)] + damping * np.eye(np.sum(free))
            try:
                step = np.zeros_like(current.vector)
                step[free] = np.linalg.solve(system, -current.gradient[free])
            except np.linalg.LinAlgError:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "singular_curvature"
                    break
                continue
            if np.any(~np.isfinite(step)):
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "nonfinite_step"
                    break
                continue
            maximum = float(np.max(np.abs(step)))
            if maximum > 1.0:
                step /= maximum

            accepted = None
            accepted_step = None
            for fraction in (1.0, 0.5, 0.25, 0.125):
                candidate_vector = _project(current.vector + fraction * step, bounds)
                actual_step = candidate_vector - current.vector
                if not np.any(actual_step):
                    continue
                candidate = evaluate(candidate_vector)
                if candidate.objective < current.objective:
                    accepted = candidate
                    accepted_step = actual_step
                    break
            if accepted is None:
                damping = min(damping * 10.0, 1e18)
                rejected_steps += 1
                if damping >= 1e18:
                    reason = "no_acceptable_step"
                    break
                continue

            previous_objective = current.objective
            current = accepted
            accepted_steps += 1
            damping = max(damping / 3.0, 1e-12)
            step_norm = float(np.max(np.abs(accepted_step)))
            improvement = previous_objective - current.objective
            last_accepted_step_inf_norm = step_norm
            last_accepted_loss_decrease = float(improvement)
            if step_norm <= 1e-6 and improvement <= 1e-8 * (1.0 + abs(previous_objective)):
                accepted_projected = _projected_gradient(
                    current.vector, current.gradient, bounds
                )
                if np.max(np.abs(accepted_projected)) <= 1e-4:
                    success = True
                    reason = "projected_gradient_after_tiny_step"
                else:
                    accepted_free = _free_variables(
                        current.vector, current.gradient, bounds
                    )
                    accepted_stationarity = _newton_stationarity(
                        current.objective,
                        current.gradient,
                        current.hessian,
                        accepted_free,
                        damping,
                    )
                    if accepted_stationarity["low_damping_positive_newton_converged"]:
                        success = True
                        reason = "low_damping_positive_newton_decrement_after_tiny_step"
                    else:
                        reason = "tiny_accepted_step_without_gradient_convergence"
                break
    except TimeoutError:
        reason = "budget_exhausted"
    except Exception as error:
        reason = f"evaluation_error:{type(error).__name__}:{error}"

    final_evaluation_error = None
    try:
        final = evaluate(best.vector, check_time=False)
    except Exception as error:
        final = best
        success = False
        final_evaluation_error = f"{type(error).__name__}:{error}"
        reason = f"final_evaluation_failed:{final_evaluation_error}"
        if hasattr(likelihood, "last_result"):
            likelihood.last_result = dict(best.likelihood)
    if final is None:
        raise RuntimeError("RF GN produced no finite state")
    retained_matches_current = bool(
        final.vector.shape == current.vector.shape
        and np.allclose(final.vector, current.vector, rtol=0, atol=1e-10)
    )
    if success and not retained_matches_current:
        success = False
        reason = "converged_state_differs_from_retained_incumbent"
    projected = _projected_gradient(final.vector, final.gradient, bounds)
    final_free = _free_variables(final.vector, final.gradient, bounds)
    stationarity = _newton_stationarity(
        final.objective,
        final.gradient,
        final.hessian,
        final_free,
        damping,
    )
    groups = len(final.likelihood["group_values"])
    penalties = model_penalties(groups, len(satellites))
    if not np.isclose(
        source_trial["total_entry_penalty"],
        penalties["total_entry_penalty"],
        rtol=0,
        atol=1e-9,
    ):
        raise ValueError("source RF penalty differs from the frozen model penalty")
    return {
        "model": "finite_set_rf_complete_data_fisher_gn",
        "parameters": final.parameters,
        "coefficients_hz_ghz": final.coefficients_hz_ghz,
        "coefficients_ppm": final.coefficients_hz_ghz * 0.001,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "source_objective": float(source_trial["objective"]),
        "objective_improvement": float(initial_objective - final.objective),
        "selection_score": float(final.objective + penalties["total_entry_penalty"]),
        **penalties,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": reason,
        "convergence_reason": reason,
        "algorithm_version": "finite-set-rf-complete-data-fisher-gn/v1",
        "optimizer_status": None,
        "final_evaluation_error": final_evaluation_error,
        "evaluations": evaluations,
        "iterations": iterations,
        "accepted_steps": accepted_steps,
        "rejected_steps": rejected_steps,
        "elapsed_s": time.monotonic() - started,
        "groups": groups,
        "sigma_hz": SIGMA_HZ,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "rx_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "coefficient_prior_sigma_hz_ghz": RF_PRIOR_SIGMA_HZ_GHZ,
        "coefficient_bound_hz_ghz": RF_BOUND_HZ_GHZ,
        "tau_prior": final.tau_prior,
        "coefficient_prior": final.coefficient_prior,
        "total_log_likelihood": float(final.likelihood["total_log_likelihood"]),
        "satellite_support": final.likelihood["satellite_support"],
        "null_support": float(final.likelihood["null_support"]),
        "gradient_inf_norm": float(np.max(np.abs(final.gradient))),
        "projected_gradient_inf_norm": float(np.max(np.abs(projected))),
        "last_accepted_step_inf_norm": last_accepted_step_inf_norm,
        "last_accepted_loss_decrease": last_accepted_loss_decrease,
        "damping": float(damping),
        "free_parameter_count": int(np.sum(final_free)),
        "zero_width_bound_count": int(
            sum(
                lower is not None and upper is not None and lower == upper
                for lower, upper in bounds
            )
        ),
        "stationarity_thresholds": {
            "projected_gradient_inf_norm": 1e-4,
            "modeled_newton_relative_loss_decrease": 1e-10,
            "undamped_newton_step_inf_norm": 1e-5,
            "damping_to_free_min_eigenvalue": 1e-6,
            "positive_free_curvature_required": True,
        },
        **stationarity,
        "source_reproduction": source_reproduction,
        "gradient_method": "Analytic finite-set prediction gradient plus receiver RF design",
        "curvature_method": (
            "Complete-data/Fisher physical JtWJ, exact physical-RF cross block, RF design "
            "block, and Gaussian tau/RF priors"
        ),
        "optimizer_terminal_matches_retained": retained_matches_current,
        "best_finite_preserved": True,
    }


def fit_rf_gauss_newton_branches(data, source_fit, *, budget_s_per_bank=20.0):
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    if len(full_bank) == 0 or len(np.unique(full_bank)) != len(full_bank):
        raise ValueError("source full bank must be nonempty and unique")
    design, centers, spans = receiver_rf_design(data)
    if not np.array_equal(np.asarray(source_fit["rf_centers_hz"]), centers):
        raise ValueError("reconstructed RF centers differ from sealed RF source")
    trials = []
    for source_trial in source_fit["trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        likelihood = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
        trials.append(
            fit_rf_gauss_newton_trial(
                data,
                source_trial,
                likelihood,
                design,
                budget_s=budget_s_per_bank,
            )
        )
    return {
        "full_bank": full_bank,
        "trials": trials,
        "selection": select_trials(trials),
        "rf_centers_hz": centers,
        "rf_spans": spans,
        "source_bank_order_preserved": True,
        "scope": (
            "One bounded complete-data/Fisher Gauss-Newton continuation from every sealed RF-v1 "
            "bank. The same candidate banks, data, finite-set masses, sigma, priors, bounds, and "
            "two-parameter model penalty are retained. No reference coordinates enter fitting "
            "or model selection."
        ),
    }


def validate_source_binding(source, unit_id, data, input_paths):
    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("run_id") != SOURCE_RUN
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("dataset") != unit_id[:4]
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("sealed") is not True
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free RF-v1 fit")
    fit = source.get("fit", {})
    if (
        fit.get("coefficient_prior_sigma_hz_ghz") != RF_PRIOR_SIGMA_HZ_GHZ
        or fit.get("coefficient_bound_hz_ghz") != RF_BOUND_HZ_GHZ
        or fit.get("sigma_hz") != SIGMA_HZ
        or fit.get("tau_sigma_s") != TAU_SIGMA_S
        or fit.get("tau_bound_s") != TAU_BOUND_S
        or fit.get("slope_bound_hz_s") != SLOPE_BOUND_HZ_S
        or fit.get("coefficient_count") != 2
    ):
        raise ValueError("source RF model configuration differs from the continuation")
    trials = fit.get("trials")
    full_bank = fit.get("full_bank")
    if not isinstance(trials, list) or len(trials) != 5 or not isinstance(full_bank, list):
        raise ValueError("source RF fit must contain the frozen five-bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in trials]
    if any(not bank for bank in banks) or len(set(banks)) != 5 or tuple(full_bank) not in banks:
        raise ValueError("source RF bank ladder is incomplete or duplicated")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source RF fit lacks numerical hashes")
    assert_snapshot_unchanged(source_hashes)
    actual_inputs = snapshot_files(input_paths)
    if actual_inputs != source.get("bound_input_hashes"):
        raise ValueError("reconstructed inputs differ from sealed RF source")
    geometry = serializable(data.geometry_receipt)
    if geometry != source.get("geometry_receipt"):
        raise ValueError("reconstructed geometry differs from sealed RF source")
    return {
        "source_hashes": dict(source_hashes),
        "bound_input_hashes": actual_inputs,
        "geometry_receipt": geometry,
    }


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
        source = json.loads(source_path.read_text())
        manifest_path = ROOT / "runs" / "alias-family-cohort-v1" / "manifest.json"
        expected_manifest = source.get("bound_input_hashes", {}).get(
            str(manifest_path.resolve())
        )
        if expected_manifest is None:
            raise ValueError("source RF fit does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            manifest_path.parent,
            expected_manifest_sha256=expected_manifest,
        )
        binding = validate_source_binding(source, unit_id, data, input_paths)
        paths = [*binding["source_hashes"], source_path, Path(__file__)]
        paths.extend(ROOT / name for name in NUMERICAL_DEPENDENCIES)
        paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_rf_gauss_newton_branches(
            data,
            source["fit"],
            budget_s_per_bank=20.0,
        )
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
        "inherited_source_hashes": binding["source_hashes"],
        "bound_input_hashes": binding["bound_input_hashes"],
        "geometry_receipt": binding["geometry_receipt"],
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


__all__ = [
    "RFFisherState",
    "evaluate_rf_fisher_state",
    "fit_rf_gauss_newton_trial",
    "rf_trial_specification",
]
