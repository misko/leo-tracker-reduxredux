#!/usr/bin/env python3
"""Bounded same-bank GNv2 fits for the fixed two-width group mixture."""

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
from finite_set_rf_cohort import validate_source_record
from finite_set_tau_continue import (
    expected_bound_input_hashes,
    validate_bound_input_hashes,
    validate_geometry_binding,
)
from gauss_newton import refine_gauss_newton
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-tau-profile-v1"
RUN_ID = "finite-set-group-mixture-v1"
SCHEMA = "finite-set-group-mixture/v1"
INITIAL_UNITS = ("DS10-S01", "DS11-S02")
ALL_UNITS = tuple(
    f"{dataset}-S{index:02d}"
    for dataset in ("DS10", "DS11")
    for index in range(1, 17)
)
NARROW_SIGMA_HZ = 100.0
BROAD_SIGMA_HZ = 400.0
NARROW_WEIGHT = 0.8
SOURCE_SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
TAU_BOUND_S = 3.0
SLOPE_BOUND_HZ_S = 50.0
BUDGET_S_PER_BANK = 15.0
DIRECT_DEPENDENCIES = (
    "finite_set_group_mixture_run.py",
    "finite_set_group_mixture.py",
    "finite_set_rf_cohort.py",
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
    """Snapshot the adapter and every directly used validator before invocation."""

    return snapshotter(source_dependency_paths(source, source_path))


def _validate_bank(source_fit):
    full_bank = np.asarray(source_fit.get("full_bank"), dtype=int)
    trials = source_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(trials, list) or not trials:
        raise ValueError("source fit lacks its frozen bank ladder")
    banks = [tuple(trial.get("satellite_indices", ())) for trial in trials]
    if any(not bank for bank in banks) or len(set(banks)) != len(banks):
        raise ValueError("source banks are empty or duplicated")
    if tuple(full_bank) not in banks:
        raise ValueError("source bank ladder omits the frozen full bank")
    return full_bank, trials


def evaluate_frozen_objective(
    data,
    trial,
    likelihood,
    *,
    plan_factory=SharedPredictionPlan,
):
    """Evaluate one unchanged bank and parameter vector without fitting."""

    satellites = np.asarray(trial["satellite_indices"], dtype=int)
    parameters = np.asarray(trial["parameters"], dtype=float)
    weights = np.asarray(trial["satellite_weights"], dtype=float)
    if (
        parameters.shape != (6 + len(data.numbers),)
        or np.any(~np.isfinite(parameters))
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= len(data.numbers))
        or weights.shape != satellites.shape
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
    ):
        raise ValueError("source trial state is malformed")
    predicted, visible, _ = plan_factory(data, satellites).predict(parameters)
    shape = (len(data.times), len(satellites))
    predicted = np.asarray(predicted, dtype=float).reshape(shape)
    visible = np.asarray(visible, dtype=bool).reshape(shape)
    result = likelihood.evaluate(
        predicted,
        visible,
        sigma_hz=SOURCE_SIGMA_HZ,
        satellite_weights=weights,
        background_mass=0.2,
    )
    tau = parameters[6 + satellites]
    tau_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    objective = -float(result["total_log_likelihood"]) + tau_prior
    if not np.isfinite(objective):
        raise FloatingPointError("frozen objective must be finite")
    return {
        "objective": objective,
        "total_log_likelihood": float(result["total_log_likelihood"]),
        "tau_prior": tau_prior,
        "groups": len(result["group_values"]),
    }


