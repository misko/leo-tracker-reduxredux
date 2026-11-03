"""Bounded same-bank timing-profile branches from uniform grouped cohort fits."""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import UTC, datetime

import numpy as np
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_tau_profile import profile_timing_offsets
from gauss_newton import refine_gauss_newton
from rough_smoke import serializable
from selection import ROOT
from staged_fit import select_trials

SOURCE_RUN = "finite-set-grouped-cohort-v1"
RUN_ID = "finite-set-tau-profile-v1"


def fit_profile_branches(
    data, source_fit, *, cavity_factory, profiler=profile_timing_offsets,
    refiner=refine_gauss_newton,
):
    full_bank = source_fit["full_bank"]
    trials = []
    attempts = []
    for source in source_fit["trials"]:
        satellites = np.asarray(source["satellite_indices"], dtype=int)
        likelihood = build_likelihood_arms(data, len(satellites), len(full_bank))["finite_set"]
        profile = profiler(
            data, source["parameters"], satellites, likelihood.prepared,
            cavity_factory=cavity_factory, detection_probability=0.8 / len(full_bank),
            sigma_hz=200.0, clutter_rate=2.0, tau_sigma_s=1.0, tau_bound_s=3.0,
            step_s=0.1, budget_s=20.0,
        )
        if not np.isclose(profile["initial_objective"], source["objective"], rtol=0, atol=1e-6):
            raise ValueError("profile seed does not reproduce sealed source")
        candidate = refiner(
            data, np.asarray(profile["parameters"]).copy(), satellites,
            np.ones(len(satellites)), likelihood,
            sigma_hz=200.0, tau_sigma_s=1.0, tau_bound_s=3.0, slope_bound=50.0, budget_s=15.0,
        )
        if not np.isclose(
            candidate["initial_objective"], profile["objective"], rtol=0, atol=1e-6,
        ):
            raise ValueError("local refinement does not reproduce profiled seed")
        if candidate["objective"] > profile["objective"] + 1e-6:
            raise ValueError("local refinement lost its profiled incumbent")
        use_candidate = candidate["objective"] < source["objective"] or (
            candidate["objective"] == source["objective"]
            and candidate["success"] and not source["success"]
        )
        trials.append(copy.deepcopy(candidate if use_candidate else source))
        attempts.append({
            "satellite_indices": satellites, "satellite_count": len(satellites),
            "profile": profile, "local_refinement": candidate,
            "source_objective": source["objective"],
            "selected_branch": "profile_then_refine" if use_candidate else "sealed_incumbent",
        })
    selection = select_trials(trials)
    local_resolved = selection["selection_resolved"]
    profiles_complete = all(attempt["profile"]["complete"] for attempt in attempts)
    selection["selection_resolved"] = local_resolved and profiles_complete
    selection["success"] = selection["selection_resolved"]
    return {
        "full_bank": full_bank, "trials": trials, "attempts": attempts,
        "selection": selection, "local_refinements_resolved": local_resolved,
        "all_timing_profiles_complete": profiles_complete,
        "scope": (
            "One sequential timing-coordinate grid pass, followed by joint GN, per same bank. "
            "Incumbents retained by objective only. Fixed priors, widths, masses and bank ladder. "
            "No reference or previously better pilot parameters used for initialization. "
            "A complete grid pass is not proof of a global optimum."
        ),
    }


def run_unit(unit_id):
    from alias_family_joint import load_unit_with_family_exports
    from finite_set_cavity import prepare_replacement_scorer
    from finite_set_grouped_cohort import EXPORT_SHA256, EXPORTS

    directory = ROOT / "runs" / RUN_ID / unit_id
    if directory.exists():
        raise FileExistsError(directory)
    source_path = ROOT / "runs" / SOURCE_RUN / unit_id / "fit.json"
    source = json.loads(source_path.read_text())
    if (
        source.get("schema") != "finite-set-grouped-cohort/v1"
        or source["unit"]["unit_id"] != unit_id
        or source.get("reference_read_before_seal") is not False
        or source.get("evaluation_written") is not False
        or not source.get("sealed_utc")
    ):
        raise ValueError("source must be a sealed truth-free grouped cohort fit")
    _, data, inputs = load_unit_with_family_exports(
        unit_id, EXPORTS, expected_manifest_sha256=EXPORT_SHA256,
    )
    if data.geometry_receipt["fitted_array_sha256"] != source["fit"]["grouped_geometry"][
        "fitted_array_sha256"
    ]:
        raise ValueError("profile geometry differs from sealed source")
    dependency_names = (
        "finite_set_tau_profile.py", "finite_set_cavity.py", "finite_set_fit.py",
        "finite_set_likelihood.py", "gauss_newton.py", "prediction_plan.py",
        "prediction_jacobian.py", "joint_inputs.py", "staged_fit.py", "rough_smoke.py",
        "alias_family_joint.py", "finite_set_grouped_cohort.py", "track_likelihood.py",
        "grouped_likelihood.py",
    )
    paths = [*inputs, source_path, __file__, *[ROOT / name for name in dependency_names]]
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    snapshot = snapshot_files(paths)
    started = time.monotonic()
    try:
        fitted = fit_profile_branches(
            data, source["fit"], cavity_factory=prepare_replacement_scorer
        )
        assert_snapshot_unchanged(snapshot)
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / "failure.json").open("x") as stream:
            json.dump({"unit_id": unit_id, "error": str(error),
                       "error_type": type(error).__name__, "source_hashes": snapshot},
                      stream, indent=2)
        raise
    result = {
        "schema": "finite-set-tau-profile/v1", "run_id": RUN_ID,
        "unit": source["unit"], "dataset": source["dataset"],
        "source_fit_sha256": digest(source_path), "source_hashes": snapshot,
        "reference_read_before_seal": False, "evaluation_written": False,
        "eligible_for_cohort": False, "fit": fitted,
        "elapsed_s": time.monotonic() - started, "sealed_utc": datetime.now(UTC).isoformat(),
    }
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / "fit.json"
    with output.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"unit_id": unit_id, "output": str(output), "sha256": digest(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", choices=("DS10-S01", "DS11-S02"))
    arguments = parser.parse_args()
    print(json.dumps(run_unit(arguments.unit_id)))
