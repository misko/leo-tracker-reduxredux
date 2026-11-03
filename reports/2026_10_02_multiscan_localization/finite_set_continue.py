"""Bounded same-bank numerical continuation of sealed finite-set v1 pilots."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    GroupMedianGeometryData,
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from gauss_newton import refine_gauss_newton
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN_ID = "finite-set-raw-control-v1"
DEFAULT_RUN_ID = "finite-set-raw-control-v2"


def _trial_diagnostics(arm, likelihood):
    result = likelihood.last_result
    if arm == "finite_set":
        return {
            "satellite_detection_probability": result["satellite_detection_probability"],
            "expected_clutter_count": result["expected_clutter_count"],
            "raw_peak_count": result["raw_peak_count"],
            "unique_peak_count": result["unique_peak_count"],
            "conditioned_nonempty": result["conditioned_nonempty"],
            "density_convention": result["density_convention"],
        }
    return {
        key: value for key, value in result.items() if "track" in key or key.endswith("group_count")
    }


def _candidate_from_incumbent(candidate, incumbent, arm, likelihood):
    candidate = dict(candidate)
    candidate.pop("satellite_weights", None)
    for key in (
        "arm",
        "source_parameters",
        "source_parameters_sha256",
        "full_bank_count",
        "per_satellite_probability",
        "raw_masses",
        "anchors_used",
    ):
        candidate[key] = copy.deepcopy(incumbent[key])
    candidate["continuation_seed_parameters"] = copy.deepcopy(incumbent["parameters"])
    candidate["continuation_source_run"] = SOURCE_RUN_ID
    candidate["likelihood_diagnostics"] = _trial_diagnostics(arm, likelihood)
    return candidate


def continue_arm_trials(
    data,
    source_trials,
    arm,
    full_bank_count,
    *,
    budget_s=30.0,
    refiner=refine_gauss_newton,
    likelihood_builder=build_likelihood_arms,
):
    if arm not in ("finite_set", "categorical_control"):
        raise ValueError("unknown continuation arm")
    if not np.isfinite(budget_s) or not 0 < budget_s <= 30:
        raise ValueError("continuation budget must lie in (0, 30]")
    retained = []
    attempts = []
    for source_trial in source_trials:
        incumbent = copy.deepcopy(source_trial)
        satellites = np.asarray(incumbent["satellite_indices"], dtype=int)
        if incumbent.get("arm") != arm:
            raise ValueError("source trial belongs to a different arm")
        if incumbent["satellite_count"] != len(satellites):
            raise ValueError("source trial bank cardinality is inconsistent")
        if incumbent["success"]:
            retained.append(incumbent)
            attempts.append(
                {
                    "satellite_count": len(satellites),
                    "attempted": False,
                    "reason": "v1_trial_already_converged",
                    "selected_branch": "verbatim_v1_incumbent",
                }
            )
            continue

        likelihood = likelihood_builder(data, len(satellites), full_bank_count)[arm]
        attempt = {
            "satellite_count": len(satellites),
            "satellite_indices": satellites,
            "attempted": True,
            "budget_s": float(budget_s),
            "incumbent_objective": float(incumbent["objective"]),
            "seed_is_exact_v1_same_arm_same_bank_incumbent": True,
        }
        try:
            candidate = refiner(
                data,
                np.asarray(incumbent["parameters"], dtype=float).copy(),
                satellites,
                np.ones(len(satellites)),
                likelihood,
                sigma_hz=200.0,
                tau_sigma_s=1.0,
                tau_bound_s=3.0,
                slope_bound=50.0,
                budget_s=float(budget_s),
            )
            if not np.isclose(
                candidate["initial_objective"],
                incumbent["objective"],
                rtol=0,
                atol=1e-6,
            ):
                raise ValueError("continuation seed objective does not reproduce v1 incumbent")
            candidate = _candidate_from_incumbent(candidate, incumbent, arm, likelihood)
            candidate_finite = np.isfinite(candidate["objective"])
            candidate_lower = candidate_finite and candidate["objective"] < incumbent["objective"]
            selected = candidate if candidate_lower else incumbent
            retained.append(selected)
            attempt.update(
                {
                    "candidate_objective": float(candidate["objective"]),
                    "candidate_success": bool(candidate["success"]),
                    "candidate_status": candidate["status"],
                    "candidate_convergence_reason": candidate["convergence_reason"],
                    "candidate_elapsed_s": float(candidate["elapsed_s"]),
                    "selected_branch": "continuation_candidate"
                    if candidate_lower
                    else "verbatim_v1_incumbent",
                    "lower_objective_retained": True,
                }
            )
        except Exception as error:
            retained.append(incumbent)
            attempt.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "selected_branch": "verbatim_v1_incumbent",
                    "lower_objective_retained": True,
                }
            )
        attempts.append(attempt)
    return retained, attempts, select_trials(retained)


def continue_v1_fit(
    data,
    source_fit,
    *,
    budget_s=30.0,
    refiner=refine_gauss_newton,
    likelihood_builder=build_likelihood_arms,
):
    full_bank_count = len(source_fit["full_bank"])
    finite_trials, finite_attempts, finite_selection = continue_arm_trials(
        data,
        source_fit["finite_set_trials"],
        "finite_set",
        full_bank_count,
        budget_s=budget_s,
        refiner=refiner,
        likelihood_builder=likelihood_builder,
    )
    control_trials, control_attempts, control_selection = continue_arm_trials(
        data,
        source_fit["categorical_control_trials"],
        "categorical_control",
        full_bank_count,
        budget_s=budget_s,
        refiner=refiner,
        likelihood_builder=likelihood_builder,
    )
    return {
        "full_bank": copy.deepcopy(source_fit["full_bank"]),
        "fitted_bank_sizes": copy.deepcopy(source_fit["fitted_bank_sizes"]),
        "finite_set_trials": finite_trials,
        "categorical_control_trials": control_trials,
        "finite_set_selection": finite_selection,
        "categorical_control_selection": control_selection,
        "finite_set_continuation_attempts": finite_attempts,
        "categorical_control_continuation_attempts": control_attempts,
        "geometry": copy.deepcopy(source_fit["geometry"]),
        "prediction_geometry_preflight": copy.deepcopy(source_fit["prediction_geometry_preflight"]),
        "anchors_used_by_either_arm": 0,
        "continuation_budget_s_per_nonconverged_trial": float(budget_s),
        "converged_v1_trials_preserved_verbatim": True,
        "nonconverged_trials_receive_at_most_one_call": True,
        "same_arm_same_bank_v1_incumbent_seeds_only": True,
        "cross_arm_objective_ranking_performed": False,
        "finite_set_clutter_rate": source_fit["finite_set_clutter_rate"],
        "finite_set_clutter_rate_semantics": source_fit["finite_set_clutter_rate_semantics"],
        "scope": (
            "Numerical continuation only. Each nonconverged v1 trial receives one bounded GN call "
            "from its exact same-arm, same-bank incumbent. Converged trials are copied verbatim. "
            "A continuation candidate replaces its incumbent only at lower finite objective on the "
            "same likelihood scale. Arm-specific ladder selection is recomputed; objectives are "
            "never compared across arms. No model, geometry, mass, prior, or bound changes."
        ),
    }


def validate_v1_bindings(receipt, fit_path):
    if receipt.get("schema") != "finite-set-raw-control-fit/v1":
        raise ValueError("unsupported v1 finite-set source schema")
    if receipt.get("reference_read_before_seal") is not False:
        raise ValueError("v1 source lacks truth-free sealing")
    if receipt.get("evaluation_written") is not False:
        raise ValueError("v1 source receipt unexpectedly includes evaluation")
    if receipt.get("prefit_hashes_reverified_unchanged_before_seal") is not True:
        raise ValueError("v1 source did not reverify prefit hashes")
    source_snapshot = receipt["source_hashes_prefit"]
    artifact_snapshot = receipt["bound_artifact_hashes_prefit"]
    assert_snapshot_unchanged(source_snapshot)
    assert_snapshot_unchanged(artifact_snapshot)
    return {
        "v1_fit": str(Path(fit_path)),
        "v1_fit_sha256": digest(fit_path),
        "v1_source_hashes": copy.deepcopy(source_snapshot),
        "v1_bound_artifact_hashes": copy.deepcopy(artifact_snapshot),
    }


def run_case(unit_id, run_id, *, budget_s=30.0):
    source_path = ROOT / "runs" / SOURCE_RUN_ID / unit_id / "fit.json"
    source_receipt = json.loads(source_path.read_text())
    if source_receipt["unit"]["unit_id"] != unit_id:
        raise ValueError("v1 source unit mismatch")
    provenance = validate_v1_bindings(source_receipt, source_path)
    output = ROOT / "runs" / run_id / unit_id
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")

    bundle = load_module(
        f"finite_set_continue_bundle_{unit_id}",
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    )
    session_id = source_receipt["unit"]["session_ids"][0]
    data = GroupMedianGeometryData(bundle.Data(ROOT / "scans" / session_id))
    if data.geometry_receipt != source_receipt["fit"]["geometry"]:
        raise ValueError("reconstructed group-median geometry differs from sealed v1")

    source_paths = [Path(path) for path in source_receipt["source_hashes_prefit"]]
    source_paths.append(Path(__file__))
    source_snapshot = snapshot_files(source_paths)
    artifact_paths = [Path(path) for path in source_receipt["bound_artifact_hashes_prefit"]]
    artifact_paths.append(source_path)
    artifact_snapshot = snapshot_files(artifact_paths)
    started = time.monotonic()
    fitted = continue_v1_fit(
        data,
        source_receipt["fit"],
        budget_s=budget_s,
    )
    assert_snapshot_unchanged(source_snapshot)
    assert_snapshot_unchanged(artifact_snapshot)
    receipt = {
        "schema": "finite-set-raw-control-continuation/v1",
        "stage": "finite_set_raw_control_continuation",
        "unit": source_receipt["unit"],
        "dataset": source_receipt["dataset"],
        "run_id": run_id,
        "source_run_id": SOURCE_RUN_ID,
        **provenance,
        "source_hashes_prefit": source_snapshot,
        "bound_artifact_hashes_prefit": artifact_snapshot,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "budget_s_per_nonconverged_trial": float(budget_s),
            "optimizer": "complete-data-fisher-gn/v2",
        },
        "reference_read_before_seal": False,
        "v1_evaluation_read": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    assert_snapshot_unchanged(source_snapshot)
    assert_snapshot_unchanged(artifact_snapshot)
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--budget-s", type=float, default=30.0)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        parser.error("run-id must be one path component")
    if not 0 < args.budget_s <= 30:
        parser.error("budget-s must lie in (0, 30]")
    fit_path, receipt = run_case(args.unit_id, args.run_id, budget_s=args.budget_s)
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "finite_set_leader_k": receipt["fit"]["finite_set_selection"]["score_leader"][
                    "satellite_count"
                ],
                "control_leader_k": receipt["fit"]["categorical_control_selection"]["score_leader"][
                    "satellite_count"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "continue_arm_trials",
    "continue_v1_fit",
    "run_case",
    "validate_v1_bindings",
]