def fit_group_mixture_branches(
    data,
    source_fit,
    *,
    refiner=refine_gauss_newton,
    adapter_factory=GroupMixtureLikelihoodAdapter,
    plan_factory=SharedPredictionPlan,
):
    """Run one direct mixture-GN continuation for every unchanged source bank."""

    full_bank, source_trials = _validate_bank(source_fit)
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        ordinary = build_likelihood_arms(
            data, len(satellites), len(full_bank)
        )["finite_set"]
        baseline = evaluate_frozen_objective(
            data,
            source,
            ordinary,
            plan_factory=plan_factory,
        )
        if not np.isclose(baseline["objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("ordinary 200 Hz evaluation does not reproduce sealed source")
        mixture = adapter_factory(
            ordinary.prepared,
            ordinary.detection_probability,
            clutter_rate=ordinary.clutter_rate,
            narrow_sigma_hz=NARROW_SIGMA_HZ,
            broad_sigma_hz=BROAD_SIGMA_HZ,
            narrow_weight=NARROW_WEIGHT,
        )
        mixture_initial = evaluate_frozen_objective(
            data,
            source,
            mixture,
            plan_factory=plan_factory,
        )
        candidate = refiner(
            data,
            np.asarray(source["parameters"], dtype=float).copy(),
            satellites,
            np.asarray(source["satellite_weights"], dtype=float),
            mixture,
            sigma_hz=SOURCE_SIGMA_HZ,
            tau_sigma_s=TAU_SIGMA_S,
            tau_bound_s=TAU_BOUND_S,
            slope_bound=SLOPE_BOUND_HZ_S,
            budget_s=BUDGET_S_PER_BANK,
        )
        if not np.isclose(
            candidate["initial_objective"], mixture_initial["objective"], rtol=0, atol=1e-6
        ):
            raise ValueError("mixture GN seed does not reproduce the mixture objective")
        if candidate["objective"] > mixture_initial["objective"] + 1e-6:
            raise ValueError("mixture GN lost its own initial incumbent")
        if not np.array_equal(candidate["satellite_indices"], satellites):
            raise ValueError("mixture GN changed the frozen satellite bank")
        if not np.isclose(
            candidate["entry_penalty"], source["entry_penalty"], rtol=0, atol=1e-9
        ):
            raise ValueError("group mixture changed the unchanged source-bank penalty")
        trial = copy.deepcopy(candidate)
        trial.update(
            source_timing_profile_objective=float(source["objective"]),
            source_timing_profile_success=bool(source.get("success")),
            source_convergence_not_inherited=True,
            ordinary_200hz_source_reproduced=True,
            group_mixture_initial_objective=float(mixture_initial["objective"]),
            no_timing_profile_performed=True,
        )
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_success": bool(source.get("success")),
                "source_status": source.get("status"),
                "ordinary_200hz_source_objective": baseline["objective"],
                "ordinary_200hz_source_objective_delta": float(
                    baseline["objective"] - source["objective"]
                ),
                "group_mixture_initial_objective": mixture_initial["objective"],
                "group_mixture_gn": candidate,
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
        "budget_s_per_bank": BUDGET_S_PER_BANK,
        "source_sigma_hz": SOURCE_SIGMA_HZ,
        "narrow_sigma_hz": NARROW_SIGMA_HZ,
        "broad_sigma_hz": BROAD_SIGMA_HZ,
        "narrow_weight": NARROW_WEIGHT,
        "tau_sigma_s": TAU_SIGMA_S,
        "tau_bound_s": TAU_BOUND_S,
        "slope_bound_hz_s": SLOPE_BOUND_HZ_S,
        "new_parameter_count": 0,
        "scope": (
            "Direct 15-second complete-data/Fisher GNv2 from every unchanged no-RF timing-"
            "profile bank under a fixed 100/400 Hz group-latent width mixture with 0.8/0.2 "
            "weights. Ordinary 200 Hz likelihood is evaluated only to reproduce the sealed "
            "source. The mixture objective is independently evaluated and is the sole new-model "
            "incumbent. No timing profile, new parameter, bank change, penalty change, reference, "
            "or evaluation artifact is used."
        ),
    }


def run_unit(unit_id, *, allow_all_32=False):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_grouped_cohort import EXPORT_SHA256, EXPORTS

    allowed = ALL_UNITS if allow_all_32 else INITIAL_UNITS
    if unit_id not in allowed:
        raise ValueError(f"unit_id must be one of {allowed}")
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
        bound_inputs = validate_bound_input_hashes(
            input_paths,
            expected_bound_input_hashes(source),
        )
        geometry = validate_geometry_binding(source, data.geometry_receipt)
        fitted = fit_group_mixture_branches(data, source["fit"])
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
        "eligible_for_cohort": bool(allow_all_32),
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
    parser.add_argument("unit_id", choices=ALL_UNITS)
    parser.add_argument("--allow-all-32", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id, allow_all_32=arguments.allow_all_32)))


__all__ = [
    "evaluate_frozen_objective",
    "fit_group_mixture_branches",
    "run_unit",
    "snapshot_before_source_validation",
    "source_dependency_paths",
]
