#!/usr/bin/env python3
"""Truth-free timing-prior sensitivity at all 32 sealed no-RF score leaders."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms
from finite_set_prior_sensitivity import prior_sensitivity
from finite_set_rf_score import _selected_trial, validate_authoritative_bindings
from finite_set_satellite_influence import (
    ALL_UNITS,
    EXPORT_SHA256,
    SOURCE_RUN,
    TAU_SIGMA_S,
    digest,
    jsonable,
    physical_specification,
    snapshot,
)
from finite_set_satellite_influence import (
    SOURCE_DEPENDENCIES as INFLUENCE_DEPENDENCIES,
)
from prediction_plan import SharedPredictionPlan

ROOT = Path(__file__).resolve().parent
SCHEMA = "finite-set-prior-sensitivity/v1"
DEFAULT_PROFILE_ROOT = ROOT / "runs" / SOURCE_RUN
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-prior-sensitivity-all32-v1.json"
SIGMA_HZ = 200.0
SOURCE_DEPENDENCIES = tuple(
    dict.fromkeys(
        (
            "finite_set_prior_sensitivity_run.py",
            "finite_set_prior_sensitivity.py",
            *INFLUENCE_DEPENDENCIES,
        )
    )
)


def source_dependency_paths():
    paths = [ROOT / name for name in SOURCE_DEPENDENCIES]
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return paths


def snapshot_before_validation(*, snapshotter=snapshot):
    """Snapshot every numerical dependency before source validators are called."""

    return snapshotter(source_dependency_paths())


def validate_source_receipts(profile, grouped, unit_id, grouped_path):
    """Apply the same sealed no-RF score-leader binding as influence diagnostics."""

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
    return _selected_trial(profile), authoritative


def compute_prior_sensitivity(
    data,
    trial,
    evaluator,
    *,
    plan_factory=SharedPredictionPlan,
    sensitivity=prior_sensitivity,
):
    """Assemble the sealed GNv2 gradient/Fisher and evaluate local prior response."""

    satellites = np.asarray(trial.get("satellite_indices"), dtype=int)
    parameters = np.asarray(trial.get("parameters"), dtype=float)
    satellite_weights = np.asarray(trial.get("satellite_weights"), dtype=float)
    candidate_count = len(data.numbers)
    if (
        parameters.shape != (6 + candidate_count,)
        or np.any(~np.isfinite(parameters))
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
        or satellite_weights.shape != satellites.shape
        or np.any(~np.isfinite(satellite_weights))
        or np.any(satellite_weights <= 0)
        or not np.isfinite(trial.get("objective", np.nan))
    ):
        raise ValueError("selected source trial is malformed")
    if "coefficients_hz_ghz" in trial:
        raise ValueError("source trial is not the declared no-RF model")

    active, scales, bounds = physical_specification(candidate_count, satellites)
    vector = parameters[active] / scales
    predicted, visible, jacobian = plan_factory(data, satellites).predict(parameters)
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

    full_count = 6 + candidate_count
    total_physical_gradient = -np.asarray(
        jacobian.transpose_multiply(prediction_score.ravel()), dtype=float
    )
    total_physical_hessian = np.asarray(
        jacobian.normal_matrix(prediction_precision.ravel()), dtype=float
    )
    if total_physical_gradient.shape != (full_count,) or total_physical_hessian.shape != (
        full_count,
        full_count,
    ):
        raise ValueError("prediction Jacobian derivatives have the wrong dimensions")
    tau_indices = 6 + satellites
    tau = parameters[tau_indices]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    total_physical_gradient[tau_indices] += tau / TAU_SIGMA_S**2
    total_physical_hessian[tau_indices, tau_indices] += 1.0 / TAU_SIGMA_S**2
    reproduced_objective = -float(likelihood["total_log_likelihood"]) + tau_prior
    if not np.isclose(reproduced_objective, trial["objective"], rtol=0, atol=1e-6):
        raise ValueError("diagnostic evaluation does not reproduce sealed objective")

    total_gradient = total_physical_gradient[active] * scales
    hessian = total_physical_hessian[np.ix_(active, active)]
    hessian = hessian * scales[:, None] * scales[None, :]
    hessian = 0.5 * (hessian + hessian.T)
    prior_gradient = np.r_[np.zeros(6), tau / TAU_SIGMA_S**2]
    result = sensitivity(
        hessian,
        total_gradient,
        prior_gradient,
        vector,
        bounds,
        scales,
    )
    return {
        "status": "complete" if result["available"] else "unavailable",
        "source_parameters_unchanged": True,
        "source_objective": float(trial["objective"]),
        "reproduced_objective": reproduced_objective,
        "objective_absolute_error": abs(reproduced_objective - trial["objective"]),
        "selected_satellite_count": len(satellites),
        "active_parameter_indices": active,
        "parameter_scales": scales,
        "tau_prior": tau_prior,
        "tau_prior_precision": 1.0 / TAU_SIGMA_S**2,
        "tau_prior_gradient_scaled": prior_gradient,
        "total_nll_gradient_scaled": total_gradient,
        "sensitivity": result,
        "method": {
            "curvature": "GNv2 scaled complete-data/Fisher J.T W J plus tau prior at lambda=1",
            "free_set": "one frozen source-bound free mask from the total lambda=1 gradient",
            "response": "dtheta/dlambda=-H_ff^-1 g_tau with no inverse or pseudoinverse",
            "zero_precision_shift": "Delta lambda=-1 first-order extrapolation only",
            "position_scale_km": 20.0,
        },
        "interpretation": (
            "Bound-conditional local sensitivity to timing-prior precision, not a free fit, "
            "bound-loosening result, calibrated uncertainty, or position correction."
        ),
    }


def diagnose_unit(
    unit_id,
    *,
    profile_root=DEFAULT_PROFILE_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
):
    """Diagnose one predeclared score leader without fitting or reference access."""

    if unit_id not in ALL_UNITS:
        raise ValueError("unit_id is outside the declared 32-unit finite-set cohort")
    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    source_before = snapshot_before_validation()
    fixed_before = snapshot([profile_path, grouped_path])
    trial, authoritative = validate_source_receipts(
        profile, grouped, unit_id, grouped_path
    )
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
    diagnostic = compute_prior_sensitivity(data, trial, evaluator)
    assert_snapshot_unchanged(authoritative)
    source_after = snapshot(source_dependency_paths())
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
            "timing_bound_changed": False,
            "manual_position_correction_applied": False,
        },
    }


def run(unit_ids=None, *, diagnoser=diagnose_unit, **kwargs):
    requested = ALL_UNITS if unit_ids is None else tuple(unit_ids)
    if len(requested) != len(ALL_UNITS) or set(requested) != set(ALL_UNITS):
        raise ValueError("diagnostic requires exactly all 32 declared units")
    return {
        "schema": SCHEMA,
        "source_run_id": SOURCE_RUN,
        "configuration": {
            "units": list(ALL_UNITS),
            "sigma_hz": SIGMA_HZ,
            "tau_sigma_s": TAU_SIGMA_S,
            "tau_prior_precision": 1.0 / TAU_SIGMA_S**2,
        },
        "scope": (
            "Truth-free no-fit local timing-prior sensitivity at all 32 sealed no-RF score "
            "leaders. Parameters, associations, source bounds, and the total-gradient free mask "
            "remain frozen. Delta lambda=-1 is a first-order diagnostic, not a fit or correction. "
            "No reference, evaluation artifact, IQ, RF collection, or bound change is used."
        ),
        "units": [diagnoser(unit_id, **kwargs) for unit_id in ALL_UNITS],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    receipt = run(
        profile_root=arguments.profile_root,
        grouped_root=arguments.grouped_root,
        exports=arguments.exports,
        expected_export_sha256=arguments.expected_export_sha256,
    )
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    arguments.output.write_text(
        json.dumps(jsonable(receipt), indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({"output": str(arguments.output), "unit_count": len(receipt["units"])}))


if __name__ == "__main__":
    main()


__all__ = [
    "compute_prior_sensitivity",
    "diagnose_unit",
    "run",
    "snapshot_before_validation",
    "source_dependency_paths",
    "validate_source_receipts",
]
