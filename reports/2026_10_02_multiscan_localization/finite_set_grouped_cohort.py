"""Uniform expanded-bank finite-set refinement for grouped cohort observations."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from gauss_newton import refine_gauss_newton
from rough_smoke import serializable
from selection import ROOT
from staged_fit import candidate_ladder, select_trials

RUN_ID = "finite-set-grouped-cohort-v1"
EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
EXPORT_SHA256 = "8752be16157de6c04e7242e6178d2e9e74725ec3c5eb279e9cbc3eefc43b34b1"


def expanded_seed_ladder(source_fit, candidate_count, capture_count):
    if candidate_count < 1 or capture_count not in (1, 2, 4):
        raise ValueError("invalid candidate or capture count")
    ladder = candidate_ladder(
        source_fit["rough"]["assignments"],
        sizes=tuple(size * capture_count for size in (4, 8, 12, 16)) + (candidate_count,),
    )
    source_trials = source_fit["trials"]
    by_bank = {tuple(trial["satellite_indices"]): trial for trial in source_trials}
    if len(by_bank) != len(source_trials) or not source_trials:
        raise ValueError("coherent source must contain distinct nonempty banks")
    largest = max(source_trials, key=lambda trial: len(trial["satellite_indices"]))
    seeds = []
    for satellites, support in ladder:
        if np.any(satellites < 0) or np.any(satellites >= candidate_count):
            raise ValueError("rough assignments contain invalid satellite indices")
        source = by_bank.get(tuple(satellites), largest)
        parameters = np.asarray(source["parameters"], dtype=float).copy()
        if parameters.shape != (6 + candidate_count,) or np.any(~np.isfinite(parameters)):
            raise ValueError("source parameters do not match the candidate pool")
        retained_tau = parameters[6 + satellites].copy()
        parameters[6:] = 0.0
        parameters[6 + satellites] = retained_tau
        seeds.append({
            "satellite_indices": satellites,
            "track_support": support,
            "parameters": parameters,
            "seed_bank": source["satellite_indices"],
            "seed_policy": "same_bank_coherent" if tuple(satellites) in by_bank
            else "largest_coherent_bank_with_omitted_tau_zero",
        })
    return seeds


def fit_grouped_cohort_unit(
    data, source_fit, *, capture_count, budget_s=15.0, refiner=refine_gauss_newton,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("per-bank budget must lie in (0, 15]")
    seeds = expanded_seed_ladder(source_fit, len(data.numbers), capture_count)
    full_bank = seeds[-1]["satellite_indices"]
    trials = []
    for seed in seeds:
        satellites = seed["satellite_indices"]
        likelihood = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
        trial = refiner(
            data, seed["parameters"].copy(), satellites, np.ones(len(satellites)), likelihood,
            sigma_hz=200.0, tau_sigma_s=1.0, tau_bound_s=3.0,
            slope_bound=50.0, budget_s=float(budget_s),
        )
        if trial["objective"] > trial["initial_objective"] + 1e-6:
            raise ValueError("grouped refinement lost its same-data seed incumbent")
        trial["seed"] = seed
        trials.append(trial)
    return {
        "full_bank": full_bank,
        "trials": trials,
        "selection": select_trials(trials),
        "detection_probability_per_satellite": 0.8 / len(full_bank),
        "clutter_rate": 2.0,
        "grouped_geometry": data.geometry_receipt,
        "rx_model": "one shared linear progression per RX across the entire unit",
        "capture_count": capture_count,
        "scope": (
            "Uniform track-ranked expanded banks, grouped finite-set likelihood, independent "
            "N(0,1s^2) timing priors bounded to +/-3s. Shared RX slopes bounded to +/-50Hz/s. "
            "No satellite frequency biases or capture intercept resets in this baseline. "
            "All families train the fit. Candidate pool conditional on persisted reviews."
        ),
    }


def joint_child_bindings(provenance):
    children = provenance.get("children")
    if children is None:
        children = provenance.get("legacy_manifest_artifacts", {}).get("children")
    if not isinstance(children, list) or not children:
        raise ValueError("joint provenance lacks child bundle bindings")
    return children


def _run_unit(unit_id, *, run_id=RUN_ID):
    from alias_family_joint import load_unit_with_family_exports

    directory = ROOT / "runs" / run_id / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    source_path = ROOT / "runs" / "coherent-v1" / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    selection_path = ROOT / "selection.json"
    selection = json.loads(selection_path.read_text())
    units = [
        unit for population in selection["datasets"].values() for unit in population["units"]
        if unit["unit_id"] == unit_id
    ]
    if (
        len(units) != 1 or source.get("stage") != "coherent"
        or source["unit"] != units[0]
        or source["selection_sha256"] != digest(selection_path)
    ):
        raise ValueError("coherent seed does not bind the frozen selected unit")
    unit = units[0]
    expected_inputs = {
        session: digest(ROOT / "scans" / session / "bundle.json")
        for session in unit["session_ids"]
    }
    if unit["size"] > 1:
        expected_inputs[unit_id] = digest(ROOT / "units" / unit_id / "bundle.json")
    if expected_inputs != source["inputs"]:
        raise ValueError("coherent seed input bundles changed")
    original, data, input_paths = load_unit_with_family_exports(
        unit_id, EXPORTS, expected_manifest_sha256=EXPORT_SHA256
    )
    if unit["size"] > 1:
        children = joint_child_bindings(original.provenance)
        if [child["session_id"] for child in children] != unit["session_ids"]:
            raise ValueError("joint provenance does not bind the selected child order")
        for child in children:
            session = child["session_id"]
            if (
                child["bundle_json_sha256"] != expected_inputs[session]
                or child["bundle_npz_sha256"]
                != digest(ROOT / "scans" / session / "bundle.npz")
            ):
                raise ValueError("joint provenance differs from the selected child bundle")
    if unit["size"] != len(unit["session_ids"]):
        raise ValueError("selected capture count is inconsistent")
    dependency_names = (
        "alias_family_joint.py", "finite_set_fit.py", "finite_set_likelihood.py",
        "gauss_newton.py", "prediction_plan.py", "prediction_jacobian.py", "joint_inputs.py",
        "staged_fit.py", "grouped_likelihood.py", "track_likelihood.py", "rough_smoke.py",
    )
    paths = [*input_paths, source_path, __file__]
    paths += [ROOT / name for name in dependency_names]
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    snapshot = snapshot_files(paths)
    started = time.monotonic()
    try:
        fitted = fit_grouped_cohort_unit(data, source["fit"], capture_count=unit["size"])
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / "failure.json").open("x") as stream:
            json.dump({
                "unit_id": unit_id, "error_type": type(error).__name__, "error": str(error),
                "source_hashes": snapshot, "elapsed_s": time.monotonic() - started,
                "reference_read_before_seal": False,
            }, stream, indent=2)
        raise
    result = {
        "schema": "finite-set-grouped-cohort/v1", "run_id": run_id,
        "unit": unit, "dataset": source["dataset"],
        "source_run_id": "coherent-v1", "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot, "selection_sha256": digest(selection_path),
        "original_row_count": len(original.times), "grouped_row_count": len(data.times),
        "reference_read_before_seal": False, "evaluation_written": False,
        "elapsed_s": time.monotonic() - started, "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "limitations": (
            "Conditional all-data development benchmark, not blind validation. "
            "Pairs/quads retain a continuous RX line; physical capture resets remain unmodeled."
        ),
    }
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "fit.json"
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(output), "sha256": digest(output)}


def run_unit(unit_id, *, run_id=RUN_ID):
    if not run_id or Path(run_id).name != run_id or run_id in (".", ".."):
        raise ValueError("run_id must be a single path component")
    if (
        len(unit_id) != 8 or unit_id[:4] not in ("DS10", "DS11")
        or unit_id[4] != "-" or unit_id[5] not in "SDQ" or not unit_id[6:].isdigit()
    ):
        raise ValueError("unit_id must identify a selected DS10/DS11 unit")
    directory = ROOT / "runs" / run_id / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    try:
        return _run_unit(unit_id, run_id=run_id)
    except Exception as error:
        if not directory.exists():
            directory.mkdir(parents=True, exist_ok=False)
            with (directory / "failure.json").open("x") as stream:
                json.dump({
                    "unit_id": unit_id, "stage": "loading_or_initialization",
                    "error_type": type(error).__name__, "error": str(error),
                    "reference_read_before_seal": False,
                }, stream, indent=2)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id")
    parser.add_argument("--run-id", default=RUN_ID)
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id, run_id=arguments.run_id)))
