#!/usr/bin/env python3
"""Refine screen-prescribed positive same-K identity replacements."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import numpy as np
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_identity_screen import (
    EXPORT_SHA256,
    SIGMA_HZ,
    SOURCE_RUN,
    SUPPORTED_UNITS,
)
from finite_set_rf_score import _selected_trial, validate_authoritative_bindings
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SCHEMA = "finite-set-identity-refine/v1"
SCREEN_SCHEMA = "finite-set-identity-screen/v1"
DEFAULT_SCREEN = ROOT / "finite-set-identity-screen-v1.json"
DEFAULT_PROFILE_ROOT = ROOT / "runs" / SOURCE_RUN
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-identity-refine-v1.json"
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
SLOPE_BOUND_HZ_S = 50.0
BUDGET_S_PER_REPLACEMENT = 15.0
DIRECT_DEPENDENCIES = (
    "finite_set_identity_refine.py",
    "finite_set_identity_screen.py",
    "finite_set_cavity.py",
    "finite_set_rf_score.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
    "alias_family_joint.py",
    "finite_set_grouped_cohort.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "rough_smoke.py",
    "selection.py",
)


def _unique_paths(paths):
    return list(dict.fromkeys(str(Path(path).resolve()) for path in paths))


def source_dependency_paths(screen, screen_path, profile_paths, grouped_paths):
    paths = [screen_path, *profile_paths, *grouped_paths]
    for unit in screen.get("units", []):
        inherited = unit.get("source_hashes_snapshotted_before_validator_use")
        if not isinstance(inherited, dict) or not inherited:
            raise ValueError("screen unit lacks its source-hash closure")
        if any(
            not isinstance(path, str) or not isinstance(value, str) or len(value) != 64
            for path, value in inherited.items()
        ):
            raise ValueError("screen source-hash closure is malformed")
        paths.extend(inherited)
    paths.extend(ROOT / name for name in DIRECT_DEPENDENCIES)
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return _unique_paths(paths)


def _positive_prescribed_swaps(screen_diagnostic):
    if (
        screen_diagnostic.get("complete") is not True
        or screen_diagnostic.get("status") != "complete"
        or screen_diagnostic.get("evaluated_pair_count")
        != screen_diagnostic.get("total_pair_count")
    ):
        raise ValueError("identity screen must be complete")
    top = screen_diagnostic.get("top3_full_dp")
    if not isinstance(top, list) or len(top) > 3:
        raise ValueError("identity screen top-three records are malformed")
    positive = []
    pairs = set()
    for item in top:
        pair = (item.get("removed_index"), item.get("added_index"))
        if (
            pair in pairs
            or not all(isinstance(value, int) for value in pair)
            or not np.isfinite(item.get("objective", np.nan))
            or not np.isfinite(item.get("objective_improvement", np.nan))
            or item.get("cavity_full_dp_objective_error", np.inf) > 1e-6
        ):
            raise ValueError("identity screen replacement record is malformed")
        pairs.add(pair)
        if item["objective_improvement"] > 0:
            positive.append(item)
    return positive


def _objective(data, parameters, satellites, weights, evaluator, plan_factory):
    predicted, visible, _ = plan_factory(data, satellites).predict(parameters)
    shape = (len(data.times), len(satellites))
    result = evaluator.evaluate(
        np.asarray(predicted, dtype=float).reshape(shape),
        np.asarray(visible, dtype=bool).reshape(shape),
        sigma_hz=SIGMA_HZ,
        satellite_weights=weights,
        background_mass=0.2,
    )
    tau = parameters[6 + satellites]
    return -float(result["total_log_likelihood"]) + 0.5 * float(
        np.sum((tau / TAU_SIGMA_S) ** 2)
    )


def refine_identity_replacements(
    data,
    source,
    full_bank,
    screen_diagnostic,
    *,
    refiner=refine_gauss_newton,
    arms_factory=build_likelihood_arms,
    plan_factory=SharedPredictionPlan,
):
    """Refine only positive replacements among the sealed screen's top three."""

    satellites = np.asarray(source.get("satellite_indices"), dtype=int)
    parameters = np.asarray(source.get("parameters"), dtype=float)
    weights = np.asarray(source.get("satellite_weights"), dtype=float)
    full_bank = np.asarray(full_bank, dtype=int)
    candidate_count = len(data.numbers)
    if (
        parameters.shape != (6 + candidate_count,)
        or np.any(~np.isfinite(parameters))
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or weights.shape != satellites.shape
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
        or full_bank.ndim != 1
        or len(full_bank) < len(satellites)
        or len(np.unique(full_bank)) != len(full_bank)
        or not set(satellites).issubset(set(full_bank))
    ):
        raise ValueError("source state or frozen full bank is malformed")
    if (
        screen_diagnostic.get("selected_count") != len(satellites)
        or screen_diagnostic.get("source_full_bank_count") != len(full_bank)
        or not np.isclose(
            screen_diagnostic.get("source_objective", np.nan),
            source["objective"],
            rtol=0,
            atol=1e-6,
        )
        or not np.isclose(
            screen_diagnostic.get("source_entry_penalty", np.nan),
            source["entry_penalty"],
            rtol=0,
            atol=1e-9,
        )
    ):
        raise ValueError("identity screen does not bind the source model")
    prescribed = _positive_prescribed_swaps(screen_diagnostic)
    incumbent = copy.deepcopy(source)
    incumbent.update(
        branch="sealed_source_incumbent",
        refit_performed=False,
        source_incumbent_preserved=True,
    )
    if not prescribed:
        selection = select_trials([incumbent])
        return {
            "full_bank": full_bank,
            "trials": [incumbent],
            "attempts": [],
            "selection": selection,
            "candidate_fit_count": 0,
            "positive_screen_replacement_count": 0,
            "source_unchanged_without_fit": True,
            "common_entry_penalty": float(source["entry_penalty"]),
            "scope": (
                "The complete same-K screen had no positive top-three replacement. The sealed "
                "source is recorded unchanged and no optimizer was called."
            ),
        }

    arms = arms_factory(data, len(satellites), len(full_bank))
    evaluator = arms["finite_set"]
    expected_probability = 0.8 / len(full_bank)
    if not np.isclose(
        evaluator.detection_probability, expected_probability, rtol=0, atol=1e-15
    ):
        raise ValueError("replacement refiner changed frozen full-K probability")
    source_objective = _objective(
        data, parameters, satellites, weights, evaluator, plan_factory
    )
    if not np.isclose(source_objective, source["objective"], rtol=0, atol=1e-6):
        raise ValueError("same-model evaluator does not reproduce source incumbent")

    trials = [incumbent]
    attempts = []
    selected_set = set(int(value) for value in satellites)
    for prescribed_swap in prescribed:
        removed = int(prescribed_swap["removed_index"])
        added = int(prescribed_swap["added_index"])
        locations = np.flatnonzero(satellites == removed)
        if len(locations) != 1 or added in selected_set or not 0 <= added < candidate_count:
            raise ValueError("screen prescribed an invalid same-K replacement")
        slot = int(locations[0])
        replacement_bank = satellites.copy()
        replacement_bank[slot] = added
        initial = parameters.copy()
        initial[6 + added] = 0.0
        direct_initial = _objective(
            data, initial, replacement_bank, weights, evaluator, plan_factory
        )
        if not np.isclose(
            direct_initial, prescribed_swap["objective"], rtol=0, atol=1e-6
        ):
            raise ValueError("replacement initializer does not reproduce sealed screen")
        candidate = refiner(
            data,
            initial,
            replacement_bank,
            weights.copy(),
            evaluator,
            sigma_hz=SIGMA_HZ,
            tau_sigma_s=TAU_SIGMA_S,
            tau_bound_s=TAU_BOUND_S,
            slope_bound=SLOPE_BOUND_HZ_S,
            budget_s=BUDGET_S_PER_REPLACEMENT,
        )
        if not np.isclose(
            candidate["initial_objective"], direct_initial, rtol=0, atol=1e-6
        ):
            raise ValueError("replacement GN initial objective changed the model")
        if candidate["objective"] > direct_initial + 1e-6:
            raise ValueError("replacement GN lost its fixed-state incumbent")
        if not np.array_equal(candidate["satellite_indices"], replacement_bank):
            raise ValueError("replacement GN changed the prescribed same-K bank")
        if not np.isclose(
            candidate["entry_penalty"], source["entry_penalty"], rtol=0, atol=1e-9
        ):
            raise ValueError("same-K replacement changed the source entry penalty")
        trial = copy.deepcopy(candidate)
        trial.update(
            branch="screen_prescribed_single_replacement",
            removed_index=removed,
            removed_catalog_number=int(np.asarray(data.numbers)[removed]),
            added_index=added,
            added_catalog_number=int(np.asarray(data.numbers)[added]),
            added_tau_initial_s=0.0,
            screen_fixed_state_objective=float(prescribed_swap["objective"]),
            screen_objective_improvement=float(
                prescribed_swap["objective_improvement"]
            ),
            conditional_single_source_leader_search=True,
            full_bank_global_convergence_claimed=False,
        )
        trials.append(trial)
        attempts.append(
            {
                "removed_index": removed,
                "added_index": added,
                "screen_record": prescribed_swap,
                "gn": candidate,
                "budget_s": BUDGET_S_PER_REPLACEMENT,
            }
        )
    selection = select_trials(trials)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "candidate_fit_count": len(attempts),
        "positive_screen_replacement_count": len(prescribed),
        "source_unchanged_without_fit": False,
        "common_entry_penalty": float(source["entry_penalty"]),
        "detection_probability_per_satellite": expected_probability,
        "conditional_single_source_leader_search": True,
        "full_bank_global_convergence_claimed": False,
        "scope": (
            "One 15-second GNv2 refinement for each positive replacement among the sealed exact "
            "screen's top three. The source incumbent, K, 0.8/source-full-K detection probability, "
            "entry penalty, likelihood, priors, and bounds are unchanged. This is a conditional "
            "single-source-leader replacement search, not full-bank global convergence."
        ),
    }


