"""Predeclared constant-width sensitivity from sealed timing-profile incumbents."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, build_likelihood_arms, digest, snapshot_files
from finite_set_tau_continue import (
    SOURCE_RUN,
    SUPPORTED_UNITS,
    expected_bound_input_hashes,
    validate_bound_input_hashes,
    validate_geometry_binding,
    validate_source_record,
)
from finite_set_tau_profile import profile_timing_offsets
from gauss_newton import refine_gauss_newton
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

RUN_ID = "finite-set-width82-v1"
SIGMA_HZ = 82.0


def fit_width_branches(
    data, source_fit, *, cavity_factory, profiler=profile_timing_offsets,
    refiner=refine_gauss_newton,
):
    full_bank = source_fit["full_bank"]
    trials, attempts = [], []
    options = dict(sigma_hz=SIGMA_HZ, tau_sigma_s=1.0, tau_bound_s=3.0,
                   slope_bound=50.0, budget_s=15.0)
    for source in source_fit["trials"]:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        likelihood = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
        initial = refiner(
            data, np.asarray(source["parameters"]).copy(), satellites,
            np.ones(len(satellites)), likelihood, **options,
        )
        if initial["objective"] > initial["initial_objective"] + 1e-6:
            raise ValueError("narrow-width refiner lost its starting incumbent")
        profile = profiler(
            data, initial["parameters"], satellites, likelihood.prepared,
            cavity_factory=cavity_factory, detection_probability=0.8 / len(full_bank),
            sigma_hz=SIGMA_HZ, clutter_rate=2.0, tau_sigma_s=1.0,
            tau_bound_s=3.0, step_s=0.05, budget_s=30.0,
        )
        if not np.isclose(profile["initial_objective"], initial["objective"], rtol=0, atol=1e-6):
            raise ValueError("profile does not reproduce narrow-width incumbent")
        final = refiner(
            data, np.asarray(profile["parameters"]).copy(), satellites,
            np.ones(len(satellites)), likelihood, **options,
        )
        if not np.isclose(final["initial_objective"], profile["objective"], rtol=0, atol=1e-6):
            raise ValueError("refiner does not reproduce narrow-width profile")
        if final["objective"] > profile["objective"] + 1e-6:
            raise ValueError("refiner lost profiled incumbent")
        use_final = final["objective"] < initial["objective"] or (
            final["objective"] == initial["objective"] and final["success"]
        )
        trials.append(copy.deepcopy(final if use_final else initial))
        attempts.append({"satellite_indices": satellites, "initial_refinement": initial,
                         "profile": profile, "final_refinement": final})
    selection = select_trials(trials)
    local_resolved = selection["selection_resolved"]
    complete = all(attempt["profile"]["complete"] for attempt in attempts)
    selection["selection_resolved"] = local_resolved and complete
    selection["success"] = selection["selection_resolved"]
    return {"full_bank": full_bank, "trials": trials, "attempts": attempts,
            "selection": selection, "local_refinements_resolved": local_resolved,
            "all_timing_profiles_complete": complete, "sigma_hz": SIGMA_HZ}


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_cavity import prepare_replacement_scorer
    from finite_set_grouped_cohort import EXPORT_SHA256, EXPORTS

    if unit_id not in SUPPORTED_UNITS:
        raise ValueError("unsupported pilot unit")
    directory = ROOT / "runs" / RUN_ID / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    source_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
    started = time.monotonic()
    snapshot = None
    try:
        source = validate_source_record(json.loads(source_path.read_text()), unit_id)
        assert_snapshot_unchanged(source["source_hashes"])
        _, data, inputs = load_unit_with_family_exports(
            unit_id, EXPORTS, expected_manifest_sha256=EXPORT_SHA256,
        )
        bound_inputs = validate_bound_input_hashes(inputs, expected_bound_input_hashes(source))
        geometry = validate_geometry_binding(source, data.geometry_receipt)
        snapshot = snapshot_files([
            *source["source_hashes"], source_path, __file__, ROOT / "finite_set_tau_continue.py",
        ])
        fitted = fit_width_branches(data, source["fit"], cavity_factory=prepare_replacement_scorer)
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / "failure.json").open("x") as stream:
            json.dump({"unit_id": unit_id, "error": str(error),
                       "error_type": type(error).__name__, "source_hashes": snapshot}, stream,
                      indent=2, allow_nan=False)
        raise
    result = {
        "schema": "finite-set-width-sensitivity/v1", "run_id": RUN_ID,
        "unit": source["unit"], "dataset": source["dataset"],
        "source_fit_sha256": digest(source_path), "source_hashes": snapshot,
        "bound_input_hashes": bound_inputs, "geometry_receipt": geometry,
        "reference_read_before_seal": False, "evaluation_written": False,
        "eligible_for_cohort": False, "fit": fitted,
        "elapsed_s": time.monotonic() - started, "sealed_utc": datetime.now(UTC).isoformat(),
        "scope": (
            "Predeclared 82 Hz constant-width sensitivity, not absolute orbit-error calibration. "
            "Same grouped data, banks, timing prior, RX bounds and detection/clutter model as v1. "
            "Refit, one 0.05 s timing-grid pass, then joint refinement. All data used for fitting. "
            "200 Hz objectives are not used for incumbent selection at the new width."
        ),
    }
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "fit.json"
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(output), "sha256": digest(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=SUPPORTED_UNITS)
    print(json.dumps(run_unit(parser.parse_args().unit_id)))
