"""One fixed-RF timing profile followed by RF-aware Fisher GN."""

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
from finite_set_rf_fit import (
    RF_BOUND_HZ_GHZ,
    RF_PRIOR_SIGMA_HZ_GHZ,
    SIGMA_HZ,
    SLOPE_BOUND_HZ_S,
    TAU_BOUND_S,
    TAU_SIGMA_S,
    receiver_rf_design,
)
from finite_set_rf_gn import fit_rf_gauss_newton_trial
from finite_set_tau_profile import profile_timing_offsets
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-rf-gn-v1"
RUN_ID = "finite-set-rf-profile-v1"
SOURCE_SCHEMA = "finite-set-rf-gn/v1"
SCHEMA = "finite-set-rf-profile/v1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
NEW_DEPENDENCIES = (
    "finite_set_tau_profile.py",
    "finite_set_cavity.py",
    "finite_set_rf_gn.py",
)


class FixedRFPredictor:
    """Cache shared plans and add fixed RF corrections after row expansion."""

    def __init__(
        self,
        data,
        coefficients_hz_ghz,
        design,
        *,
        plan_factory=SharedPredictionPlan,
    ):
        self.data = data
        self.coefficients_hz_ghz = np.asarray(coefficients_hz_ghz, dtype=float).copy()
        self.design = np.asarray(design, dtype=float).copy()
        if self.coefficients_hz_ghz.shape != (2,) or np.any(
            ~np.isfinite(self.coefficients_hz_ghz)
        ):
            raise ValueError("fixed RF coefficients must contain two finite values")
        if self.design.shape != (len(data.times), 2) or np.any(~np.isfinite(self.design)):
            raise ValueError("fixed RF design must align with data rows")
        self.correction_hz = self.design @ self.coefficients_hz_ghz
        self.plan_factory = plan_factory
        self.plans = {}
        self.plan_build_count = 0

    def __call__(self, data, parameters, satellites):
        if data is not self.data:
            raise ValueError("fixed-RF predictor received different data")
        satellites = np.asarray(satellites, dtype=int)
        key = tuple(int(value) for value in satellites)
        if key not in self.plans:
            self.plans[key] = self.plan_factory(data, satellites)
            self.plan_build_count += 1
        predicted, visible, _ = self.plans[key].predict(parameters)
        shape = (len(data.times), len(satellites))
        predicted = np.asarray(predicted, dtype=float).reshape(shape)
        predicted = predicted + self.correction_hz[:, None]
        return predicted, np.asarray(visible, dtype=bool).reshape(shape)


def coefficient_prior(coefficients_hz_ghz):
    coefficients = np.asarray(coefficients_hz_ghz, dtype=float)
    if coefficients.shape != (2,) or np.any(~np.isfinite(coefficients)):
        raise ValueError("RF coefficients must contain two finite values")
    return 0.5 * float(np.sum((coefficients / RF_PRIOR_SIGMA_HZ_GHZ) ** 2))


def derived_gn_seed(source, profile, constant_rf_prior):
    """Create an explicit mutable continuation seed without relabeling the source."""

    parameters = np.asarray(profile["parameters"], dtype=float)
    source_parameters = np.asarray(source["parameters"], dtype=float)
    coefficients = np.asarray(source["coefficients_hz_ghz"], dtype=float)
    if parameters.shape != source_parameters.shape or np.any(~np.isfinite(parameters)):
        raise ValueError("profiled parameters do not match the RF source state")
    full_objective = float(profile["objective"] + constant_rf_prior)
    seed = copy.deepcopy(source)
    seed["parameters"] = parameters.copy()
    seed["coefficients_hz_ghz"] = coefficients.copy()
    seed["objective"] = full_objective
    receipt = {
        "kind": "derived_fixed_rf_profile_seed",
        "source_parameters_sha256": array_digest(source_parameters),
        "profiled_parameters_sha256": array_digest(parameters),
        "fixed_coefficients_sha256": array_digest(coefficients),
        "source_full_objective": float(source["objective"]),
        "profile_likelihood_plus_tau_objective": float(profile["objective"]),
        "constant_rf_prior": float(constant_rf_prior),
        "derived_full_objective": full_objective,
        "source_object_not_mutated": True,
        "fixed_coefficients_preserved": True,
    }
    return seed, receipt


def _same_state(left, right):
    return np.array_equal(left["parameters"], right["parameters"]) and np.array_equal(
        left["coefficients_hz_ghz"], right["coefficients_hz_ghz"]
    )


