"""Finite-set localization with receiver-specific quadratic time drift."""

from __future__ import annotations

import argparse
import copy
import json
import time
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
from quadratic_drift_fit import (
    CURVATURE_BOUND_HZ,
    CURVATURE_PRIOR_SIGMA_HZ,
    SLOPE_BOUND_HZ_S,
    TIME_SCALE_S,
    fit_quadratic_trial,
)
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import select_trials


SOURCE_RUN_ID = "finite-set-raw-control-v2"
DEFAULT_RUN_ID = "finite-set-quadratic-v1"
NUMERICAL_DEPENDENCIES = (
    "finite_set_quadratic.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "quadratic_drift_fit.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
)


def _same_numeric(left, right):
    left = np.asarray(left)
    right = np.asarray(right)
    if left.size == 0 and right.size == 0:
        return True
    return left.shape == right.shape and np.allclose(left, right, rtol=0, atol=1e-12)


class FiniteSetQuadraticLikelihoodAdapter:
    """Translate the quadratic prototype's mass contract to finite-set evaluation."""

    def __init__(self, finite_set, frozen_masses):
        self.finite_set = finite_set
        self.frozen_masses = copy.deepcopy(frozen_masses)
        self.last_result = None

    def evaluate(
        self,
        predicted,
        visible,
        *,
        sigma_hz,
        raw_satellite_mass,
        raw_background_mass,
        anchor_satellite_mass,
        anchor_unknown_mass,
        track_contamination,
        return_gradient=False,
        return_precision=False,
    ):
        supplied = {
            "raw_satellite_mass": raw_satellite_mass,
            "raw_background_mass": raw_background_mass,
            "anchor_satellite_mass": anchor_satellite_mass,
            "anchor_unknown_mass": anchor_unknown_mass,
        }
        if set(supplied) != set(self.frozen_masses):
            raise ValueError("finite-set quadratic masses are incomplete")
        for key, value in supplied.items():
            if not _same_numeric(value, self.frozen_masses[key]):
                raise ValueError(f"finite-set quadratic {key} differs from its frozen value")
        if np.asarray(anchor_satellite_mass).size or np.asarray(anchor_unknown_mass).size:
            raise ValueError("finite-set quadratic prototype is raw-only")
        if not np.isclose(track_contamination, 0.2, rtol=0, atol=0):
            raise ValueError("unexpected quadratic track-contamination argument")
        result = self.finite_set.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            satellite_weights=np.asarray(raw_satellite_mass, dtype=float),
            background_mass=float(raw_background_mass),
            return_gradient=return_gradient,
            return_precision=return_precision,
        )
        self.last_result = {
            **result,
            "track_unknown_responsibility": np.empty(0),
            "quadratic_mass_contract_translated": True,
        }
        return self.last_result


def _compact_trial(trial, model):
    return {
        "model": model,
        "satellite_count": int(trial["satellite_count"]),
        "satellite_indices": copy.deepcopy(trial["satellite_indices"]),
        "objective": float(trial["objective"]),
        "selection_score": float(trial["selection_score"]),
        "success": bool(trial["success"]),
        "status": trial["status"],
        "convergence_reason": trial.get("convergence_reason"),
    }


def _validate_source(source, unit_id):
    if source.get("schema") != "finite-set-raw-control-continuation/v1":
        raise ValueError("source must be a sealed finite-set v2 continuation")
    if source.get("stage") != "finite_set_raw_control_continuation":
        raise ValueError("source has the wrong finite-set stage")
    if source.get("reference_read_before_seal") is not False:
        raise ValueError("source was not sealed before reference access")
    if source.get("v1_evaluation_read") is not False:
        raise ValueError("source continuation read a prior evaluation")
    if source.get("evaluation_written") is not False:
        raise ValueError("source receipt unexpectedly contains an evaluation")
    if source.get("prefit_hashes_reverified_unchanged_before_seal") is not True:
        raise ValueError("source did not reverify its bound inputs")
    if source.get("unit", {}).get("unit_id") != unit_id:
        raise ValueError("source unit does not match the requested pilot")
    fit = source["fit"]
    trials = fit["finite_set_trials"]
    if not trials:
        raise ValueError("source contains no finite-set trials")
    banks = [tuple(np.asarray(trial["satellite_indices"], dtype=int)) for trial in trials]
    if len(set(banks)) != len(banks):
        raise ValueError("source contains duplicate finite-set banks")
    if any(trial.get("arm") != "finite_set" for trial in trials):
        raise ValueError("source finite-set ladder contains another arm")
    if fit.get("anchors_used_by_either_arm") != 0:
        raise ValueError("finite-set v2 source must be raw-only")
    return fit


