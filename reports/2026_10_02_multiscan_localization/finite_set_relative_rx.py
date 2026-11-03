"""Finite-set localization with fixed relative-RX calibration and tied common drift."""

from __future__ import annotations

import argparse
import copy
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    FiniteSetLikelihoodAdapter,
    GroupMedianGeometryData,
    assert_snapshot_unchanged,
    digest,
    frozen_raw_masses,
    snapshot_files,
)
from finite_set_likelihood import prepare_finite_set_likelihood
from finite_set_quadratic import (
    FiniteSetQuadraticLikelihoodAdapter,
    _same_numeric,
    _validate_source,
)
from prediction_plan import SharedPredictionPlan
from quadratic_drift_fit import (
    CURVATURE_BOUND_HZ,
    CURVATURE_PRIOR_SIGMA_HZ,
    SLOPE_BOUND_HZ_S,
    TIME_SCALE_S,
    _evaluate_joint,
    quadratic_time_basis,
)
from relative_rx_fit import (
    CalibratedData,
    _load_differential_case,
    array_digest,
    expand_tied_parameters,
    reduce_tied_parameters,
    select_differential_calibration,
)
from rough_smoke import load_module, serializable
from rx_difference import pair_receiver_groups
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN_ID = "finite-set-raw-control-v2"
DEFAULT_RX_SOURCE = ROOT / "runs" / "rx-difference-cohort-v1"
DEFAULT_RUN_ID = "finite-set-relative-rx-v1"
MODEL_NAMES = ("tied_common_linear", "tied_common_linear_plus_quadratic")
NUMERICAL_DEPENDENCIES = (
    "finite_set_relative_rx.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "finite_set_quadratic.py",
    "quadratic_drift_fit.py",
    "relative_rx_fit.py",
    "rx_difference.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
)


@dataclass(frozen=True)
class _State:
    vector: np.ndarray
    reduced: np.ndarray
    curvature_hz: float
    objective: float
    gradient: np.ndarray
    likelihood: dict
    tau_prior: float
    curvature_prior: float


def calibration_derivative(calibration, times):
    times = np.asarray(times, dtype=float)
    if calibration.model == "line":
        return np.full(times.shape, calibration.parameters[1], dtype=float)
    if calibration.model != "quadratic":
        raise ValueError(f"unsupported differential model {calibration.model!r}")
    span = calibration.end_time_s - calibration.start_time_s
    if not np.isfinite(span) or span <= 0:
        raise ValueError("quadratic differential calibration span must be positive")
    fraction = (times - calibration.start_time_s) / span
    return calibration.parameters[1] + (
        calibration.parameters[2] - calibration.parameters[1]
    ) * fraction


def common_quadratic_basis(data):
    return np.sum(quadratic_time_basis(data), axis=1)


def physical_endpoint_slopes(data, calibration, common_slope_hz_s, curvature_hz=0.0):
    endpoints = np.asarray([np.min(data.times), np.max(data.times)], dtype=float)
    basis_derivative = 2.0 * (endpoints - TIME_SCALE_S) / TIME_SCALE_S**2
    common = float(common_slope_hz_s) + float(curvature_hz) * basis_derivative
    differential = calibration_derivative(calibration, endpoints)
    return common[:, None] + differential[:, None] * np.asarray([-0.5, 0.5])


def slope_constraint(data, calibration, include_quadratic, vector_size):
    endpoints = np.asarray([np.min(data.times), np.max(data.times)], dtype=float)
    differential = calibration_derivative(calibration, endpoints)
    matrix = np.zeros((4, vector_size))
    lower = np.empty(4)
    upper = np.empty(4)
    row = 0
    for endpoint_index, endpoint in enumerate(endpoints):
        curvature_derivative = 2.0 * (endpoint - TIME_SCALE_S) / TIME_SCALE_S**2
        for differential_sign in (-0.5, 0.5):
            matrix[row, 3] = 10.0
            if include_quadratic:
                matrix[row, -1] = CURVATURE_PRIOR_SIGMA_HZ * curvature_derivative
            offset = differential_sign * differential[endpoint_index]
            lower[row] = -SLOPE_BOUND_HZ_S - offset
            upper[row] = SLOPE_BOUND_HZ_S - offset
            row += 1
    return matrix, lower, upper