def run(*, screen_path=DEFAULT_SCREEN, diagnoser=None, **kwargs):
    screen_path = Path(screen_path)
    screen = json.loads(screen_path.read_text())
    if screen.get("schema") != SCREEN_SCHEMA or screen.get("source_run_id") != SOURCE_RUN:
        raise ValueError("source must be the grouped finite-set identity screen")
    screen_units = screen.get("units")
    if not isinstance(screen_units, list) or {
        unit.get("unit_id") for unit in screen_units if isinstance(unit, dict)
    } != set(SUPPORTED_UNITS):
        raise ValueError("identity screen must contain exactly the two declared pilots")
    if diagnoser is None:
        diagnoser = diagnose_unit
    return {
        "schema": SCHEMA,
        "source_screen_sha256": digest(screen_path),
        "source_run_id": SOURCE_RUN,
        "configuration": {
            "units": list(SUPPORTED_UNITS),
            "budget_s_per_replacement": BUDGET_S_PER_REPLACEMENT,
            "sigma_hz": SIGMA_HZ,
            "tau_sigma_s": TAU_SIGMA_S,
            "tau_bound_s": TAU_BOUND_S,
            "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        },
        "scope": (
            "Truth-free bounded refinements of only positive top-three same-K replacements from "
            "the sealed grouped finite-set screen. No substitution filtering, reference, "
            "evaluation artifact, IQ, RF collection, or global-bank convergence claim."
        ),
        "units": [
            diagnoser(unit_id, screen, screen_path=screen_path, **kwargs)
            for unit_id in SUPPORTED_UNITS
        ],
    }


def diagnose_unit(
    unit_id,
    screen,
    *,
    screen_path=DEFAULT_SCREEN,
    profile_root=DEFAULT_PROFILE_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
):
    matches = [unit for unit in screen["units"] if unit.get("unit_id") == unit_id]
    if len(matches) != 1:
        raise ValueError("identity screen must contain one requested unit")
    screen_unit = matches[0]
    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile_paths = [Path(profile_root) / unit / "fit.json" for unit in SUPPORTED_UNITS]
    grouped_paths = [Path(grouped_root) / unit / "fit.json" for unit in SUPPORTED_UNITS]
    closure = snapshot_files(
        source_dependency_paths(screen, screen_path, profile_paths, grouped_paths)
    )
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    trial = _selected_trial(profile)
    if (
        screen_unit.get("profile_fit_sha256") != digest(profile_path)
        or screen_unit.get("grouped_fit_sha256") != digest(grouped_path)
        or screen_unit.get("provenance", {}).get("reference_accessed") is not False
        or screen_unit.get("provenance", {}).get("evaluation_artifact_accessed") is not False
        or screen_unit.get("provenance", {}).get("fit_performed") is not False
        or profile.get("source_fit_sha256") != digest(grouped_path)
        or grouped.get("fit", {}).get("grouped_geometry") is None
    ):
        raise ValueError("screen and no-RF source receipts are not strictly bound")
    authoritative = profile.get("source_hashes")
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
        grouped["fit"]["grouped_geometry"],
    )
    fitted = refine_identity_replacements(
        data,
        trial,
        profile["fit"]["full_bank"],
        screen_unit["diagnostic"],
    )
    assert_snapshot_unchanged(closure)
    return {
        "unit_id": unit_id,
        "dataset": profile["dataset"],
        "source_selection": "predeclared score_leader",
        "profile_fit_sha256": digest(profile_path),
        "grouped_fit_sha256": digest(grouped_path),
        "screen_fit_sha256": digest(screen_path),
        "source_hashes_snapshotted_before_validator_use": closure,
        "loader_inputs_bound_to_profile_source_hashes": loader_hashes,
        "fit": fitted,
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "screen_substitution_filtering_performed": False,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    receipt = run(
        screen_path=arguments.screen,
        profile_root=arguments.profile_root,
        grouped_root=arguments.grouped_root,
        exports=arguments.exports,
        expected_export_sha256=arguments.expected_export_sha256,
    )
    arguments.output.write_text(
        json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({"output": str(arguments.output), "unit_count": len(receipt["units"])}))


if __name__ == "__main__":
    main()


__all__ = ["diagnose_unit", "refine_identity_replacements", "run"]
