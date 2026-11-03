#!/usr/bin/env python3
"""Continue every sealed group-mixture bank with one bounded GNv2 pass."""

from __future__ import annotations

import argparse
import copy
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
from finite_set_group_mixture import GroupMixtureLikelihoodAdapter
from finite_set_tau_continue import (
    expected_bound_input_hashes,
    validate_bound_input_hashes,
)
from gauss_newton import refine_gauss_newton
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-group-mixture-v1"
RUN_ID = "finite-set-group-mixture-continue-v1"
SOURCE_SCHEMA = "finite-set-group-mixture/v1"
SCHEMA = "finite-set-group-mixture-continue/v1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
NARROW_SIGMA_HZ = 100.0
BROAD_SIGMA_HZ = 400.0
NARROW_WEIGHT = 0.8
OPTIMIZER_SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
SLOPE_BOUND_HZ_S = 50.0
BUDGET_S_PER_BANK = 20.0
FROZEN_ADAPTER_SHA256 = (
    "930d5426f6e756dcc0dd1d9d880bbfc53a1847b15feb6ed268c1203971afe225"
)
DIRECT_DEPENDENCIES = (
    "finite_set_group_mixture_continue.py",
    "finite_set_group_mixture.py",
    "finite_set_tau_continue.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "gauss_newton.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "staged_fit.py",
    "rough_smoke.py",
    "selection.py",
    "alias_family_joint.py",
    "finite_set_grouped_cohort.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
)


def _unique_paths(paths):
    return list(dict.fromkeys(str(Path(path).resolve()) for path in paths))


def source_dependency_paths(source, source_path):
    inherited = source.get("source_hashes")
    if not isinstance(inherited, dict) or not inherited:
        raise ValueError("source lacks inherited hashes")
    paths = [*inherited, source_path]
    paths.extend(ROOT / name for name in DIRECT_DEPENDENCIES)
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return _unique_paths(paths)


def snapshot_before_source_validation(source, source_path, *, snapshotter=snapshot_files):
    """Snapshot every inherited and directly used dependency before validation."""

    return snapshotter(source_dependency_paths(source, source_path))


def _validate_model_contract(fit):
    expected = {
        "source_sigma_hz": OPTIMIZER_SIGMA_HZ,
        "narrow_sigma_hz": NARROW_SIGMA_HZ,
        "broad_sigma_hz": BROAD_SIGMA_HZ,
        "narrow_weight": NARROW_WEIGHT,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "new_parameter_count": 0,
    }
    for name, value in expected.items():
        if not np.isclose(fit.get(name, np.nan), value, rtol=0, atol=0):
            raise ValueError(f"source mixture changed frozen model field {name}")
    if fit.get("source_bank_order_preserved") is not True:
        raise ValueError("source mixture did not preserve its bank order")


