"""Satellite-bias ablation on sealed candidate-independent alias families."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime

import numpy as np
from finite_set_alias_family import FamilyGeometryData
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_satellite_bias import (
    NUMERICAL_DEPENDENCIES,
    FiniteSetLikelihoodAdapter,
    fit_satellite_bias_trial,
    frozen_raw_masses,
    prepare_finite_set_likelihood,
)
from rough_smoke import load_module, serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN_ID = "finite-set-alias-family-v1"
RUN_ID = "finite-set-family-bias-v1"


def reconstruct_geometry(data, source):
    families = source["grouping"]["families"]
    lineage = [item["input_row_index"] for family in families for item in family["lineage"]]
    if sorted(lineage) != list(range(len(data.times))):
        raise ValueError("family lineage must partition every original row exactly once")
    representatives = []
    for family in families:
        matches = [
            item["input_row_index"] for item in family["lineage"]
            if item["candidate_id"] == family["representative_candidate_id"]
        ]
        if len(matches) != 1:
            raise ValueError("family must have exactly one representative in its lineage")
        members = [item["input_row_index"] for item in family["lineage"]]
        if len(np.unique(data.group[members])) != 1:
            raise ValueError("family cannot cross observation groups")
        representatives.append(matches[0])
    if len(representatives) != source["representative_row_count"]:
        raise ValueError("representative count differs from sealed grouping")
    return FamilyGeometryData(data, representatives)


def validate_geometry_receipt(data, source, correction=None):
    receipt = source["geometry_receipt"]
    if "fitted_array_hashes" in receipt:
        if receipt != data.geometry_receipt:
            raise ValueError("fitted geometry differs from sealed geometry")
        return
    if receipt != data.geometry_receipt["preselection_geometry"] or correction is None:
        raise ValueError("legacy geometry requires its explicit postseal correction")
    if (
        correction["fitted_row_hashes"] != data.geometry_receipt["fitted_array_hashes"]
        or correction["original_rows_sha256"] != data.geometry_receipt["original_rows_sha256"]
        or correction["fitted_row_count"] != len(data.times)
        or correction["fitted_group_count"] != len(np.unique(data.group))
    ):
        raise ValueError("fitted geometry differs from sealed correction")


def fit_models(data, source_fit, *, fitter=fit_satellite_bias_trial, budget_s=15.0):
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    full_bank = source_fit["full_bank"]
    source_trials = source_fit["finite_set_trials"]
    banks = [tuple(trial["satellite_indices"]) for trial in source_trials]
    if not banks or len(banks) != len(set(banks)) or tuple(full_bank) not in banks:
        raise ValueError("source must contain a unique ladder including its full bank")
    bias_trials = []
    baseline_trials = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        groups = len(np.unique(data.group))
        entry_penalty = 0.5 * len(satellites) * np.log(groups)
        if (
            not np.isclose(source["entry_penalty"], entry_penalty, rtol=0, atol=1e-8)
            or not np.isclose(
                source["selection_score"], source["objective"] + entry_penalty,
                rtol=0, atol=1e-8,
            )
        ):
            raise ValueError("baseline score differs from frozen penalty convention")
        likelihood = FiniteSetLikelihoodAdapter(
            prepared, detection_probability=0.8 / len(full_bank), clutter_rate=2.0
        )
        likelihood.frozen_masses = frozen_raw_masses(len(satellites), len(full_bank))
        trial = fitter(data, source, likelihood, budget_s=budget_s)
        if not np.isclose(trial["initial_objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("zero-bias objective does not reproduce grouped seed")
        if trial["objective"] > trial["initial_objective"] + 1e-6:
            raise ValueError("bias fit lost its finite zero-bias incumbent")
        bias_penalty = 0.5 * (len(satellites) - 1) * np.log(groups)
        if not np.isclose(
            trial["selection_score"], trial["objective"] + entry_penalty + bias_penalty,
            rtol=0, atol=1e-8,
        ):
            raise ValueError("bias score differs from frozen contrast penalty")
        baseline = copy.deepcopy(source)
        baseline["model"] = "grouped_linear"
        baseline_trials.append(baseline)
        bias_trials.append(trial)
    return {
        "full_bank": full_bank,
        "baseline_trials": baseline_trials,
        "satellite_bias_trials": bias_trials,
        "baseline_selection": select_trials(baseline_trials),
        "satellite_bias_selection": select_trials(bias_trials),
        "combined_selection": select_trials(baseline_trials + bias_trials),
        "omega_prior": "N(0, (200 Hz)^2), heuristic; shared across RX and channels",
        "score_interpretation": "Conditional penalized MAP, not calibrated marginal evidence",
    }


def run_case(unit_id, *, solver="lbfgs"):
    if solver not in ("lbfgs", "fisher-gn"):
        raise ValueError("unknown satellite-bias solver")
    run_id = RUN_ID if solver == "lbfgs" else "finite-set-family-bias-gn-v1"
    fitter = fit_satellite_bias_trial
    if solver == "fisher-gn":
        from finite_set_bias_gn import fit_satellite_bias_trial as fitter

    source_path = ROOT / "runs" / SOURCE_RUN_ID / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    if (
        source.get("schema") != "finite-set-alias-family-pilot/v1"
        or source.get("unit_id") != unit_id
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("sealed") is not True
        or len(source["fit"]["finite_set_trials"]) != 5
    ):
        raise ValueError("source must be a sealed five-bank truth-free alias-family fit")
    directory = ROOT / "runs" / run_id / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    bundle_path = ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py"
    bundle_directory = ROOT / "scans" / source["session_id"]
    artifacts = [source_path, bundle_directory / "bundle.json", bundle_directory / "bundle.npz"]
    for path in artifacts[1:]:
        if digest(path) != source["source_hashes"][str(path.resolve())]:
            raise ValueError("original bundle no longer matches sealed grouping source")
    correction_path = source_path.parent / "receipt-correction.json"
    correction = None
    if "fitted_array_hashes" not in source["geometry_receipt"]:
        correction = json.loads(correction_path.read_text())
        if correction["fit_sha256"] != digest(source_path):
            raise ValueError("geometry correction belongs to a different fit")
        artifacts.append(correction_path)
    code = [ROOT / name for name in NUMERICAL_DEPENDENCIES]
    code += [ROOT / "finite_set_alias_family.py", ROOT / "rough_smoke.py", bundle_path]
    if solver == "fisher-gn":
        code += [ROOT / "finite_set_bias_gn.py", ROOT / "gauss_newton.py"]
    snapshot = snapshot_files(artifacts + code + [__file__])
    bundle = load_module("grouped_bias_bundle", bundle_path)
    data = reconstruct_geometry(bundle.Data(bundle_directory), source)
    validate_geometry_receipt(data, source, correction)
    started = time.monotonic()
    fit = fit_models(data, source["fit"], fitter=fitter)
    assert_snapshot_unchanged(snapshot)
    receipt = {
        "schema": "finite-set-family-bias/v1",
        "solver": solver,
        "run_id": run_id,
        "unit_id": unit_id,
        "session_id": source["session_id"],
        "source_fit_sha256": digest(source_path),
        "source_hashes": snapshot,
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "eligible_for_cohort": False,
        "geometry": data.geometry_receipt,
        "fit": fit,
        "elapsed_s": time.monotonic() - started,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "limitations": (
            "Candidate bank conditional on persisted reviews; all families train the fit. "
            "No holdout. Constant-Hz bias is phenomenological, not an RF-scaled orbit model."
        ),
    }
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "fit.json"
    with output.open("x") as stream:
        json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
    return {"output": str(output), "sha256": digest(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    parser.add_argument("--solver", choices=("lbfgs", "fisher-gn"), default="lbfgs")
    arguments = parser.parse_args()
    print(json.dumps(run_case(arguments.unit_id, solver=arguments.solver)))