def fit_rf_profile_branches(
    data,
    source_fit,
    *,
    cavity_factory,
    profiler=profile_timing_offsets,
    refiner=fit_rf_gauss_newton_trial,
):
    """Profile every bank once at fixed RF, then run one RF-aware GN continuation."""

    full_bank = np.asarray(source_fit.get("full_bank"), dtype=int)
    source_trials = source_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("source RF-GN fit lacks its bank ladder")
    source_banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(source_banks)) != len(source_banks):
        raise ValueError("source RF-GN banks must be nonempty and distinct")
    if tuple(full_bank) not in source_banks:
        raise ValueError("source RF-GN ladder omits its full bank")
    design, centers, spans = receiver_rf_design(data)
    if not np.array_equal(np.asarray(source_fit.get("rf_centers_hz")), centers):
        raise ValueError("reconstructed RF centers differ from sealed RF-GN source")

    trials = []
    attempts = []
    for source in source_trials:
        source_copy = copy.deepcopy(source)
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        parameters = np.asarray(source["parameters"], dtype=float)
        coefficients = np.asarray(source["coefficients_hz_ghz"], dtype=float)
        if (
            satellites.ndim != 1
            or not len(satellites)
            or len(np.unique(satellites)) != len(satellites)
            or np.any(satellites < 0)
            or np.any(satellites >= len(data.numbers))
        ):
            raise ValueError("source RF-GN trial has an invalid candidate bank")
        constant_prior = coefficient_prior(coefficients)
        if not np.isclose(
            source["coefficient_prior"], constant_prior, rtol=0, atol=1e-12
        ):
            raise ValueError("source RF prior differs from its sealed coefficients")
        likelihood = build_likelihood_arms(
            data,
            len(satellites),
            len(full_bank),
        )["finite_set"]
        predictor = FixedRFPredictor(data, coefficients, design)
        profile = profiler(
            data,
            parameters,
            satellites,
            likelihood.prepared,
            cavity_factory=cavity_factory,
            detection_probability=0.8 / len(full_bank),
            sigma_hz=SIGMA_HZ,
            clutter_rate=2.0,
            tau_sigma_s=TAU_SIGMA_S,
            tau_bound_s=TAU_BOUND_S,
            step_s=0.1,
            budget_s=20.0,
            predictor=predictor,
        )
        source_profile_objective = float(source["objective"] - constant_prior)
        if not np.isclose(
            profile["initial_objective"], source_profile_objective, rtol=0, atol=1e-6
        ):
            raise ValueError("fixed-RF timing profile does not reproduce its source")
        seed, seed_receipt = derived_gn_seed(source, profile, constant_prior)
        candidate = refiner(
            data,
            seed,
            likelihood,
            design,
            budget_s=20.0,
        )
        if not np.isclose(
            candidate["initial_objective"], seed["objective"], rtol=0, atol=1e-6
        ):
            raise ValueError("RF GN does not reproduce its derived profile seed")
        if candidate["objective"] > seed["objective"] + 1e-6:
            raise ValueError("RF GN lost its derived profile incumbent")
        if not np.isclose(
            candidate["total_entry_penalty"],
            source["total_entry_penalty"],
            rtol=0,
            atol=1e-9,
        ):
            raise ValueError("RF timing continuation changed the model penalty")
        if serializable(source) != serializable(source_copy):
            raise RuntimeError("RF timing continuation mutated its sealed source trial")

        use_candidate = candidate["objective"] < source["objective"]
        trial = copy.deepcopy(candidate if use_candidate else source)
        changed = not _same_state(trial, source)
        trial["source_rf_gn_objective"] = float(source["objective"])
        trial["selected_branch"] = "profile_then_rf_gn" if use_candidate else "sealed_source"
        trial["selected_state_changed_from_source"] = changed
        trial["convergence_provenance"] = (
            "derived_profile_gn_terminal" if use_candidate else "sealed_source_unchanged"
        )
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_objective": float(source["objective"]),
                "source_success": bool(source.get("success")),
                "constant_rf_prior": constant_prior,
                "profile_objective_without_rf_prior": float(profile["objective"]),
                "profile_full_objective": float(profile["objective"] + constant_prior),
                "profile": profile,
                "derived_gn_seed": seed_receipt,
                "rf_gn": candidate,
                "selected_branch": trial["selected_branch"],
                "predictor_plan_build_count": predictor.plan_build_count,
                "fixed_coefficients_during_profile": coefficients.copy(),
            }
        )
    selection = select_trials(trials)
    local_resolved = selection["selection_resolved"]
    profiles_complete = all(attempt["profile"]["complete"] for attempt in attempts)
    selection["selection_resolved"] = local_resolved and profiles_complete
    selection["success"] = selection["selection_resolved"]
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "local_refinements_resolved": local_resolved,
        "all_timing_profiles_complete": profiles_complete,
        "rf_centers_hz": centers,
        "rf_spans": spans,
        "source_bank_order_preserved": True,
        "profile_passes": 1,
        "profile_budget_s_per_bank": 20.0,
        "gn_budget_s_per_bank": 20.0,
        "sigma_hz": SIGMA_HZ,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "coefficient_prior_sigma_hz_ghz": RF_PRIOR_SIGMA_HZ_GHZ,
        "coefficient_bound_hz_ghz": RF_BOUND_HZ_GHZ,
        "scope": (
            "Exactly one bounded sequential tau profile with each source bank's RF coefficients "
            "fixed, followed by one RF-aware Fisher GN. The profile objective contains only the "
            "finite-set likelihood and tau prior; the unchanged RF prior is restored explicitly "
            "for full-model comparisons. Incomplete profiles remain explicit. Candidate banks, "
            "masses, priors, bounds, penalties, and inputs remain frozen; no reference is used."
        ),
    }