def _likelihood_diagnostics(adapter):
    result = adapter.last_result
    return {
        "conditioned_nonempty": bool(result["conditioned_nonempty"]),
        "density_convention": result["density_convention"],
        "group_count": int(len(result["group_values"])),
        "total_satellite_support": float(np.sum(result["satellite_support"])),
        "total_expected_clutter_count": float(np.sum(result["expected_clutter_count"])),
        "total_raw_peak_count": int(np.sum(result["raw_peak_count"])),
        "total_unique_peak_count": int(np.sum(result["unique_peak_count"])),
        "quadratic_mass_contract_translated": True,
    }


def fit_finite_set_quadratic(
    data,
    source,
    *,
    budget_s=15.0,
    trial_fitter=fit_quadratic_trial,
    likelihood_preparer=prepare_finite_set_likelihood,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("budget_s must lie in (0, 15]")
    unit_id = source["unit"]["unit_id"]
    source_fit = _validate_source(source, unit_id)
    geometry = data if isinstance(data, GroupMedianGeometryData) else GroupMedianGeometryData(data)
    if geometry.geometry_receipt != source_fit["geometry"]:
        raise ValueError("reconstructed group-median geometry differs from sealed finite-set v2")
    full_bank = np.asarray(source_fit["full_bank"], dtype=int)
    if len(full_bank) == 0 or len(np.unique(full_bank)) != len(full_bank):
        raise ValueError("source full bank must be nonempty and unique")
    prepared = likelihood_preparer(geometry.measured, geometry.group)
    quadratic_trials = []
    baseline_trials = []
    per_bank_incumbents = []
    for source_trial in source_fit["finite_set_trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        if source_trial["satellite_count"] != len(satellites):
            raise ValueError("source finite-set bank cardinality is inconsistent")
        expected_masses = frozen_raw_masses(len(satellites), len(full_bank))
        source_masses = source_trial["raw_masses"]
        if set(source_masses) != set(expected_masses):
            raise ValueError("source finite-set masses are incomplete")
        if any(not _same_numeric(source_masses[key], value) for key, value in expected_masses.items()):
            raise ValueError("source finite-set masses differ from the frozen full-bank scale")
        expected_probability = 0.8 / len(full_bank)
        if not np.isclose(
            source_trial["per_satellite_probability"], expected_probability, rtol=0, atol=1e-12
        ):
            raise ValueError("source detection probability differs from the frozen full-bank scale")
        finite_set = FiniteSetLikelihoodAdapter(
            prepared,
            detection_probability=expected_probability,
            clutter_rate=float(source_fit["finite_set_clutter_rate"]),
        )
        adapter = FiniteSetQuadraticLikelihoodAdapter(finite_set, expected_masses)
        quadratic_source = dict(source_trial)
        quadratic_source["identity_masses"] = expected_masses
        trial = trial_fitter(
            geometry,
            quadratic_source,
            adapter,
            budget_s=float(budget_s),
        )
        if not np.isclose(
            trial["initial_objective"], source_trial["objective"], rtol=0, atol=1e-5
        ):
            raise ValueError("zero-curvature state does not reproduce its finite-set v2 seed")
        trial["model"] = "finite_set_quadratic"
        trial["source_model"] = "finite_set_linear_v2"
        trial["source_objective"] = float(source_trial["objective"])
        trial["source_selection_score"] = float(source_trial["selection_score"])
        trial["source_success"] = bool(source_trial["success"])
        trial["source_status"] = source_trial["status"]
        trial["zero_curvature_initialization"] = True
        trial["likelihood_diagnostics"] = _likelihood_diagnostics(adapter)
        quadratic_trials.append(trial)
        baseline = _compact_trial(source_trial, "finite_set_linear_v2")
        baseline_trials.append(baseline)
        quadratic = _compact_trial(trial, "finite_set_quadratic")
        per_bank_incumbents.append(
            min((baseline, quadratic), key=lambda candidate: candidate["selection_score"])
        )
    quadratic_selection = select_trials(quadratic_trials)
    baseline_selection = select_trials(baseline_trials)
    combined_selection = select_trials(
        baseline_trials
        + [_compact_trial(trial, "finite_set_quadratic") for trial in quadratic_trials]
    )
    return {
        "full_bank": full_bank,
        "fitted_bank_sizes": [int(trial["satellite_count"]) for trial in quadratic_trials],
        "quadratic_trials": quadratic_trials,
        "quadratic_selection": quadratic_selection,
        "baseline_linear_trials": baseline_trials,
        "baseline_linear_selection": baseline_selection,
        "per_bank_penalized_incumbents": per_bank_incumbents,
        "combined_penalized_selection": combined_selection,
        "geometry": copy.deepcopy(geometry.geometry_receipt),
        "anchors_used": 0,
        "same_bank_finite_set_v2_seed_only": True,
        "zero_curvature_initialization": True,
        "baseline_linear_v2_incumbent_retained": True,
        "bank_selection_reevaluated": True,
        "time_basis": "((group-median-time-reference_time_s)/150s)^2 - 1/3",
        "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
        "curvature_bound_hz": CURVATURE_BOUND_HZ,
        "total_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "coefficient_count": 2,
        "scope": (
            "Truth-free finite-set quadratic-drift pilot. Every bank starts from its sealed v2 "
            "finite-set parameters with zero receiver curvature. Candidate banks, group-median "
            "geometry, detection probability, clutter rate, sigma, tau prior and bounds remain "
            "frozen. The existing quadratic optimizer adds two regularized receiver curvature "
            "coefficients and its two-parameter model-selection penalty. The sealed linear v2 "
            "trials remain explicit penalized incumbents. No categorical arm, anchors, RF term, "
            "reference coordinate, or reference-derived parameter is used."
        ),
    }


def run_case(unit_id, run_id, *, budget_s=15.0):
    if unit_id not in ("DS10-S01", "DS11-S02"):
        raise ValueError("finite-set quadratic v1 is restricted to the two frozen pilots")
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be one path component")
    source_path = ROOT / "runs" / SOURCE_RUN_ID / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    source_fit = _validate_source(source, unit_id)
    output = ROOT / "runs" / run_id / unit_id
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    session_id = source["unit"]["session_ids"][0]
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle_directory = ROOT / "scans" / session_id
    source_paths = [ROOT / name for name in NUMERICAL_DEPENDENCIES] + [bundle_path]
    artifact_paths = [
        source_path,
        bundle_directory / "bundle.json",
        bundle_directory / "bundle.npz",
    ]
    source_hashes_prefit = snapshot_files(source_paths)
    artifact_hashes_prefit = snapshot_files(artifact_paths)
    bundle = load_module(f"finite_set_quadratic_bundle_{unit_id}", bundle_path)
    data = GroupMedianGeometryData(bundle.Data(bundle_directory))
    if data.geometry_receipt != source_fit["geometry"]:
        raise ValueError("pilot geometry does not reproduce the sealed finite-set v2 geometry")
    started = time.monotonic()
    fitted = fit_finite_set_quadratic(data, source, budget_s=budget_s)
    assert_snapshot_unchanged(source_hashes_prefit)
    assert_snapshot_unchanged(artifact_hashes_prefit)
    source_hashes_postfit = snapshot_files(source_paths)
    artifact_hashes_postfit = snapshot_files(artifact_paths)
    receipt = {
        "schema": "finite-set-quadratic-fit/v1",
        "stage": "finite_set_quadratic",
        "unit": source["unit"],
        "dataset": source["dataset"],
        "run_id": run_id,
        "source_run_id": SOURCE_RUN_ID,
        "source_fit": str(source_path),
        "source_fit_sha256": digest(source_path),
        "source_hashes_prefit": source_hashes_prefit,
        "source_hashes_postfit": source_hashes_postfit,
        "bound_artifact_hashes_prefit": artifact_hashes_prefit,
        "bound_artifact_hashes_postfit": artifact_hashes_postfit,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "linear_and_total_endpoint_slope_bound_hz_s": SLOPE_BOUND_HZ_S,
            "curvature_prior_sigma_hz": CURVATURE_PRIOR_SIGMA_HZ,
            "curvature_bound_hz": CURVATURE_BOUND_HZ,
            "extra_dof": 2,
            "finite_set_clutter_rate": float(source_fit["finite_set_clutter_rate"]),
            "finite_set_detection_probability": float(0.8 / len(source_fit["full_bank"])),
            "budget_s_per_bank": float(budget_s),
            "optimizer": "existing-joint-slsqp-linear-endpoint-constraints",
        },
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    output.mkdir(parents=True, exist_ok=False)
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--budget-s", type=float, default=15.0)
    args = parser.parse_args()
    if not 0 < args.budget_s <= 15:
        parser.error("budget-s must lie in (0, 15]")
    fit_path, receipt = run_case(args.unit_id, args.run_id, budget_s=args.budget_s)
    selection = receipt["fit"]["quadratic_selection"]
    combined = receipt["fit"]["combined_penalized_selection"]
    print(
        json.dumps(
            {
                "unit_id": args.unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "quadratic_leader_k": selection["score_leader"]["satellite_count"],
                "quadratic_selection_resolved": selection["selection_resolved"],
                "combined_model": combined["score_leader"]["model"],
                "combined_leader_k": combined["score_leader"]["satellite_count"],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "FiniteSetQuadraticLikelihoodAdapter",
    "fit_finite_set_quadratic",
    "run_case",
]