def validate_source_record(source, unit_id):
    """Require a sealed truth-free v1 group-mixture source and complete bank ladder."""

    if (
        source.get("schema") != SOURCE_SCHEMA
        or source.get("run_id") != SOURCE_RUN
        or source.get("source_run_id") != "finite-set-tau-profile-v1"
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("unit", {}).get("size") != 1
        or source.get("dataset") != unit_id[:4]
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("sealed") is not True
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free single group-mixture fit")
    hashes = source.get("source_hashes")
    if not isinstance(hashes, dict) or not hashes or any(
        not isinstance(path, str) or not isinstance(value, str) or len(value) != 64
        for path, value in hashes.items()
    ):
        raise ValueError("source inherited hashes are malformed")
    adapter_path = str((ROOT / "finite_set_group_mixture.py").resolve())
    if hashes.get(adapter_path) != FROZEN_ADAPTER_SHA256:
        raise ValueError("source does not bind the frozen group-mixture adapter")
    source_fit_sha256 = source.get("source_fit_sha256")
    upstream_path = str(
        (ROOT / "runs" / "finite-set-tau-profile-v1" / unit_id / "fit.json").resolve()
    )
    if (
        not isinstance(source_fit_sha256, str)
        or len(source_fit_sha256) != 64
        or hashes.get(upstream_path) != source_fit_sha256
    ):
        raise ValueError("source timing-profile digest is not inherited exactly")
    fit = source.get("fit")
    if not isinstance(fit, dict):
        raise ValueError("source lacks group-mixture fit")
    _validate_model_contract(fit)
    full_bank = fit.get("full_bank")
    trials = fit.get("trials")
    attempts = fit.get("attempts")
    if (
        not isinstance(full_bank, list)
        or not full_bank
        or not isinstance(trials, list)
        or not trials
        or not isinstance(attempts, list)
        or len(attempts) != len(trials)
        or fit.get("source_trial_count") != len(trials)
    ):
        raise ValueError("source group-mixture bank ladder is incomplete")
    banks = []
    for trial, attempt in zip(trials, attempts, strict=True):
        bank = trial.get("satellite_indices")
        parameters = np.asarray(trial.get("parameters"), dtype=float)
        weights = np.asarray(trial.get("satellite_weights"), dtype=float)
        if (
            not isinstance(bank, list)
            or not bank
            or len(set(bank)) != len(bank)
            or parameters.ndim != 1
            or np.any(~np.isfinite(parameters))
            or weights.shape != (len(bank),)
            or np.any(~np.isfinite(weights))
            or np.any(weights <= 0)
            or not np.isfinite(trial.get("objective", np.nan))
            or not np.isfinite(trial.get("entry_penalty", np.nan))
            or trial.get("algorithm_version") != "complete-data-fisher-gn/v2"
            or attempt.get("satellite_indices") != bank
            or attempt.get("timing_profile_performed") is not False
        ):
            raise ValueError("source group-mixture trial is malformed")
        banks.append(tuple(bank))
    if len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("source banks are duplicated or omit the full bank")
    return source


def validate_reconstructed_source(
    source,
    data,
    input_paths,
    *,
    expected_factory=expected_bound_input_hashes,
    input_validator=validate_bound_input_hashes,
):
    """Require exact loader inputs and the complete sealed geometry receipt."""

    expected = expected_factory(source)
    if source.get("bound_input_hashes") != expected:
        raise ValueError("source bound inputs differ from inherited input hashes")
    bound_inputs = input_validator(input_paths, expected)
    geometry = serializable(data.geometry_receipt)
    if geometry != source.get("geometry_receipt"):
        raise ValueError("reconstructed full geometry differs from sealed source")
    return bound_inputs, geometry


def _same_state(left, right):
    return np.array_equal(left["parameters"], right["parameters"])


def continue_group_mixture_branches(
    data,
    source_fit,
    *,
    refiner=refine_gauss_newton,
    adapter_factory=GroupMixtureLikelihoodAdapter,
):
    """Run one additional bounded GN pass from every sealed mixture bank."""

    _validate_model_contract(source_fit)
    full_bank = np.asarray(source_fit.get("full_bank"), dtype=int)
    source_trials = source_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("source mixture fit lacks its bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(banks)) != len(banks) or tuple(full_bank) not in banks:
        raise ValueError("source banks are empty, duplicated, or omit the full bank")
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        parameters = np.asarray(source["parameters"], dtype=float)
        support = np.asarray(source["satellite_weights"], dtype=float)
        if (
            parameters.shape != (6 + len(data.numbers),)
            or np.any(~np.isfinite(parameters))
            or satellites.ndim != 1
            or not len(satellites)
            or len(np.unique(satellites)) != len(satellites)
            or np.any(satellites < 0)
            or np.any(satellites >= len(data.numbers))
            or support.shape != satellites.shape
            or np.any(~np.isfinite(support))
            or np.any(support <= 0)
        ):
            raise ValueError("source mixture trial state is malformed")
        ordinary = build_likelihood_arms(
            data, len(satellites), len(full_bank)
        )["finite_set"]
        mixture = adapter_factory(
            ordinary.prepared,
            ordinary.detection_probability,
            clutter_rate=ordinary.clutter_rate,
            narrow_sigma_hz=NARROW_SIGMA_HZ,
            broad_sigma_hz=BROAD_SIGMA_HZ,
            narrow_weight=NARROW_WEIGHT,
        )
        candidate = refiner(
            data,
            parameters.copy(),
            satellites,
            support.copy(),
            mixture,
            sigma_hz=OPTIMIZER_SIGMA_HZ,
            tau_sigma_s=TAU_SIGMA_S,
            tau_bound_s=TAU_BOUND_S,
            slope_bound=SLOPE_BOUND_HZ_S,
            budget_s=BUDGET_S_PER_BANK,
        )
        if not np.isclose(
            candidate["initial_objective"], source["objective"], rtol=0, atol=1e-6
        ):
            raise ValueError("continued GN does not reproduce its sealed mixture source")
        if candidate["objective"] > source["objective"] + 1e-6:
            raise ValueError("continued GN lost its sealed source incumbent")
        if not np.array_equal(candidate["satellite_indices"], satellites):
            raise ValueError("continued GN changed the frozen satellite bank")
        if not np.isclose(
            candidate["entry_penalty"], source["entry_penalty"], rtol=0, atol=1e-9
        ):
            raise ValueError("continued GN changed the frozen bank penalty")
        use_candidate = candidate["objective"] < source["objective"] - 1e-7 or (
            np.isclose(candidate["objective"], source["objective"], rtol=0, atol=1e-7)
            and candidate.get("success") is True
            and source.get("success") is not True
        )
        trial = copy.deepcopy(candidate if use_candidate else source)
        changed = not _same_state(trial, source)
        trial.update(
            source_group_mixture_objective=float(source["objective"]),
            source_group_mixture_success=bool(source.get("success")),
            source_incumbent_preserved=True,
            selected_branch="continued_gn" if use_candidate else "sealed_source",
            selected_state_changed_from_source=changed,
            convergence_provenance=(
                "candidate_terminal_state" if use_candidate else "sealed_source_unchanged"
            ),
            no_timing_profile_performed=True,
        )
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_objective": float(source["objective"]),
                "source_success": bool(source.get("success")),
                "source_status": source.get("status"),
                "continued_gn": candidate,
                "selected_branch": trial["selected_branch"],
                "selected_state_changed_from_source": changed,
                "budget_s": BUDGET_S_PER_BANK,
                "timing_profile_performed": False,
            }
        )
    return {
        "full_bank": full_bank,
        "trials": trials,
        "attempts": attempts,
        "selection": select_trials(trials),
        "source_bank_order_preserved": True,
        "source_trial_count": len(source_trials),
        "continuation_passes": 1,
        "budget_s_per_bank": BUDGET_S_PER_BANK,
        "source_sigma_hz": OPTIMIZER_SIGMA_HZ,
        "narrow_sigma_hz": NARROW_SIGMA_HZ,
        "broad_sigma_hz": BROAD_SIGMA_HZ,
        "narrow_weight": NARROW_WEIGHT,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "new_parameter_count": 0,
        "scope": (
            "Exactly one additional 20-second complete-data/Fisher GNv2 pass from every "
            "sealed group-mixture bank under the unchanged fixed 100/400 Hz group-latent "
            "mixture. Each sealed source remains an incumbent; convergence is taken from the "
            "selected state. No timing profile, model change, bank change, penalty change, "
            "reference, or evaluation artifact is used."
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
    source_snapshot = None
    try:
        source = json.loads(source_path.read_text())
        source_snapshot = snapshot_before_source_validation(source, source_path)
        source = validate_source_record(source, unit_id)
        assert_snapshot_unchanged(source["source_hashes"])
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            EXPORTS,
            expected_manifest_sha256=EXPORT_SHA256,
        )
        bound_inputs, geometry = validate_reconstructed_source(
            source, data, input_paths
        )
        fitted = continue_group_mixture_branches(data, source["fit"])
        assert_snapshot_unchanged(source_snapshot)
    except Exception as error:
        output.mkdir(parents=True, exist_ok=False)
        failure = {
            "schema": SCHEMA,
            "run_id": RUN_ID,
            "unit_id": unit_id,
            "error_type": type(error).__name__,
            "error": str(error),
            "elapsed_s": time.monotonic() - started,
            "source_hashes": source_snapshot,
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
        "source_hashes": source_snapshot,
        "inherited_source_hashes": source["source_hashes"],
        "bound_input_hashes": bound_inputs,
        "geometry_receipt": geometry,
        "limits": {"budget_s_per_bank": BUDGET_S_PER_BANK, "numerical_threads": 1},
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
    "continue_group_mixture_branches",
    "run_unit",
    "snapshot_before_source_validation",
    "source_dependency_paths",
    "validate_reconstructed_source",
    "validate_source_record",
]