def _constraint_violation(vector, bounds, matrix, lower, upper):
    vector = np.asarray(vector, dtype=float)
    values = matrix @ vector
    violation = max(
        0.0,
        float(np.max(lower - values)),
        float(np.max(values - upper)),
    )
    for index, (minimum, maximum) in enumerate(bounds):
        if minimum is not None:
            violation = max(violation, minimum - vector[index])
        if maximum is not None:
            violation = max(violation, vector[index] - maximum)
    return float(max(0.0, violation))


def _trial_specification(data, source_parameters, satellites, calibration, include_quadratic):
    candidate_count = len(data.numbers)
    source_parameters = np.asarray(source_parameters, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    if source_parameters.shape != (6 + candidate_count,) or np.any(
        ~np.isfinite(source_parameters)
    ):
        raise ValueError("sealed source parameters do not match the candidate pool")
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if len(np.unique(satellites)) != len(satellites) or np.any(satellites < 0) or np.any(
        satellites >= candidate_count
    ):
        raise ValueError("satellites must be unique valid candidate indices")
    reduced_initial = reduce_tied_parameters(source_parameters)
    active = np.r_[np.arange(4), 4 + satellites]
    scales = np.r_[
        20.0,
        20.0,
        1000.0,
        10.0,
        np.ones(len(satellites)),
        CURVATURE_PRIOR_SIGMA_HZ,
    ]
    bounds = [(-10.0, 10.0), (-10.0, 10.0), (None, None), (None, None)]
    bounds += [(-3.0, 3.0)] * len(satellites)
    vector = np.r_[reduced_initial[active] / scales[:-1], 0.0]
    if include_quadratic:
        bounds.append(
            (
                -CURVATURE_BOUND_HZ / CURVATURE_PRIOR_SIGMA_HZ,
                CURVATURE_BOUND_HZ / CURVATURE_PRIOR_SIGMA_HZ,
            )
        )
    else:
        bounds.append((0.0, 0.0))
    matrix, lower, upper = slope_constraint(
        data, calibration, include_quadratic, len(vector)
    )
    if _constraint_violation(vector, bounds, matrix, lower, upper) > 1e-9:
        raise ValueError("projected sealed source violates physical RX endpoint slope bounds")
    expanded_active = np.r_[np.arange(6), 6 + satellites]
    expanded_scales = np.r_[
        20.0,
        20.0,
        1000.0,
        10.0,
        1000.0,
        10.0,
        np.ones(len(satellites)),
        CURVATURE_PRIOR_SIGMA_HZ,
        CURVATURE_PRIOR_SIGMA_HZ,
    ]
    transform = np.zeros((len(expanded_scales), len(scales)))
    transform[0, 0] = 1.0
    transform[1, 1] = 1.0
    transform[2, 2] = 1.0
    transform[3, 3] = 1.0
    transform[4, 2] = 1.0
    transform[5, 3] = 1.0
    transform[6 : 6 + len(satellites), 4 : 4 + len(satellites)] = np.eye(
        len(satellites)
    )
    transform[-2:, -1] = 1.0
    return {
        "initial_parameters": expand_tied_parameters(reduced_initial),
        "reduced_initial": reduced_initial,
        "active": active,
        "scales": scales,
        "bounds": bounds,
        "vector": vector,
        "constraint_matrix": matrix,
        "constraint_lower": lower,
        "constraint_upper": upper,
        "expanded_active": expanded_active,
        "expanded_scales": expanded_scales,
        "expanded_from_reduced": transform,
    }


def _evaluate_trial_state(
    vector,
    *,
    data,
    specification,
    satellites,
    likelihood,
    plan,
    design,
):
    vector = np.asarray(vector, dtype=float)
    transform = specification["expanded_from_reduced"]
    expanded_vector = transform @ vector
    state = _evaluate_joint(
        expanded_vector,
        data=data,
        initial_parameters=specification["initial_parameters"],
        satellites=satellites,
        prepared=likelihood,
        masses=likelihood.frozen_masses,
        design=design,
        plan=plan,
        active=specification["expanded_active"],
        scales=specification["expanded_scales"],
    )
    objective, expanded_gradient, parameters, coefficients = state[:4]
    diagnostics, tau_prior, doubled_curvature_prior = state[4:]
    if not np.isclose(coefficients[0], coefficients[1], rtol=0, atol=1e-12):
        raise RuntimeError("expanded common curvature coefficients are not tied")
    curvature_hz = float(coefficients[0])
    duplicated_prior = 0.5 * vector[-1] ** 2
    objective -= duplicated_prior
    gradient = transform.T @ expanded_gradient
    gradient[-1] -= vector[-1]
    curvature_prior = doubled_curvature_prior - duplicated_prior
    if not np.isfinite(objective) or np.any(~np.isfinite(gradient)):
        raise FloatingPointError("finite-set tied objective or gradient is non-finite")
    return _State(
        vector=vector.copy(),
        reduced=reduce_tied_parameters(parameters),
        curvature_hz=curvature_hz,
        objective=float(objective),
        gradient=gradient,
        likelihood=diagnostics,
        tau_prior=float(tau_prior),
        curvature_prior=float(curvature_prior),
    )


def fit_tied_finite_set_trial(
    data,
    source_trial,
    likelihood,
    calibration,
    *,
    include_quadratic,
    budget_s=15.0,
    minimizer=None,
    plan_factory=SharedPredictionPlan,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("budget_s must lie in (0, 15]")
    satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
    specification = _trial_specification(
        data,
        source_trial["parameters"],
        satellites,
        calibration,
        include_quadratic,
    )
    bounds = specification["bounds"]
    vector = specification["vector"]
    matrix = specification["constraint_matrix"]
    lower = specification["constraint_lower"]
    upper = specification["constraint_upper"]
    design = quadratic_time_basis(data)
    plan = plan_factory(data, satellites)
    started = time.monotonic()
    deadline = started + float(budget_s)
    evaluations = 0
    best = None

    def evaluate(candidate, *, check_time=True):
        nonlocal best, evaluations
        if check_time and time.monotonic() > deadline:
            raise TimeoutError("finite-set relative-RX fit budget exhausted")
        evaluations += 1
        state = _evaluate_trial_state(
            candidate,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
            design=design,
        )
        if _constraint_violation(candidate, bounds, matrix, lower, upper) <= 1e-7 and (
            best is None or state.objective < best.objective
        ):
            best = state
        return state.objective, state.gradient

    initial_objective, _ = evaluate(vector, check_time=False)
    optimizer = None
    timed_out = False
    try:
        if minimizer is None:
            from scipy.optimize import LinearConstraint, minimize

            constraints = (LinearConstraint(matrix, lower, upper),)
            optimizer = minimize(
                evaluate,
                vector,
                method="SLSQP",
                jac=True,
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 500, "ftol": 1e-10},
            )
        else:
            optimizer = minimizer(evaluate, vector, bounds, matrix, lower, upper)
    except TimeoutError:
        timed_out = True
    if best is None:
        raise RuntimeError("finite-set relative-RX fit produced no feasible finite state")
    final = _evaluate_trial_state(
        best.vector,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
        design=design,
    )
    violation = _constraint_violation(best.vector, bounds, matrix, lower, upper)
    success = bool(
        optimizer is not None
        and optimizer.success
        and not timed_out
        and violation <= 1e-7
    )
    full = expand_tied_parameters(final.reduced)
    groups = len(final.likelihood["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(groups)
    model_penalty = 0.5 * int(include_quadratic) * np.log(groups)
    endpoint_slopes = physical_endpoint_slopes(
        data, calibration, final.reduced[3], final.curvature_hz
    )
    return {
        "model": MODEL_NAMES[int(include_quadratic)],
        "parameters": full,
        "reduced_parameters": final.reduced,
        "curvature_hz": final.curvature_hz,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": final.objective,
        "initial_objective": initial_objective,
        "selection_score": float(final.objective + entry_penalty + model_penalty),
        "entry_penalty": float(entry_penalty),
        "common_quadratic_parameter_penalty": float(model_penalty),
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": (
            "budget_exhausted"
            if timed_out
            else str(optimizer.message if optimizer is not None else "optimizer_not_started")
        ),
        "optimizer_status": None
        if optimizer is None or not hasattr(optimizer, "status")
        else int(optimizer.status),
        "evaluations": evaluations,
        "iterations": None
        if optimizer is None or not hasattr(optimizer, "nit")
        else int(optimizer.nit),
        "elapsed_s": time.monotonic() - started,
        "groups": groups,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
        "curvature_bound_hz": CURVATURE_BOUND_HZ,
        "curvature_prior": final.curvature_prior,
        "tau_prior": final.tau_prior,
        "physical_rx_endpoint_slopes_hz_s": endpoint_slopes,
        "physical_rx_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "constraint_violation_hz_s": violation,
        "gradient_inf_norm": float(np.max(np.abs(final.gradient))),
        "rx_tie_exact": bool(full[2] == full[4] and full[3] == full[5]),
        "zero_curvature_initialization": bool(include_quadratic),
        "source_projected_to_tied_common_line": True,
        "best_feasible_finite_preserved": True,
        "satellite_support": final.likelihood["satellite_support"],
        "null_support": final.likelihood["null_support"],
    }


def _likelihood_diagnostics(likelihood):
    result = likelihood.last_result
    return {
        "conditioned_nonempty": bool(result["conditioned_nonempty"]),
        "density_convention": result["density_convention"],
        "group_count": int(len(result["group_values"])),
        "total_satellite_support": float(np.sum(result["satellite_support"])),
        "total_expected_clutter_count": float(np.sum(result["expected_clutter_count"])),
        "total_raw_peak_count": int(np.sum(result["raw_peak_count"])),
        "total_unique_peak_count": int(np.sum(result["unique_peak_count"])),
    }


def fit_relative_rx_models(
    data,
    source,
    differential_case,
    *,
    budget_s_per_model_bank=15.0,
    trial_fitter=fit_tied_finite_set_trial,
    likelihood_preparer=prepare_finite_set_likelihood,
):
    if not np.isfinite(budget_s_per_model_bank) or not 0 < budget_s_per_model_bank <= 15:
        raise ValueError("budget_s_per_model_bank must lie in (0, 15]")
    unit_id = source["unit"]["unit_id"]
    source_fit = _validate_source(source, unit_id)
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    if geometry.geometry_receipt != source_fit["geometry"]:
        raise ValueError("reconstructed group-median geometry differs from sealed finite-set v2")
    paired = pair_receiver_groups(geometry)
    calibration, calibration_selection = select_differential_calibration(
        differential_case, paired.times
    )
    calibrated = CalibratedData(geometry, calibration)
    prepared = likelihood_preparer(calibrated.measured, calibrated.group)
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    trials = {name: [] for name in MODEL_NAMES}
    for source_trial in source_fit["finite_set_trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        expected_masses = frozen_raw_masses(len(satellites), len(full_bank))
        if set(source_trial["raw_masses"]) != set(expected_masses) or any(
            not _same_numeric(source_trial["raw_masses"][key], value)
            for key, value in expected_masses.items()
        ):
            raise ValueError("sealed finite-set v2 masses differ from the frozen full-bank scale")
        expected_probability = 0.8 / len(full_bank)
        if not np.isclose(
            source_trial["per_satellite_probability"], expected_probability, rtol=0, atol=1e-12
        ):
            raise ValueError("sealed detection probability differs from full-bank scale")
        bank_initial_objectives = []
        for include_quadratic, model_name in enumerate(MODEL_NAMES):
            finite_set = FiniteSetLikelihoodAdapter(
                prepared,
                detection_probability=expected_probability,
                clutter_rate=float(source_fit["finite_set_clutter_rate"]),
            )
            likelihood = FiniteSetQuadraticLikelihoodAdapter(
                finite_set, expected_masses
            )
            trial = trial_fitter(
                calibrated,
                source_trial,
                likelihood,
                calibration,
                include_quadratic=bool(include_quadratic),
                budget_s=float(budget_s_per_model_bank),
            )
            trial["model"] = model_name
            trial["source_model"] = "sealed_finite_set_linear_v2"
            trial["source_status"] = source_trial["status"]
            trial["source_success"] = bool(source_trial["success"])
            trial["source_objective"] = float(source_trial["objective"])
            trial["source_parameters_sha256"] = array_digest(source_trial["parameters"])
            trial["full_bank_count"] = len(full_bank)
            trial["per_satellite_probability"] = expected_probability
            trial["raw_masses"] = copy.deepcopy(expected_masses)
            trial["anchors_used"] = 0
            trial["likelihood_diagnostics"] = _likelihood_diagnostics(likelihood)
            trials[model_name].append(trial)
            bank_initial_objectives.append(trial["initial_objective"])
        if not np.isclose(
            bank_initial_objectives[0], bank_initial_objectives[1], rtol=0, atol=1e-7
        ):
            raise ValueError("linear and quadratic models did not receive the same bank seed")
    selections = {name: select_trials(trials[name]) for name in MODEL_NAMES}
    combined_trials = trials[MODEL_NAMES[0]] + trials[MODEL_NAMES[1]]
    return {
        "full_bank": full_bank,
        "fitted_bank_sizes": [
            int(trial["satellite_count"]) for trial in source_fit["finite_set_trials"]
        ],
        "linear_trials": trials[MODEL_NAMES[0]],
        "quadratic_trials": trials[MODEL_NAMES[1]],
        "linear_selection": selections[MODEL_NAMES[0]],
        "quadratic_selection": selections[MODEL_NAMES[1]],
        "combined_selection": select_trials(combined_trials),
        "selection_resolution_policy": (
            "staged_fit.select_trials: resolved only when every fitted bank converges; "
            "score_leader is retained separately"
        ),
        "geometry": copy.deepcopy(geometry.geometry_receipt),
        "anchors_used": 0,
        "same_sealed_v2_bank_seed_for_both_models": True,
        "all_source_ladder_banks_fitted_in_both_models": True,
        "same_budget_per_model_per_bank_s": float(budget_s_per_model_bank),
        "calibration": {
            "model": calibration.model,
            "parameters": calibration.parameters,
            "reference_time_s": calibration.reference_time_s,
            "start_time_s": calibration.start_time_s,
            "end_time_s": calibration.end_time_s,
            "endpoint_slopes_hz_s": calibration.endpoint_slopes_hz_s,
            "measurement_correction": "RX0 += delta(t)/2; RX1 -= delta(t)/2",
        },
        "calibration_selection": calibration_selection,
        "differential_likelihood_added_to_localization_objective": False,
        "plug_in_calibration_uncertainty_propagated": False,
        "same_data_calibration_treated_as_independent_evidence": False,
        "finite_set_clutter_rate": float(source_fit["finite_set_clutter_rate"]),
        "finite_set_clutter_rate_semantics": source_fit[
            "finite_set_clutter_rate_semantics"
        ],
        "scope": (
            "Truth-free normalized finite-set comparison using every sealed finite-set linear-v2 "
            "bank as its sole same-bank start. The fixed same-data RX1-RX0 calibration corrects "
            "measurements but contributes no independent likelihood factor. Both models fit "
            "position, one tied common RX line and the same candidate taus; the quadratic model "
            "adds one zero-initialized common coefficient with the frozen 250 Hz prior and 1000 "
            "Hz bound. Both physical receiver endpoint slopes include the fixed differential "
            "derivative and remain within 50 Hz/s. Calibration uncertainty is not propagated."
        ),
    }


def _load_sources(unit_id, source_run_id, differential_source):
    source_path = ROOT / "runs" / source_run_id / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    _validate_source(source, unit_id)
    differential_case, calibration_source = _load_differential_case(
        unit_id, differential_source
    )
    if calibration_source["kind"] != "cohort_unit_receipt":
        raise ValueError("relative finite-set fit requires the sealed differential cohort")
    session_id = source["unit"]["session_ids"][0]
    if differential_case["session_id"] != session_id:
        raise ValueError("finite-set and differential sources refer to different sessions")
    bundle_directory = ROOT / "scans" / session_id
    if differential_case["source_sha256"] != digest(ROOT / "rx_difference.py"):
        raise ValueError("differential numerical source digest mismatch")
    if differential_case["bundle_manifest_sha256"] != digest(
        bundle_directory / "bundle.json"
    ):
        raise ValueError("differential bundle manifest digest mismatch")
    if differential_case["bundle_npz_sha256"] != digest(bundle_directory / "bundle.npz"):
        raise ValueError("differential bundle payload digest mismatch")
    return {
        "source": source,
        "source_path": source_path,
        "calibration_case": differential_case,
        "calibration_source": calibration_source,
        "bundle_directory": bundle_directory,
    }


def run_case(
    unit_id,
    run_id=DEFAULT_RUN_ID,
    *,
    source_run_id=SOURCE_RUN_ID,
    differential_source=DEFAULT_RX_SOURCE,
    budget_s_per_model_bank=15.0,
):
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    if not source_run_id or Path(source_run_id).name != source_run_id:
        raise ValueError("source_run_id must be one path component")
    sources = _load_sources(unit_id, source_run_id, differential_source)
    output = ROOT / "runs" / run_id / unit_id
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    artifact_paths = [
        sources["source_path"],
        sources["calibration_source"]["source_path"],
        sources["calibration_source"]["summary_path"],
        sources["bundle_directory"] / "bundle.json",
        sources["bundle_directory"] / "bundle.npz",
    ]
    source_snapshot = snapshot_files(source_paths)
    artifact_snapshot = snapshot_files(artifact_paths)
    bundle = load_module(f"finite_set_relative_rx_bundle_{unit_id}", bundle_path)
    data = GroupMedianGeometryData(bundle.Data(sources["bundle_directory"]))
    started = time.monotonic()
    fitted = fit_relative_rx_models(
        data,
        sources["source"],
        sources["calibration_case"],
        budget_s_per_model_bank=budget_s_per_model_bank,
    )
    assert_snapshot_unchanged(source_snapshot)
    assert_snapshot_unchanged(artifact_snapshot)
    receipt = {
        "schema": "finite-set-relative-rx-fit/v1",
        "stage": "finite_set_relative_rx",
        "unit": sources["source"]["unit"],
        "dataset": sources["source"]["dataset"],
        "run_id": run_id,
        "source_run_id": source_run_id,
        "source_fit": str(sources["source_path"]),
        "source_fit_sha256": digest(sources["source_path"]),
        "rx_calibration_source": str(sources["calibration_source"]["source_path"]),
        "rx_calibration_source_sha256": sources["calibration_source"]["source_sha256"],
        "rx_calibration_summary": str(sources["calibration_source"]["summary_path"]),
        "rx_calibration_summary_sha256": sources["calibration_source"][
            "summary_sha256"
        ],
        "source_hashes_prefit": source_snapshot,
        "bound_artifact_hashes_prefit": artifact_snapshot,
        "source_hashes_postfit": snapshot_files(source_paths),
        "bound_artifact_hashes_postfit": snapshot_files(artifact_paths),
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
            "curvature_bound_hz": CURVATURE_BOUND_HZ,
            "physical_rx_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
            "finite_set_clutter_rate": 2.0,
            "budget_s_per_model_per_bank": float(budget_s_per_model_bank),
            "optimizer": "analytic-vjp SLSQP shared by both compared models",
        },
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "limitations": (
            "The differential calibration was estimated from these same stored observations and "
            "is treated as a fixed plug-in without uncertainty propagation. It is not added as an "
            "independent likelihood factor. The normalized finite-set likelihood remains a "
            "conditional approximation with frozen heuristic clutter rate and piecewise "
            "visibility. No reference coordinates or post-fit evaluations are read before seal."
        ),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--source-run-id", default=SOURCE_RUN_ID)
    parser.add_argument("--rx-source", type=Path, default=DEFAULT_RX_SOURCE)
    parser.add_argument("--budget-s-per-model-bank", type=float, default=15.0)
    args = parser.parse_args()
    fit_path, receipt = run_case(
        args.unit_id,
        args.run_id,
        source_run_id=args.source_run_id,
        differential_source=args.rx_source,
        budget_s_per_model_bank=args.budget_s_per_model_bank,
    )
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "score_leader_model": receipt["fit"]["combined_selection"][
                    "score_leader"
                ]["model"],
                "selection_resolved": receipt["fit"]["combined_selection"][
                    "selection_resolved"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "calibration_derivative",
    "common_quadratic_basis",
    "fit_relative_rx_models",
    "fit_tied_finite_set_trial",
    "physical_endpoint_slopes",
    "run_case",
    "slope_constraint",
]