def validate_source_binding(source, unit_id, data, input_paths):
    """Validate the sealed RF-GN source, all inherited bytes, inputs, and geometry."""

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
        raise ValueError("source must be a sealed truth-free RF-GN fit")
    fit = source.get("fit", {})
    trials = fit.get("trials")
    full_bank = fit.get("full_bank")
    if not isinstance(trials, list) or len(trials) != 5 or not isinstance(full_bank, list):
        raise ValueError("source RF-GN fit must contain the frozen five-bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in trials]
    if any(not bank for bank in banks) or len(set(banks)) != 5 or tuple(full_bank) not in banks:
        raise ValueError("source RF-GN bank ladder is incomplete or duplicated")
    for trial in trials:
        if (
            trial.get("success") is not True
            or trial.get("sigma_hz") != SIGMA_HZ
            or trial.get("tau_sigma_s") != TAU_SIGMA_S
            or trial.get("tau_bound_s") != TAU_BOUND_S
            or trial.get("rx_slope_bound_hz_s") != SLOPE_BOUND_HZ_S
            or trial.get("coefficient_prior_sigma_hz_ghz") != RF_PRIOR_SIGMA_HZ_GHZ
            or trial.get("coefficient_bound_hz_ghz") != RF_BOUND_HZ_GHZ
        ):
            raise ValueError("source RF-GN trials differ from the frozen model or convergence")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source RF-GN fit lacks numerical hashes")
    assert_snapshot_unchanged(source_hashes)
    actual_inputs = snapshot_files(input_paths)
    if actual_inputs != source.get("bound_input_hashes"):
        raise ValueError("reconstructed inputs differ from sealed RF-GN source")
    geometry = serializable(data.geometry_receipt)
    if geometry != source.get("geometry_receipt"):
        raise ValueError("reconstructed geometry differs from sealed RF-GN source")
    return {
        "source_hashes": dict(source_hashes),
        "bound_input_hashes": actual_inputs,
        "geometry_receipt": geometry,
    }


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_cavity import prepare_replacement_scorer

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
            raise ValueError("source RF-GN fit does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            manifest_path.parent,
            expected_manifest_sha256=expected_manifest,
        )
        binding = validate_source_binding(source, unit_id, data, input_paths)
        paths = [*binding["source_hashes"], source_path, Path(__file__)]
        paths.extend(ROOT / name for name in NEW_DEPENDENCIES)
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_rf_profile_branches(
            data,
            source["fit"],
            cavity_factory=prepare_replacement_scorer,
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
        "limits": {
            "profile_budget_s_per_bank": 20.0,
            "gn_budget_s_per_bank": 20.0,
            "profile_passes": 1,
            "numerical_threads": 1,
        },
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
    "FixedRFPredictor",
    "coefficient_prior",
    "derived_gn_seed",
    "fit_rf_profile_branches",
    "run_unit",
    "validate_source_binding",
]
