#!/usr/bin/env python3
"""Exact same-K grouped finite-set identity screens for two sealed pilots."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from finite_set_cavity import prepare_replacement_scorer
from finite_set_fit import (
    assert_snapshot_unchanged,
    build_likelihood_arms,
    digest,
    snapshot_files,
)
from finite_set_rf_score import _selected_trial, validate_authoritative_bindings
from prediction_plan import SharedPredictionPlan
from rough_smoke import serializable
from selection import ROOT

SOURCE_RUN = "finite-set-tau-profile-v1"
SCHEMA = "finite-set-identity-screen/v1"
SUPPORTED_UNITS = ("DS10-S01", "DS11-S02")
DEFAULT_PROFILE_ROOT = ROOT / "runs" / SOURCE_RUN
DEFAULT_GROUPED_ROOT = ROOT / "runs" / "finite-set-grouped-cohort-v1"
DEFAULT_EXPORTS = ROOT / "runs" / "alias-family-cohort-v1"
DEFAULT_OUTPUT = ROOT / "finite-set-identity-screen-v1.json"
EXPORT_SHA256 = "8752be16157de6c04e7242e6178d2e9e74725ec3c5eb279e9cbc3eefc43b34b1"
SIGMA_HZ = 200.0
TAU_SIGMA_S = 1.0
MAX_BUDGET_S_PER_UNIT = 60.0
DIRECT_DEPENDENCIES = (
    "finite_set_identity_screen.py",
    "finite_set_cavity.py",
    "finite_set_rf_score.py",
    "finite_set_fit.py",
    "finite_set_likelihood.py",
    "prediction_plan.py",
    "prediction_jacobian.py",
    "joint_inputs.py",
    "alias_family_joint.py",
    "finite_set_grouped_cohort.py",
    "grouped_likelihood.py",
    "track_likelihood.py",
    "rough_smoke.py",
    "selection.py",
)


def _unique_paths(paths):
    return list(dict.fromkeys(str(Path(path).resolve()) for path in paths))


def source_dependency_paths(profile, profile_path, grouped_path):
    authoritative = profile.get("source_hashes")
    if not isinstance(authoritative, dict) or not authoritative:
        raise ValueError("profile receipt lacks authoritative source hashes")
    if any(
        not isinstance(path, str) or not isinstance(value, str) or len(value) != 64
        for path, value in authoritative.items()
    ):
        raise ValueError("profile authoritative source hashes are malformed")
    paths = [*authoritative, profile_path, grouped_path]
    paths.extend(ROOT / name for name in DIRECT_DEPENDENCIES)
    paths.append(ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py")
    return _unique_paths(paths)


def snapshot_before_validation(
    profile, profile_path, grouped_path, *, snapshotter=snapshot_files
):
    return snapshotter(source_dependency_paths(profile, profile_path, grouped_path))


def _predict(plan_factory, data, satellites, parameters):
    predicted, visible, _ = plan_factory(data, satellites).predict(parameters)
    shape = (len(data.times), len(satellites))
    return (
        np.asarray(predicted, dtype=float).reshape(shape),
        np.asarray(visible, dtype=bool).reshape(shape),
    )


def _evaluate(evaluator, predicted, visible, weights):
    return evaluator.evaluate(
        predicted,
        visible,
        sigma_hz=SIGMA_HZ,
        satellite_weights=weights,
        background_mass=0.2,
    )


def _support_label(visible_group_count, row_posterior_support):
    if visible_group_count == 0:
        return "invisible_all_groups"
    if row_posterior_support == 0:
        return "exact_zero_row_posterior_support"
    return "positive_row_posterior_support"


def screen_identity_replacements(
    data,
    trial,
    full_bank,
    *,
    budget_s=MAX_BUDGET_S_PER_UNIT,
    clock=time.monotonic,
    arms_factory=build_likelihood_arms,
    plan_factory=SharedPredictionPlan,
    cavity_factory=prepare_replacement_scorer,
):
    """Screen all selected-slot/unused-candidate swaps at frozen source state."""

    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_BUDGET_S_PER_UNIT:
        raise ValueError("budget_s must lie in (0, 60]")
    started = clock()
    deadline = started + float(budget_s)
    satellites = np.asarray(trial.get("satellite_indices"), dtype=int)
    parameters = np.asarray(trial.get("parameters"), dtype=float)
    weights = np.asarray(trial.get("satellite_weights"), dtype=float)
    full_bank = np.asarray(full_bank, dtype=int)
    candidate_count = len(data.numbers)
    if (
        parameters.shape != (6 + candidate_count,)
        or np.any(~np.isfinite(parameters))
        or satellites.ndim != 1
        or not len(satellites)
        or len(np.unique(satellites)) != len(satellites)
        or np.any(satellites < 0)
        or np.any(satellites >= candidate_count)
        or weights.shape != satellites.shape
        or np.any(~np.isfinite(weights))
        or np.any(weights <= 0)
        or full_bank.ndim != 1
        or len(full_bank) < len(satellites)
        or len(np.unique(full_bank)) != len(full_bank)
        or not set(satellites).issubset(set(full_bank))
    ):
        raise ValueError("source trial or frozen full bank is malformed")
    if "coefficients_hz_ghz" in trial:
        raise ValueError("source trial is not the declared no-RF model")

    arms = arms_factory(data, len(satellites), len(full_bank))
    evaluator = arms["finite_set"]
    predicted, visible = _predict(plan_factory, data, satellites, parameters)
    baseline = _evaluate(evaluator, predicted, visible, weights)
    tau = parameters[6 + satellites]
    source_prior = 0.5 * float(np.sum((tau / TAU_SIGMA_S) ** 2))
    source_objective = -float(baseline["total_log_likelihood"]) + source_prior
    if not np.isclose(source_objective, trial["objective"], rtol=0, atol=1e-6):
        raise ValueError("grouped finite-set evaluation does not reproduce sealed source")
    group_count = len(baseline["group_values"])
    entry_penalty = 0.5 * len(satellites) * np.log(group_count)
    if not np.isclose(entry_penalty, trial["entry_penalty"], rtol=0, atol=1e-9):
        raise ValueError("source entry penalty differs from same-K grouped penalty")
    expected_probability = 0.8 / len(full_bank)
    if not np.isclose(
        evaluator.detection_probability, expected_probability, rtol=0, atol=1e-15
    ):
        raise ValueError("finite-set detection probability changed from 0.8/source full K")

    selected = set(int(value) for value in satellites)
    unused = np.asarray(
        [index for index in range(candidate_count) if index not in selected], dtype=int
    )
    candidate_parameters = parameters.copy()
    candidate_parameters[6 + unused] = 0.0
    candidate_predicted, candidate_visible = _predict(
        plan_factory, data, unused, candidate_parameters
    )
    scorers = []
    parity_errors = []
    timed_out = clock() >= deadline
    for slot in range(len(satellites)):
        if timed_out or clock() >= deadline:
            timed_out = True
            break
        scorer = cavity_factory(
            evaluator.prepared,
            predicted,
            visible,
            satellite_index=slot,
            sigma_hz=SIGMA_HZ,
            detection_probability=evaluator.detection_probability,
            clutter_rate=evaluator.clutter_rate,
        )
        reproduced = scorer.evaluate(predicted[:, slot], visible[:, slot])
        parity_errors.append(
            abs(float(reproduced["total_log_likelihood"]) - baseline["total_log_likelihood"])
        )
        scorers.append(scorer)
    maximum_source_parity_error = max(parity_errors, default=0.0)
    if maximum_source_parity_error > 1e-6:
        raise ValueError("cavity source replacement does not reproduce full DP")

    scores = []
    total_pair_count = len(satellites) * len(unused)
    for slot, scorer in enumerate(scorers):
        removed = satellites[slot]
        if timed_out:
            break
        prior_change = -0.5 * float((parameters[6 + removed] / TAU_SIGMA_S) ** 2)
        for candidate_column, added in enumerate(unused):
            if clock() >= deadline:
                timed_out = True
                break
            result = scorer.evaluate(
                candidate_predicted[:, candidate_column],
                candidate_visible[:, candidate_column],
            )
            objective = -float(result["total_log_likelihood"]) + source_prior + prior_change
            scores.append(
                {
                    "removed_index": int(removed),
                    "removed_catalog_number": int(np.asarray(data.numbers)[removed]),
                    "added_index": int(added),
                    "added_catalog_number": int(np.asarray(data.numbers)[added]),
                    "objective": objective,
                    "objective_improvement": source_objective - objective,
                    "selection_score": objective + entry_penalty,
                    "selection_score_improvement": source_objective - objective,
                    "tau_prior_change": prior_change,
                }
            )
    scores.sort(
        key=lambda item: (
            -item["objective_improvement"],
            item["removed_index"],
            item["added_index"],
        )
    )

    top_details = []
    for score in scores[:3]:
        if clock() >= deadline:
            timed_out = True
            break
        slot = int(np.flatnonzero(satellites == score["removed_index"])[0])
        new_bank = satellites.copy()
        new_bank[slot] = score["added_index"]
        direct_parameters = parameters.copy()
        direct_parameters[6 + score["added_index"]] = 0.0
        direct_predicted, direct_visible = _predict(
            plan_factory, data, new_bank, direct_parameters
        )
        direct = _evaluate(evaluator, direct_predicted, direct_visible, weights)
        direct_objective = (
            -float(direct["total_log_likelihood"])
            + source_prior
            + score["tau_prior_change"]
        )
        parity_error = abs(direct_objective - score["objective"])
        if parity_error > 1e-6:
            raise ValueError("cavity replacement does not reproduce direct full DP")
        association = np.asarray(direct["row_association_probability"], dtype=float)
        row_support = float(np.sum(association[:, slot]))
        positive_rows = int(np.sum(association[:, slot] > 0))
        visible_groups = int(len(np.unique(np.asarray(data.group)[direct_visible[:, slot]])))
        top_details.append(
            {
                **score,
                "direct_full_dp_objective": direct_objective,
                "cavity_full_dp_objective_error": parity_error,
                "replacement_visible_group_count": visible_groups,
                "replacement_row_posterior_support": row_support,
                "replacement_positive_posterior_row_count": positive_rows,
                "replacement_support_label": _support_label(visible_groups, row_support),
            }
        )
    elapsed = clock() - started
    timed_out = timed_out or elapsed > budget_s
    complete = (
        not timed_out
        and len(scores) == total_pair_count
        and len(top_details) == min(3, len(scores))
    )
    return {
        "status": "complete" if complete else "partial",
        "complete": complete,
        "budget_s": float(budget_s),
        "elapsed_s": elapsed,
        "evaluated_pair_count": len(scores),
        "total_pair_count": total_pair_count,
        "top_full_dp_recomputation_count": len(top_details),
        "selected_count": len(satellites),
        "unused_candidate_count": len(unused),
        "source_full_bank_count": len(full_bank),
        "candidate_pool_count": candidate_count,
        "detection_probability_per_satellite": expected_probability,
        "source_objective": source_objective,
        "source_entry_penalty": entry_penalty,
        "entry_penalty_change": 0.0,
        "source_selection_score": source_objective + entry_penalty,
        "source_cavity_full_dp_max_abs_error": maximum_source_parity_error,
        "source_cavity_parity_slot_count": len(scorers),
        "top10": scores[:10],
        "top3_full_dp": top_details,
        "all_scores": scores,
        "selection_filter": "none; swaps rank only by exact frozen-state objective",
        "support_policy": (
            "No support threshold is applied. Top-three replacements report visibility, exact "
            "row-posterior support, and a descriptive support label."
        ),
        "scope": (
            "Exact grouped finite-set one-for-one cavity screen at frozen position, RX, and "
            "other-satellite tau. Added-candidate tau is fixed to zero. K, 0.8/source-full-K "
            "detection probability, clutter model, and entry penalty remain unchanged. This is "
            "a bounded local association diagnostic over the persisted candidate search universe, "
            "not a change of the full-K probability denominator, timing grid, refit, calibrated "
            "model comparison, or correction."
        ),
    }


def diagnose_unit(
    unit_id,
    *,
    profile_root=DEFAULT_PROFILE_ROOT,
    grouped_root=DEFAULT_GROUPED_ROOT,
    exports=DEFAULT_EXPORTS,
    expected_export_sha256=EXPORT_SHA256,
    budget_s=MAX_BUDGET_S_PER_UNIT,
):
    if unit_id not in SUPPORTED_UNITS:
        raise ValueError(f"unit_id must be one of {SUPPORTED_UNITS}")
    profile_path = Path(profile_root) / unit_id / "fit.json"
    grouped_path = Path(grouped_root) / unit_id / "fit.json"
    profile = json.loads(profile_path.read_text())
    grouped = json.loads(grouped_path.read_text())
    closure_before = snapshot_before_validation(profile, profile_path, grouped_path)
    trial = _selected_trial(profile)
    if (
        profile.get("run_id") != SOURCE_RUN
        or profile.get("unit", {}).get("unit_id") != unit_id
        or profile.get("unit", {}).get("size") != 1
        or profile.get("dataset") != unit_id[:4]
        or profile.get("source_fit_sha256") != digest(grouped_path)
        or grouped.get("schema") != "finite-set-grouped-cohort/v1"
        or grouped.get("unit", {}).get("unit_id") != unit_id
        or grouped.get("reference_read_before_seal") is not False
        or grouped.get("evaluation_written") is not False
        or not grouped.get("sealed_utc")
    ):
        raise ValueError("profile and grouped no-RF source receipts are not strictly bound")
    authoritative = profile["source_hashes"]
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
        grouped.get("fit", {}).get("grouped_geometry", {}),
    )
    full_bank = profile.get("fit", {}).get("full_bank")
    diagnostic = screen_identity_replacements(
        data, trial, full_bank, budget_s=budget_s
    )
    assert_snapshot_unchanged(closure_before)
    return {
        "unit_id": unit_id,
        "dataset": profile["dataset"],
        "source_run_id": SOURCE_RUN,
        "source_selection": "predeclared score_leader",
        "profile_fit_sha256": digest(profile_path),
        "grouped_fit_sha256": digest(grouped_path),
        "source_hashes_snapshotted_before_validator_use": closure_before,
        "loader_inputs_bound_to_profile_source_hashes": loader_hashes,
        "diagnostic": diagnostic,
        "provenance": {
            "reference_accessed": False,
            "evaluation_artifact_accessed": False,
            "iq_read": False,
            "rf_collection_performed": False,
            "fit_performed": False,
            "timing_grid_performed": False,
            "position_or_nuisance_parameters_changed": False,
        },
    }


def run(*, diagnoser=diagnose_unit, **kwargs):
    return {
        "schema": SCHEMA,
        "source_run_id": SOURCE_RUN,
        "configuration": {
            "units": list(SUPPORTED_UNITS),
            "sigma_hz": SIGMA_HZ,
            "tau_sigma_s": TAU_SIGMA_S,
            "maximum_budget_s_per_unit": MAX_BUDGET_S_PER_UNIT,
        },
        "scope": (
            "Truth-free no-fit exact grouped finite-set same-K replacement screens for two "
            "predeclared pilots. No reference, evaluation artifact, timing grid, refit, or "
            "position correction is used."
        ),
        "units": [diagnoser(unit_id, **kwargs) for unit_id in SUPPORTED_UNITS],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_PROFILE_ROOT)
    parser.add_argument("--grouped-root", type=Path, default=DEFAULT_GROUPED_ROOT)
    parser.add_argument("--exports", type=Path, default=DEFAULT_EXPORTS)
    parser.add_argument("--expected-export-sha256", default=EXPORT_SHA256)
    parser.add_argument("--budget-s", type=float, default=MAX_BUDGET_S_PER_UNIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    if arguments.output.exists():
        raise FileExistsError(arguments.output)
    receipt = run(
        profile_root=arguments.profile_root,
        grouped_root=arguments.grouped_root,
        exports=arguments.exports,
        expected_export_sha256=arguments.expected_export_sha256,
        budget_s=arguments.budget_s,
    )
    arguments.output.write_text(
        json.dumps(serializable(receipt), indent=2, allow_nan=False) + "\n"
    )
    print(json.dumps({"output": str(arguments.output), "unit_count": len(receipt["units"])}))


if __name__ == "__main__":
    main()


__all__ = [
    "diagnose_unit",
    "run",
    "screen_identity_replacements",
    "snapshot_before_validation",
    "source_dependency_paths",
]
