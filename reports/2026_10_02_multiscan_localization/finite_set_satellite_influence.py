#!/usr/bin/env python3
"""Truth-free per-satellite score allocation at sealed finite-set fits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms
from finite_set_likelihood import circular_residual
from finite_set_rf_score import _selected_trial, validate_authoritative_bindings
from gauss_newton import _free_variables
from prediction_plan import SharedPredictionPlan

ROOT = Path(__file__).resolve().parent
SOURCE_RUN = "finite-set-tau-profile-v1"
SCHEMA = "finite-set-satellite-influence/v1"
DEFAULT_PROFILE_ROOT = ROOT / "runs" / SOURCE_RUN
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-satellite-influence-v1.json"
EXPORT_SHA256 = "8752be16157de6c04e7242e6178d2e9e74725ec3c5eb279e9cbc3eefc43b34b1"
INITIAL_UNITS = ("DS10-S01", "DS11-S02")
ALL_UNITS = tuple(
    f"{dataset}-S{index:02d}"
    for dataset in ("DS10", "DS11")
    for index in range(1, 17)
)
SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
SLOPE_BOUND_HZ_S = 50.0
CONDITION_LIMIT = 1e12
SOURCE_DEPENDENCIES = (
    "finite_set_satellite_influence.py",
    "finite_set_rf_score.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "alias_family_joint.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "rough_smoke.py",
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def snapshot(paths):
    result = {}
    for path in paths:
        resolved = str(Path(path).resolve())
        if resolved in result:
            raise ValueError(f"duplicate provenance path {resolved}")
        result[resolved] = digest(path)
    return result


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def physical_specification(candidate_count, satellites):
    satellites = np.asarray(satellites, dtype=int)
    if (
        not isinstance(candidate_count, (int, np.integer))
        or candidate_count <= 0
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
    ):
        raise ValueError("selected satellites must be unique valid candidate indices")
    active = np.r_[np.arange(6), 6 + satellites]
    scales = np.r_[
        20.0,
        20.0,
        1000.0,
        10.0,
        1000.0,
        10.0,
        np.ones(len(satellites)),
    ]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
        (None, None),
        (-SLOPE_BOUND_HZ_S / 10.0, SLOPE_BOUND_HZ_S / 10.0),
    ]
    bounds.extend([(-TAU_BOUND_S, TAU_BOUND_S)] * len(satellites))
    return active, scales, bounds


def solve_score_allocations(
    per_satellite_gradients,
    total_gradient,
    hessian,
    vector,
    bounds,
    scales,
    *,
    condition_limit=CONDITION_LIMIT,
):
    """Solve one frozen-free-set Fisher system with all satellite scores as RHS."""

    per_satellite_gradients = np.asarray(per_satellite_gradients, dtype=float)
    total_gradient = np.asarray(total_gradient, dtype=float)
    hessian = np.asarray(hessian, dtype=float)
    vector = np.asarray(vector, dtype=float)
    scales = np.asarray(scales, dtype=float)
    if per_satellite_gradients.ndim != 2:
        raise ValueError("per-satellite gradients must be a matrix")
    satellite_count, parameter_count = per_satellite_gradients.shape
    if (
        satellite_count == 0
        or total_gradient.shape != (parameter_count,)
        or hessian.shape != (parameter_count, parameter_count)
        or vector.shape != (parameter_count,)
        or scales.shape != (parameter_count,)
        or len(bounds) != parameter_count
        or np.any(~np.isfinite(per_satellite_gradients))
        or np.any(~np.isfinite(total_gradient))
        or np.any(~np.isfinite(hessian))
        or np.any(~np.isfinite(vector))
        or np.any(~np.isfinite(scales))
        or np.any(scales <= 0)
    ):
        raise ValueError("score-allocation arrays are invalid or misaligned")
    if not np.isfinite(condition_limit) or condition_limit <= 1:
        raise ValueError("condition limit must be finite and greater than one")
    asymmetry = float(np.max(np.abs(hessian - hessian.T), initial=0.0))
    hessian_scale = max(1.0, float(np.max(np.abs(hessian), initial=0.0)))
    if asymmetry > 1e-10 * hessian_scale:
        raise ValueError("Fisher matrix is materially asymmetric")
    hessian = 0.5 * (hessian + hessian.T)
    gradient_sum = np.sum(per_satellite_gradients, axis=0)
    gradient_error = gradient_sum - total_gradient
    gradient_error_max = float(np.max(np.abs(gradient_error), initial=0.0))
    gradient_tolerance = 1e-10 * max(
        1.0, float(np.max(np.abs(total_gradient), initial=0.0))
    )
    if gradient_error_max > gradient_tolerance:
        raise ValueError("per-satellite gradients do not sum to the total gradient")

    free = _free_variables(vector, total_gradient, bounds)
    free_hessian = hessian[np.ix_(free, free)]
    diagnostics = {
        "available": False,
        "reason": None,
        "condition_limit": float(condition_limit),
        "condition_number": None,
        "minimum_eigenvalue": None,
        "maximum_eigenvalue": None,
        "free_parameter_count": int(np.sum(free)),
        "frozen_parameter_indices": np.flatnonzero(~free),
        "gradient_sum_max_abs_error": gradient_error_max,
        "step_sum_max_abs_error": None,
        "pseudoinverse_used": False,
        "solve_method": "single numpy.linalg.solve call with satellite and total multi-RHS",
    }
    empty_steps = np.full((satellite_count, parameter_count), np.nan)
    empty_total = np.full(parameter_count, np.nan)
    if not np.any(free):
        diagnostics["reason"] = "no_free_parameters"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }

    eigenvalues = np.linalg.eigvalsh(free_hessian)
    minimum = float(eigenvalues[0])
    maximum = float(eigenvalues[-1])
    diagnostics["minimum_eigenvalue"] = minimum
    diagnostics["maximum_eigenvalue"] = maximum
    eigen_tolerance = 1e-10 * max(1.0, abs(minimum), abs(maximum))
    if minimum < -eigen_tolerance:
        diagnostics["reason"] = "materially_indefinite"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }
    if minimum <= eigen_tolerance:
        diagnostics["reason"] = "nonpositive_or_rank_deficient"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }
    condition = maximum / minimum
    diagnostics["condition_number"] = float(condition)
    if not np.isfinite(condition) or condition > condition_limit:
        diagnostics["reason"] = "ill_conditioned"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }

    right_hand_sides = -np.column_stack(
        [per_satellite_gradients[:, free].T, total_gradient[free]]
    )
    try:
        solved = np.linalg.solve(free_hessian, right_hand_sides)
    except np.linalg.LinAlgError:
        diagnostics["reason"] = "linear_solve_failed"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }
    if np.any(~np.isfinite(solved)):
        diagnostics["reason"] = "nonfinite_linear_solution"
        return {
            "free": free,
            "per_satellite_steps_scaled": empty_steps,
            "total_step_scaled": empty_total,
            "diagnostics": diagnostics,
        }
    per_steps = np.zeros((satellite_count, parameter_count))
    total_step = np.zeros(parameter_count)
    per_steps[:, free] = solved[:, :satellite_count].T
    total_step[free] = solved[:, -1]
    step_error = np.sum(per_steps, axis=0) - total_step
    step_error_max = float(np.max(np.abs(step_error), initial=0.0))
    step_tolerance = 1e-10 * max(
        1.0, float(np.max(np.abs(total_step), initial=0.0))
    )
    if step_error_max > step_tolerance:
        raise ArithmeticError("per-satellite Fisher steps do not sum to the total step")
    diagnostics.update(
        available=True,
        reason="available",
        step_sum_max_abs_error=step_error_max,
    )
    return {
        "free": free,
        "per_satellite_steps_scaled": per_steps,
        "per_satellite_steps_physical": per_steps * scales,
        "total_step_scaled": total_step,
        "total_step_physical": total_step * scales,
        "diagnostics": diagnostics,
    }


def _validate_trial(data, trial):
    satellites = np.asarray(trial.get("satellite_indices"), dtype=int)
    parameters = np.asarray(trial.get("parameters"), dtype=float)
    weights = np.asarray(trial.get("satellite_weights"), dtype=float)
    if (
        parameters.shape != (6 + len(data.numbers),)
        or np.any(~np.isfinite(parameters))
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= len(data.numbers))
        or weights.shape != satellites.shape
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
        or not np.isfinite(trial.get("objective", np.nan))
    ):
        raise ValueError("selected source trial is malformed")
    if "coefficients_hz_ghz" in trial:
        raise ValueError("source trial is not the declared no-RF model")
    return satellites, parameters, weights


def _posterior_summary(data, predicted, likelihood, satellites):
    association = np.asarray(likelihood["row_association_probability"], dtype=float)
    support = np.asarray(likelihood["satellite_support"], dtype=float)
    if (
        association.shape != predicted.shape
        or support.shape != satellites.shape
        or np.any(~np.isfinite(association))
        or np.any(association < 0)
        or np.any(~np.isfinite(support))
        or not np.allclose(np.sum(association, axis=0), support, rtol=1e-10, atol=1e-8)
    ):
        raise ValueError("finite-set posterior support is malformed")
    residual = circular_residual(
        np.asarray(data.measured, dtype=float)[:, None],
        predicted,
        float(likelihood["alias_hz"]),
    )
    times = np.asarray(data.times, dtype=float)
    summaries = []
    for column, satellite in enumerate(satellites):
        weights = association[:, column]
        total = float(np.sum(weights))
        positive = weights > 0
        summaries.append(
            {
                "satellite_index": int(satellite),
                "catalog_number": int(np.asarray(data.numbers)[satellite]),
                "signal_support": total,
                "positive_posterior_rows": int(np.sum(positive)),
                "posterior_time_start_s": (
                    float(np.min(times[positive])) if np.any(positive) else None
                ),
                "posterior_time_end_s": (
                    float(np.max(times[positive])) if np.any(positive) else None
                ),
                "posterior_time_span_s": (
                    float(np.ptp(times[positive])) if np.any(positive) else None
                ),
                "posterior_residual_rms_hz": (
                    float(np.sqrt(np.sum(weights * residual[:, column] ** 2) / total))
                    if total > 0
                    else None
                ),
            }
        )
    total_support = float(np.sum(association))
    overall_rms = (
        float(np.sqrt(np.sum(association * residual**2) / total_support))
        if total_support > 0
        else None
    )
    return summaries, overall_rms


def compute_satellite_influence(
    data,
    trial,
    evaluator,
    *,
    plan_factory=SharedPredictionPlan,
    condition_limit=CONDITION_LIMIT,
):
    """Evaluate one sealed state without changing parameters or associations."""

    satellites, parameters, satellite_weights = _validate_trial(data, trial)
    active, scales, bounds = physical_specification(len(data.numbers), satellites)
    vector = parameters[active] / scales
    for index, (lower, upper) in enumerate(bounds):
        if (lower is not None and vector[index] < lower - 1e-12) or (
            upper is not None and vector[index] > upper + 1e-12
        ):
            raise ValueError("selected source state lies outside GNv2 bounds")
    plan = plan_factory(data, satellites)
    predicted, visible, jacobian = plan.predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = np.asarray(predicted, dtype=float).reshape(shape)
    visible = np.asarray(visible, dtype=bool).reshape(shape)
    likelihood = evaluator.evaluate(
        predicted,
        visible,
        sigma_hz=SIGMA_HZ,
        satellite_weights=satellite_weights,
        background_mass=0.2,
        return_gradient=True,
        return_precision=True,
    )
    prediction_score = np.asarray(likelihood["prediction_gradient"], dtype=float)
    prediction_precision = np.asarray(likelihood["prediction_precision"], dtype=float)
    if (
        prediction_score.shape != shape
        or prediction_precision.shape != shape
        or np.any(~np.isfinite(prediction_score))
        or np.any(~np.isfinite(prediction_precision))
        or np.any(prediction_precision < 0)
    ):
        raise ValueError("finite-set prediction derivatives are malformed")

    full_count = 6 + len(data.numbers)
    direct_physical_gradient = -np.asarray(
        jacobian.transpose_multiply(prediction_score.ravel()), dtype=float
    )
    physical_hessian = np.asarray(
        jacobian.normal_matrix(prediction_precision.ravel()), dtype=float
    )
    if direct_physical_gradient.shape != (full_count,) or physical_hessian.shape != (
        full_count,
        full_count,
    ):
        raise ValueError("prediction Jacobian derivatives have the wrong dimensions")
    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    direct_physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    physical_hessian[tau_indices, tau_indices] += 1.0 / TAU_SIGMA_S**2
    objective = -float(likelihood["total_log_likelihood"]) + tau_prior
    if not np.isclose(objective, float(trial["objective"]), rtol=0.0, atol=1e-6):
        raise ValueError("diagnostic evaluation does not reproduce the sealed no-RF objective")

    per_gradients = []
    for column, tau_index in enumerate(tau_indices):
        masked_score = np.zeros(shape)
        masked_score[:, column] = prediction_score[:, column]
        contribution = -np.asarray(
            jacobian.transpose_multiply(masked_score.ravel()), dtype=float
        )
        contribution[tau_index] += parameters[tau_index] / TAU_SIGMA_S**2
        per_gradients.append(contribution[active] * scales)
    per_gradients = np.asarray(per_gradients)
    total_gradient = direct_physical_gradient[active] * scales
    hessian = physical_hessian[np.ix_(active, active)]
    hessian = hessian * scales[:, None] * scales[None, :]
    hessian = 0.5 * (hessian + hessian.T)
    allocation = solve_score_allocations(
        per_gradients,
        total_gradient,
        hessian,
        vector,
        bounds,
        scales,
        condition_limit=condition_limit,
    )
    posterior, overall_rms = _posterior_summary(data, predicted, likelihood, satellites)
    available = allocation["diagnostics"]["available"]
    satellite_rows = []
    for column, summary in enumerate(posterior):
        row = {
            **summary,
            "tau_s": float(tau[column]),
            "tau_prior_nll_gradient": float(tau[column] / TAU_SIGMA_S**2),
            "nll_gradient_scaled": per_gradients[column],
            "east_score_allocation_km": None,
            "north_score_allocation_km": None,
        }
        if available:
            step = allocation["per_satellite_steps_physical"][column]
            row["east_score_allocation_km"] = float(step[0])
            row["north_score_allocation_km"] = float(step[1])
        satellite_rows.append(row)
    parameter_names = [
        "east_km",
        "north_km",
        "rx0_intercept_hz",
        "rx0_slope_hz_s",
        "rx1_intercept_hz",
        "rx1_slope_hz_s",
        *[f"tau_satellite_{satellite}_s" for satellite in satellites],
    ]
    result = {
        "status": "complete" if available else "unavailable",
        "availability": allocation["diagnostics"],
        "selected_satellite_count": len(satellites),
        "active_parameter_names": parameter_names,
        "active_parameter_indices": active,
        "parameter_scales": scales,
        "source_parameters_unchanged": True,
        "source_objective": float(trial["objective"]),
        "reproduced_objective": objective,
        "objective_absolute_error": abs(objective - float(trial["objective"])),
        "tau_prior": tau_prior,
        "total_nll_gradient_scaled": total_gradient,
        "posterior_residual_rms_hz": overall_rms,
        "satellites": satellite_rows,
        "free_mask_from_total_gradient": allocation["free"],
        "total_score_step_east_km": None,
        "total_score_step_north_km": None,
        "sum_satellite_step_east_km": None,
        "sum_satellite_step_north_km": None,
        "method": {
            "gradient": (
                "Per-satellite NLL gradient is minus J.T times the finite-set prediction "
                "log-likelihood score masked to that satellite, plus only that tau prior."
            ),
            "curvature": (
                "GNv2 scaled complete-data/Fisher J.T W J plus selected-tau prior curvature."
            ),
            "free_set": "One frozen source-bound free mask computed from the total gradient.",
            "solve": "One reduced H_ff multi-RHS solve; no inverse or pseudoinverse.",
            "position_scale_km": 20.0,
        },
        "interpretation": (
            "Finite-set associations are coupled and held at the sealed state. Allocations are "
            "conditional complete-data/Fisher score decompositions, not exact delete-one or "
            "leave-one-satellite-out effects, calibrated covariance, significance, or refits."
        ),
    }
    if available:
        total_physical = allocation["total_step_physical"]
        summed_physical = np.sum(allocation["per_satellite_steps_physical"], axis=0)
        result.update(
            total_score_step_east_km=float(total_physical[0]),
            total_score_step_north_km=float(total_physical[1]),
            sum_satellite_step_east_km=float(summed_physical[0]),
            sum_satellite_step_north_km=float(summed_physical[1]),
        )
    return result


def _source_paths():
    paths = [ROOT / name for name in SOURCE_DEPENDENCIES]
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return paths


def diagnose_unit(
    unit_id,
    *,
    profile_root=DEFAULT_PROFILE_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
    condition_limit=CONDITION_LIMIT,
):
    """Diagnose one predeclared score leader without fitting or exclusion."""

    if unit_id not in ALL_UNITS:
        raise ValueError("unit_id is outside the declared 32-unit finite-set cohort")
    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    source_paths = _source_paths()
    source_before = snapshot(source_paths)
    fixed_before = snapshot([profile_path, grouped_path])

    trial = _selected_trial(profile)
    if (
        profile.get("run_id") != SOURCE_RUN
        or profile.get("unit", {}).get("unit_id") != unit_id
        or profile.get("unit", {}).get("size") != 1
        or profile.get("dataset") != unit_id[:4]
        or profile.get("source_fit_sha256") != digest(grouped_path)
        or grouped.get("schema") != "finite-set-grouped-cohort/v1"
        or grouped.get("unit", {}).get("unit_id") != unit_id
        or grouped.get("reference_read_before_seal") is not False
        or grouped.get("evaluation_written") is not False
        or not grouped.get("sealed_utc")
    ):
        raise ValueError("profile and grouped no-RF source receipts are not strictly bound")
    authoritative = profile.get("source_hashes")
    if not isinstance(authoritative, dict) or not authoritative:
        raise ValueError("profile receipt lacks authoritative source hashes")
    assert_snapshot_unchanged(authoritative)

    from alias_family_joint import load_unit_with_family_exports

    _, data, input_paths = load_unit_with_family_exports(
        unit_id,
        exports,
        expected_manifest_sha256=expected_export_sha256,
    )
    loader_hashes = validate_authoritative_bindings(
        authoritative,
        input_paths,
        data.geometry_receipt,
        grouped.get("fit", {}).get("grouped_geometry", {}),
    )
    fixed_paths = [profile_path, grouped_path, *input_paths]
    fixed_before = snapshot(fixed_paths)
    satellites = np.asarray(trial["satellite_indices"], dtype=int)
    full_bank = np.asarray(profile.get("fit", {}).get("full_bank"), dtype=int)
    if full_bank.ndim != 1 or not len(full_bank):
        raise ValueError("profile source lacks its frozen full candidate bank")
    evaluator = build_likelihood_arms(
        data, len(satellites), len(full_bank)
    )["finite_set"]
    diagnostic = compute_satellite_influence(
        data,
        trial,
        evaluator,
        condition_limit=condition_limit,
    )
    assert_snapshot_unchanged(authoritative)
    source_after = snapshot(source_paths)
    fixed_after = snapshot(fixed_paths)
    if source_after != source_before or fixed_after != fixed_before:
        raise RuntimeError("diagnostic sources or sealed inputs changed during evaluation")
    return {
        "unit_id": unit_id,
        "dataset": profile["dataset"],
        "source_run_id": SOURCE_RUN,
        "source_selection": "predeclared score_leader",
        "profile_fit_sha256": digest(profile_path),
        "grouped_fit_sha256": digest(grouped_path),
        "source_hashes_snapshotted_before_validator_use": source_before,
        "source_hashes_after": source_after,
        "fixed_input_hashes_before": fixed_before,
        "fixed_input_hashes_after": fixed_after,
        "loader_inputs_bound_to_profile_source_hashes": loader_hashes,
        "diagnostic": diagnostic,
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "fit_performed": False,
            "parameter_refit_performed": False,
            "satellite_exclusion_performed": False,
        },
    }


def run(unit_ids=None, *, allow_all_32=False, **kwargs):
    expected = ALL_UNITS if allow_all_32 else INITIAL_UNITS
    requested = expected if unit_ids is None else tuple(unit_ids)
    if len(requested) != len(expected) or set(requested) != set(expected):
        label = "all 32 declared units" if allow_all_32 else f"exactly {INITIAL_UNITS}"
        raise ValueError(f"diagnostic requires {label}")
    return {
        "schema": SCHEMA,
        "source_run_id": SOURCE_RUN,
        "configuration": {
            "units": list(expected),
            "allow_all_32": bool(allow_all_32),
            "sigma_hz": SIGMA_HZ,
            "tau_sigma_s": TAU_SIGMA_S,
            "tau_bound_s": TAU_BOUND_S,
            "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
            "condition_limit": float(kwargs.get("condition_limit", CONDITION_LIMIT)),
        },
        "scope": (
            "Truth-free no-fit score allocation at each finite-set-tau-profile-v1 predeclared "
            "score leader. No reference, evaluation artifact, IQ, RF collection, parameter "
            "refit, satellite exclusion, or exact leave-one-out calculation is performed."
        ),
        "units": [diagnose_unit(unit_id, **kwargs) for unit_id in expected],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_ids", nargs="*", choices=ALL_UNITS)
    parser.add_argument("--allow-all-32", action="store_true")
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--condition-limit", type=float, default=CONDITION_LIMIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    receipt = run(
        arguments.unit_ids or None,
        allow_all_32=arguments.allow_all_32,
        profile_root=arguments.profile_root,
        grouped_root=arguments.grouped_root,
        exports=arguments.exports,
        expected_export_sha256=arguments.expected_export_sha256,
        condition_limit=arguments.condition_limit,
    )
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    arguments.output.write_text(json.dumps(jsonable(receipt), indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(arguments.output), "unit_count": len(receipt["units"])}))


if __name__ == "__main__":
    main()


__all__ = [
    "compute_satellite_influence",
    "physical_specification",
    "solve_score_allocations",
]
