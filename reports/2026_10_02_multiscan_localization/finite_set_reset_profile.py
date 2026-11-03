"""One timing-profile continuation of sealed grouped finite-set reset fits."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from capture_reset_gn import apply_capture_offsets, refine_capture_reset_gauss_newton
from finite_set_capture_reset import validate_group_capture_rx
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_tau_profile import profile_timing_offsets
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-capture-reset-v1"
RUN_ID = "finite-set-reset-profile-v1"
SCHEMA = "finite-set-reset-profile/v1"
SUPPORTED_UNITS = ("DS10-D01", "DS11-D01")
NEW_DEPENDENCIES = ("finite_set_tau_profile.py", "finite_set_cavity.py")


class FixedResetPredictor:
    """Cache shared plans and add fixed capture offsets after row expansion."""

    def __init__(self, data, capture_jumps_hz, *, plan_factory=SharedPredictionPlan):
        self.data = data
        self.capture_jumps_hz = np.asarray(capture_jumps_hz, dtype=float).copy()
        self.plan_factory = plan_factory
        self.plans = {}
        self.plan_build_count = 0

    def __call__(self, data, parameters, satellites):
        if data is not self.data:
            raise ValueError("fixed-reset predictor received different data")
        satellites = np.asarray(satellites, dtype=int)
        key = tuple(int(value) for value in satellites)
        if key not in self.plans:
            self.plans[key] = self.plan_factory(data, satellites)
            self.plan_build_count += 1
        predicted, visible, _ = self.plans[key].predict(parameters)
        shape = (len(data.times), len(satellites))
        predicted = apply_capture_offsets(
            data,
            np.asarray(predicted).reshape(shape),
            self.capture_jumps_hz,
            len(satellites),
        )
        return predicted, np.asarray(visible).reshape(shape)


def _same_state(left, right):
    return np.array_equal(left["parameters"], right["parameters"]) and np.array_equal(
        left["capture_jumps_hz"], right["capture_jumps_hz"]
    )


def fit_reset_profile_branches(
    data,
    source_fit,
    *,
    cavity_factory,
    profiler=profile_timing_offsets,
    refiner=refine_capture_reset_gauss_newton,
):
    """Run one bounded tau profile and one reset-aware GN for each source bank."""

    geometry = validate_group_capture_rx(data)
    full_bank = np.asarray(source_fit.get("full_bank"), dtype=int)
    source_trials = source_fit.get("trials")
    if full_bank.ndim != 1 or not len(full_bank) or not isinstance(source_trials, list):
        raise ValueError("source reset fit lacks its bank ladder")
    source_banks = [tuple(trial.get("satellite_indices", ())) for trial in source_trials]
    if not source_trials or len(set(source_banks)) != len(source_banks):
        raise ValueError("source reset banks must be nonempty and distinct")
    if tuple(full_bank) not in source_banks:
        raise ValueError("source reset ladder omits its full bank")
    trials = []
    attempts = []
    for source in source_trials:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        parameters = np.asarray(source["parameters"], dtype=float)
        jumps = np.asarray(source["capture_jumps_hz"], dtype=float)
        if (
            satellites.ndim != 1
            or not len(satellites)
            or len(np.unique(satellites)) != len(satellites)
            or np.any(satellites < 0)
            or np.any(satellites >= len(data.numbers))
        ):
            raise ValueError("source reset trial has an invalid candidate bank")
        support = np.ones(len(satellites))
        likelihood = build_likelihood_arms(
            data,
            len(satellites),
            len(full_bank),
        )["finite_set"]
        predictor = FixedResetPredictor(data, jumps)
        profile = profiler(
            data,
            parameters,
            satellites,
            likelihood.prepared,
            cavity_factory=cavity_factory,
            detection_probability=0.8 / len(full_bank),
            sigma_hz=200.0,
            clutter_rate=2.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            step_s=0.1,
            budget_s=30.0,
            predictor=predictor,
        )
        if not np.isclose(profile["initial_objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("reset timing profile does not reproduce its sealed source")
        candidate = refiner(
            data,
            np.asarray(profile["parameters"], dtype=float).copy(),
            jumps.copy(),
            satellites,
            support,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            slope_bound_hz_s=50.0,
            budget_s=15.0,
        )
        if not np.isclose(candidate["initial_objective"], profile["objective"], rtol=0, atol=1e-6):
            raise ValueError("reset GN does not reproduce its profiled initializer")
        if candidate["objective"] > profile["objective"] + 1e-6:
            raise ValueError("reset GN lost its profiled incumbent")
        source_penalty = source.get("model_penalty", {}).get("total_penalty")
        candidate_penalty = candidate.get("model_penalty", {}).get("total_penalty")
        if not np.isclose(candidate_penalty, source_penalty, rtol=0, atol=1e-9):
            raise ValueError("reset timing continuation changed the model penalty")
        use_candidate = candidate["objective"] < source["objective"] - 1e-7 or (
            np.isclose(candidate["objective"], source["objective"], rtol=0, atol=1e-7)
            and candidate.get("success") is True
            and source.get("success") is not True
        )
        trial = copy.deepcopy(candidate if use_candidate else source)
        changed = not _same_state(trial, source)
        trial["source_reset_objective"] = float(source["objective"])
        trial["selected_branch"] = "profile_then_reset_gn" if use_candidate else "sealed_source"
        trial["selected_state_changed_from_source"] = changed
        trial["convergence_provenance"] = (
            "candidate_terminal_state" if use_candidate else "sealed_source_unchanged"
        )
        trials.append(trial)
        attempts.append(
            {
                "satellite_indices": satellites,
                "satellite_count": len(satellites),
                "source_objective": float(source["objective"]),
                "source_success": bool(source.get("success")),
                "gn_support_policy": "uniform_ones_finite_set_adapter_ignores_optimizer_weights",
                "profile": profile,
                "reset_gn": candidate,
                "selected_branch": trial["selected_branch"],
                "predictor_plan_build_count": predictor.plan_build_count,
                "fixed_capture_jumps_during_profile": jumps.copy(),
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
        "group_capture_rx_validation": geometry,
        "capture_count": geometry["capture_count"],
        "parent_bank_order_preserved": True,
        "profile_passes": 1,
        "profile_budget_s_per_bank": 30.0,
        "gn_budget_s_per_bank": 15.0,
        "sigma_hz": 200.0,
        "tau_sigma_s": 1.0,
        "tau_bound_s": 3.0,
        "slope_bound_hz_s": 50.0,
        "scope": (
            "Exactly one bounded sequential tau profile with source capture jumps fixed, followed "
            "by one reset-aware GN per unchanged source bank. Incomplete profiles remain explicit; "
            "no recursive completion, reference access, or changed-state convergence inheritance."
        ),
    }


def validate_source_binding(source, unit_id, data, input_paths):
    """Validate sealed reset source hashes, inputs, geometry, and unit identity."""

    if (
        source.get("schema") != "finite-set-capture-reset/v1"
        or source.get("run_id") != SOURCE_RUN
        or source.get("unit", {}).get("unit_id") != unit_id
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or source.get("sealed") is not True
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free reset fit")
    source_hashes = source.get("source_hashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError("source reset fit lacks file hashes")
    assert_snapshot_unchanged(source_hashes)
    actual_inputs = snapshot_files(input_paths)
    if actual_inputs != source.get("bound_input_hashes"):
        raise ValueError("reconstructed inputs differ from sealed reset source")
    geometry = serializable(data.geometry_receipt)
    if geometry != source.get("geometry_receipt"):
        raise ValueError("reconstructed geometry differs from sealed reset source")
    validation = validate_group_capture_rx(data)
    if tuple(data.child_sessions) != tuple(source["unit"]["session_ids"]) or validation[
        "capture_count"
    ] != source["fit"].get("capture_count"):
        raise ValueError("source reset capture lineage differs from reconstructed data")
    return {
        "source_hashes": dict(source_hashes),
        "bound_input_hashes": actual_inputs,
        "geometry_receipt": geometry,
        "group_capture_rx_validation": validation,
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
        exports = ROOT / "runs" / "alias-family-cohort-v1"
        manifest_path = exports / "manifest.json"
        expected_manifest = source.get("bound_input_hashes", {}).get(str(manifest_path.resolve()))
        if expected_manifest is None:
            raise ValueError("source reset fit does not bind the alias-family manifest")
        _, data, input_paths = load_unit_with_family_exports(
            unit_id,
            exports,
            expected_manifest_sha256=expected_manifest,
        )
        binding = validate_source_binding(source, unit_id, data, input_paths)
        paths = list(binding["source_hashes"])
        paths.extend([source_path, Path(__file__)])
        paths.extend(ROOT / name for name in NEW_DEPENDENCIES)
        paths = list(dict.fromkeys(str(Path(path).resolve()) for path in paths))
        snapshot = snapshot_files(paths)
        fitted = fit_reset_profile_branches(
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
        "bound_input_hashes": binding["bound_input_hashes"],
        "geometry_receipt": binding["geometry_receipt"],
        "limits": {
            "profile_budget_s_per_bank": 30.0,
            "gn_budget_s_per_bank": 15.0,
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
    "FixedResetPredictor",
    "fit_reset_profile_branches",
    "run_unit",
    "validate_source_binding",
]
