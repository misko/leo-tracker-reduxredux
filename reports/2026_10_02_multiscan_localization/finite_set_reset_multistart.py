"""Truth-free grouped finite-set capture-reset multistart for frozen D08 pairs."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from capture_reset_fit import (
    canonicalize_capture_jumps,
    capture_reset_model_penalty,
    initialize_from_child_fits,
)
from capture_reset_gn import refine_capture_reset_gauss_newton
from finite_set_capture_reset import (
    _find_unit,
    child_rx_only_seed,
    evaluate_reset_seed,
    retained_continuous_incumbent,
    runner_numerical_dependency_paths,
    validate_child_rough_provenance,
    validate_group_capture_rx,
    validate_parent_binding,
)
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms, digest, snapshot_files
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-grouped-cohort-v1"
RUN_ID = "finite-set-reset-multistart-v1"
SCHEMA = "finite-set-reset-multistart/v1"
SUPPORTED_UNITS = ("DS10-D08", "DS11-D08")
NEW_DEPENDENCIES = (
    "finite_set_capture_reset.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
    "rough_smoke.py",
    "alias_family_joint.py",
)


def full_child_seed(data, child_fit_receipts):
    """Return the complete sealed-child initializer, including zero union-bank taus."""

    initialized = initialize_from_child_fits(data, child_fit_receipts)
    parameters = np.asarray(initialized["parameters"], dtype=float).copy()
    jumps = canonicalize_capture_jumps(initialized["capture_jumps_hz"])
    if parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(parameters)):
        raise ValueError("full child initializer does not match the union candidate bank")
    if np.any(np.abs(parameters[:2]) > 200.0):
        raise ValueError("child-median rough position lies outside the frozen position bounds")
    if np.any(np.abs(parameters[[3, 5]]) > 50.0 + 1e-12):
        raise ValueError("child-median RX slope lies outside the frozen slope bounds")
    if np.any(parameters[6:] != 0):
        raise ValueError("fresh child initializer must start all union-bank taus at zero")
    return {
        "parameters": parameters,
        "capture_jumps_hz": jumps,
        "child_initializer": initialized,
        "policy": (
            "Coordinate-wise median of sealed child rough positions, transformed child RX lines "
            "and capture jumps, and zero timing offsets for the full union candidate bank."
        ),
        "position_source": "sealed_child_rough_coordinate_median",
        "tau_source": "zero_fresh_union_bank",
    }


def _refine_seed(data, seed, satellites, likelihood, refiner):
    candidate = refiner(
        data,
        np.asarray(seed["parameters"], dtype=float).copy(),
        np.asarray(seed["capture_jumps_hz"], dtype=float).copy(),
        satellites,
        np.ones(len(satellites)),
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        tau_bound_s=3.0,
        slope_bound_hz_s=50.0,
        budget_s=15.0,
    )
    if not np.isclose(candidate["initial_objective"], seed["objective"], rtol=0, atol=1e-6):
        raise ValueError("reset GN does not reproduce its selected multistart seed")
    if candidate["objective"] > seed["objective"] + 1e-6:
        raise ValueError("reset GN lost its multistart seed incumbent")
    return candidate


def fit_reset_multistart_branches(
    data,
    parent_fit,
    child_fit_receipts,
    *,
    refiner=refine_capture_reset_gauss_newton,
    seed_evaluator=evaluate_reset_seed,
    rx_initializer=child_rx_only_seed,
    fresh_initializer=full_child_seed,
):
    """Refine a nested/RX start and a fresh full-child start for every bank."""

    geometry = validate_group_capture_rx(data)
    capture_count = geometry["capture_count"]
    full_bank = np.asarray(parent_fit.get("full_bank"), dtype=int)
    source_trials = parent_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("continuous parent lacks a finite-set bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("continuous parent banks are empty, duplicated, or omit the full bank")

    fresh = fresh_initializer(data, child_fit_receipts)
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        parameters = np.asarray(source["parameters"], dtype=float)
        likelihood = build_likelihood_arms(
            data,
            len(satellites),
            len(full_bank),
        )["finite_set"]
        nested = seed_evaluator(
            data,
            parameters,
            np.zeros((capture_count, 2)),
            satellites,
            likelihood,
        )
        if not np.isclose(nested["objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("nested zero-reset seed does not reproduce continuous parent")

        rx_seed = rx_initializer(data, parameters, child_fit_receipts)
        rx_only = seed_evaluator(
            data,
            rx_seed["parameters"],
            rx_seed["capture_jumps_hz"],
            satellites,
            likelihood,
        )
        fresh_seed = {
            "parameters": np.asarray(fresh["parameters"], dtype=float).copy(),
            "capture_jumps_hz": np.asarray(fresh["capture_jumps_hz"], dtype=float).copy(),
        }
        fresh_score = seed_evaluator(
            data,
            fresh_seed["parameters"],
            fresh_seed["capture_jumps_hz"],
            satellites,
            likelihood,
        )
        baseline_name = (
            "parent_rx_child"
            if rx_only["objective"] < nested["objective"]
            else "nested_parent"
        )
        baseline_seed = (
            {
                "parameters": np.asarray(rx_seed["parameters"], dtype=float).copy(),
                "capture_jumps_hz": np.asarray(
                    rx_seed["capture_jumps_hz"], dtype=float
                ).copy(),
                "objective": float(rx_only["objective"]),
            }
            if baseline_name == "parent_rx_child"
            else {
                "parameters": parameters.copy(),
                "capture_jumps_hz": np.zeros((capture_count, 2)),
                "objective": float(nested["objective"]),
            }
        )
        fresh_seed["objective"] = float(fresh_score["objective"])

        baseline_candidate = _refine_seed(
            data, baseline_seed, satellites, likelihood, refiner
        )
        fresh_candidate = _refine_seed(data, fresh_seed, satellites, likelihood, refiner)
        expected_penalty = capture_reset_model_penalty(
            nested["group_count"], len(satellites), capture_count
        )
        for candidate in (baseline_candidate, fresh_candidate):
            penalty = candidate.get("model_penalty", {}).get("total_penalty")
            if not np.isclose(
                penalty, expected_penalty["total_penalty"], rtol=0, atol=1e-9
            ):
                raise ValueError("multistart branch changed the reset-model penalty")

        nested_incumbent = retained_continuous_incumbent(
            source,
            nested,
            capture_count,
            "nested_continuous_incumbent_retained_by_objective",
        )
        candidates = (
            ("nested_parent", nested_incumbent),
            ("baseline_refinement", baseline_candidate),
            ("fresh_child_refinement", fresh_candidate),
        )
        selected_name, selected = min(candidates, key=lambda item: item[1]["objective"])
        trial = copy.deepcopy(selected)
        trial["source_continuous_objective"] = float(nested["objective"])
        trial["source_continuous_success"] = bool(source.get("success"))
        trial["selected_multistart_branch"] = selected_name
        trial["baseline_seed_selected"] = baseline_name
        trial["branch_completion_required_for_resolved_selection"] = True
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "nested_parent": nested,
                "parent_rx_child": rx_only,
                "fresh_full_child": fresh_score,
                "baseline_seed_selected": baseline_name,
                "baseline_refinement": baseline_candidate,
                "fresh_child_refinement": fresh_candidate,
                "baseline_branch_complete": bool(baseline_candidate.get("success")),
                "fresh_branch_complete": bool(fresh_candidate.get("success")),
                "selected_multistart_branch": selected_name,
                "fresh_seed_policy": fresh["policy"],
                "independent_refinements": True,
                "same_bank_same_model_objective_comparison": True,
            }
        )

    selection = select_trials(trials)
    branches_complete = all(
        attempt["baseline_branch_complete"] and attempt["fresh_branch_complete"]
        for attempt in attempts
    )
    selected_resolved = selection["selection_resolved"]
    selection["selection_resolved"] = selected_resolved and branches_complete
    selection["success"] = selection["selection_resolved"]
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": selection,
        "all_refinement_branches_complete": branches_complete,
        "selected_trials_resolved": selected_resolved,
        "group_capture_rx_validation": geometry,
        "capture_count": capture_count,
        "parent_bank_order_preserved": True,
        "optimizer": "complete-data-fisher-capture-reset-gn/v1",
        "refinements_per_bank": 2,
        "budget_s_per_refinement": 15.0,
        "detection_probability_per_satellite": 0.8 / len(full_bank),
        "clutter_rate": 2.0,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "scope": (
            "Each frozen continuous parent bank evaluates nested zero-reset, parent-position/tau "
            "with sealed child RX, and fully fresh sealed-child position/RX/jumps with zero taus. "
            "The better nested/RX seed and the independent fresh seed each receive one 15-second "
            "reset-aware GN refinement. The lowest same-model objective is retained. Selection is "
            "unresolved if any branch is incomplete. No reference coordinates are read or used."
        ),
    }


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    output = ROOT / "runs" / RUN_ID / unit_id
    if output.exists():
        raise FileExistsError(output)
    started = time.monotonic()
    snapshot = None
    try:
        selection = json.loads((ROOT / "selection.json").read_text())
        dataset, unit = _find_unit(selection, unit_id)
        if unit["size"] < 2:
            raise ValueError("reset multistart requires a pair or larger unit")
        parent_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
        parent = json.loads(parent_path.read_text())
        exports = ROOT / "runs" / "alias-family-cohort-v1"
        manifest_path = exports / "manifest.json"
        manifest_key = str(manifest_path.resolve())
        expected_manifest = parent.get("source_hashes", {}).get(manifest_key)
        if expected_manifest is None:
            raise ValueError("continuous parent does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_manifest,
        )
        parent_binding = validate_parent_binding(parent, unit, dataset, data, input_paths)
        single_by_session = {
            row["session_ids"][0]: row
            for row in selection["datasets"][dataset]["units"]
            if row["size"] == 1
        }
        child_receipts = {}
        child_provenance = []
        paths = [*parent_binding["source_hashes"], parent_path, Path(__file__)]
        paths.extend(runner_numerical_dependency_paths())
        paths.extend(ROOT / name for name in NEW_DEPENDENCIES)
        for session_id in unit["session_ids"]:
            single = single_by_session.get(session_id)
            if single is None:
                raise ValueError("parent capture lacks a frozen child single")
            child_path = ROOT / "runs" / "coherent-v1" / single["unit_id"] / "fit.json"
            receipt = json.loads(child_path.read_text())
            provenance = validate_child_rough_provenance(
                receipt,
                child_path,
                single,
                dataset,
            )
            child_receipts[session_id] = receipt
            child_provenance.append(provenance)
            paths.append(child_path)
            if provenance["cached_rough_fit_path"] is not None:
                paths.append(Path(provenance["cached_rough_fit_path"]))
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_reset_multistart_branches(
            data,
            parent["fit"],
            child_receipts,
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
        "unit": unit,
        "dataset": dataset,
        "source_run_id": SOURCE_RUN,
        "source_fit_sha256": digest(parent_path),
        "source_hashes": snapshot,
        "inherited_source_hashes": parent_binding["source_hashes"],
        "source_hash_audit": parent_binding["source_hash_audit"],
        "bound_input_hashes": parent_binding["bound_input_hashes"],
        "geometry_receipt": parent_binding["geometry_receipt"],
        "child_provenance": child_provenance,
        "limits": {
            "budget_s_per_refinement": 15.0,
            "refinements_per_bank": 2,
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
    "fit_reset_multistart_branches",
    "full_child_seed",
    "run_unit",
]
