"""Direct zero-RF Fisher-GN continuation for all 32 profiled singles."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    array_digest,
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_rf_fit import model_penalties, receiver_rf_design
from finite_set_rf_gn import fit_rf_gauss_newton_trial
from finite_set_tau_continue import (
    expected_bound_input_hashes,
    validate_bound_input_hashes,
    validate_geometry_binding,
)
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-tau-profile-v1"
RUN_ID = "finite-set-rf-cohort-v1"
SOURCE_SCHEMA = "finite-set-tau-profile/v1"
SCHEMA = "finite-set-rf-cohort/v1"
SUPPORTED_UNITS = tuple(
    f"{dataset}-S{index:02d}"
    for dataset in ("DS10", "DS11")
    for index in range(1, 17)
)
NUMERICAL_DEPENDENCIES = (
    "finite_set_rf_gn.py",
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


def validate_source_record(source, unit_id):
    """Accept complete timing profiles regardless of local-refinement convergence."""

    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("run_id") != SOURCE_RUN
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("unit", {}).get("size") != 1
        or source.get("dataset") != unit_id[:4]
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free single timing-profile fit")
    fit = source.get("fit", {})
    trials = fit.get("trials")
    attempts = fit.get("attempts")
    full_bank = fit.get("full_bank")
    if (
        not isinstance(trials, list)
        or not 1 <= len(trials) <= 5
        or not isinstance(attempts, list)
        or len(attempts) != len(trials)
        or not isinstance(full_bank, list)
        or not full_bank
        or fit.get("all_timing_profiles_complete") is not True
    ):
        raise ValueError("source timing-profile ladder is incomplete")
    banks = []
    for trial, attempt in zip(trials, attempts, strict=True):
        bank = trial.get("satellite_indices")
        parameters = np.asarray(trial.get("parameters"), dtype=float)
        if (
            not isinstance(bank, list)
            or not bank
            or parameters.ndim != 1
            or np.any(~np.isfinite(parameters))
            or not np.isfinite(trial.get("objective", np.nan))
            or attempt.get("satellite_indices") != bank
            or attempt.get("profile", {}).get("complete") is not True
        ):
            raise ValueError("source bank or timing-profile attempt is invalid")
        banks.append(tuple(bank))
    if len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("source banks are duplicated or omit the full bank")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source lacks inherited hashes")
    if any(
        not isinstance(path, str) or not isinstance(value, str) or len(value) != 64
        for path, value in source_hashes.items()
    ):
        raise ValueError("source inherited hashes are malformed")
    if not isinstance(source.get("source_fit_sha256"), str) or len(
        source["source_fit_sha256"]
    ) != 64:
        raise ValueError("source grouped-fit digest is malformed")
    return source


def derive_zero_rf_trial(source_trial):
    """Expand one no-RF state into the two-coefficient RF model at c=0."""

    trial = copy.deepcopy(source_trial)
    satellites = np.asarray(trial["satellite_indices"], dtype=int)
    groups = int(trial["groups"])
    penalties = model_penalties(groups, len(satellites))
    if not np.isclose(
        trial["entry_penalty"], penalties["source_entry_penalty"], rtol=0, atol=1e-9
    ):
        raise ValueError("source entry penalty differs from its frozen bank size")
    if "coefficients_hz_ghz" in trial:
        raise ValueError("timing-profile source unexpectedly already contains RF coefficients")
    trial["coefficients_hz_ghz"] = np.zeros(2)
    trial["coefficient_prior"] = 0.0
    trial["rf_extra_parameter_count"] = 2
    trial["rf_dof_penalty"] = penalties["rf_dof_penalty"]
    trial["source_entry_penalty"] = penalties["source_entry_penalty"]
    trial["total_entry_penalty"] = penalties["total_entry_penalty"]
    trial["selection_score"] = float(trial["objective"] + penalties["total_entry_penalty"])
    receipt = {
        "kind": "zero_rf_expansion_of_timing_profile_state",
        "source_parameters_sha256": array_digest(
            np.asarray(source_trial["parameters"], dtype=float)
        ),
        "derived_parameters_sha256": array_digest(np.asarray(trial["parameters"], dtype=float)),
        "coefficients_hz_ghz": np.zeros(2),
        "coefficient_prior": 0.0,
        "source_objective": float(source_trial["objective"]),
        "derived_objective": float(trial["objective"]),
        "source_success": bool(source_trial.get("success")),
        "source_convergence_reason": source_trial.get("convergence_reason"),
        "source_convergence_not_inherited": True,
        "rf_parameter_penalty_added_once": penalties["rf_dof_penalty"],
    }
    return trial, receipt


def fit_rf_cohort_branches(
    data,
    source_fit,
    *,
    refiner=fit_rf_gauss_newton_trial,
):
    """Run one bounded direct RF-GN continuation for every unchanged source bank."""

    full_bank = np.asarray(source_fit.get("full_bank"), dtype=int)
    source_trials = source_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("source fit lacks its candidate ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("source banks are empty, duplicated, or omit the full bank")
    design, centers, spans = receiver_rf_design(data)
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        expanded, derivation = derive_zero_rf_trial(source)
        likelihood = build_likelihood_arms(
            data,
            len(satellites),
            len(full_bank),
        )["finite_set"]
        candidate = refiner(
            data,
            expanded,
            likelihood,
            design,
            budget_s=15.0,
        )
        if not np.isclose(
            candidate["initial_objective"], source["objective"], rtol=0, atol=1e-6
        ):
            raise ValueError("direct RF-GN does not reproduce its no-RF source")
        if candidate["objective"] > source["objective"] + 1e-6:
            raise ValueError("direct RF-GN lost its no-RF incumbent")
        if not np.isclose(
            candidate["total_entry_penalty"],
            expanded["total_entry_penalty"],
            rtol=0,
            atol=1e-9,
        ):
            raise ValueError("direct RF-GN changed the expanded model penalty")
        trial = copy.deepcopy(candidate)
        trial["source_timing_profile_objective"] = float(source["objective"])
        trial["source_timing_profile_success"] = bool(source.get("success"))
        trial["source_convergence_not_inherited"] = True
        trial["zero_rf_incumbent_preserved"] = True
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_success": bool(source.get("success")),
                "source_status": source.get("status"),
                "source_convergence_reason": source.get("convergence_reason"),
                "zero_rf_derivation": derivation,
                "rf_gn": candidate,
                "budget_s": 15.0,
            }
        )
    selection = select_trials(trials)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "rf_centers_hz": centers,
        "rf_spans": spans,
        "source_bank_order_preserved": True,
        "source_trial_count": len(source_trials),
        "budget_s_per_bank": 15.0,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "coefficient_prior_sigma_hz_ghz": 250.0,
        "coefficient_bound_hz_ghz": 1000.0,
        "scope": (
            "Direct complete-data/Fisher RF-GN from every sealed timing-profile bank at zero RF "
            "coefficients. The no-RF state is the retained incumbent under the expanded model. "
            "Candidate banks, finite-set masses, data, sigma, tau prior, physical bounds, and "
            "entry penalties remain frozen; exactly two RF parameters are added once. Source "
            "nonconvergence is accepted but never inherited as RF-model convergence. No reference "
            "coordinates or evaluation artifacts are read or written."
        ),
    }


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_grouped_cohort import EXPORT_SHA256, EXPORTS

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
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            EXPORTS,
            expected_manifest_sha256=EXPORT_SHA256,
        )
        bound_inputs = validate_bound_input_hashes(
            input_paths,
            expected_bound_input_hashes(source),
        )
        geometry = validate_geometry_binding(source, data.geometry_receipt)
        paths = [*source["source_hashes"], source_path, Path(__file__)]
        paths.extend(ROOT / name for name in NUMERICAL_DEPENDENCIES)
        paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_rf_cohort_branches(data, source["fit"])
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
        "limits": {"budget_s_per_bank": 15.0, "numerical_threads": 1},
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": True,
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
    "derive_zero_rf_trial",
    "fit_rf_cohort_branches",
    "run_unit",
    "validate_source_record",
]
