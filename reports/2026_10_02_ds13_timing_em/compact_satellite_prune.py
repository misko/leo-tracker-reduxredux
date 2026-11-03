"""Iterative fixed-position deletion pruning of sealed DS13 compact selections."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from all_visible_bank import load_expanded_scan
from compact_satellite_selection import (
    SESSIONS,
    FrozenBankEvaluator,
    complexity_penalty,
    fit_compact_bank,
)
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from prepare_scans import ROOT
from rough_smoke import serializable

DEFAULT_BUDGET_S = 170.0
MAX_BUDGET_S = 180.0
REFIT_BUDGET_S = 12.0
IMPROVEMENT_TOLERANCE = 1.0e-8


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _fit_score(fit, group_count, satellite_count):
    penalty = complexity_penalty(group_count, satellite_count)
    return {
        "objective": float(fit["objective"]),
        "data_objective": float(fit["data_objective"]),
        "prior_objective": float(fit["prior_objective"]),
        "raw_log_likelihood": float(fit["raw_log_likelihood"]),
        "complexity_penalty": penalty,
        "penalized_objective": float(fit["objective"]) + penalty,
    }


def evaluate_deletions(
    evaluator,
    parameters,
    satellites,
    deadline,
    *,
    clock=time.monotonic,
):
    satellites = np.asarray(satellites, dtype=int)
    rows = []
    for column, removed in enumerate(satellites):
        if clock() >= deadline:
            break
        retained = np.delete(satellites, column)
        evaluated = evaluator.evaluate_bank(parameters, retained)
        rows.append(
            {
                "removed_satellite_index": int(removed),
                "retained_satellite_indices": retained,
                **evaluated,
            }
        )
    rows.sort(
        key=lambda row: (
            row["penalized_objective"],
            row["removed_satellite_index"],
        )
    )
    return rows, len(rows) == len(satellites)


def iterative_prune(
    data,
    evaluator,
    initial_fit,
    satellites,
    detection_probability,
    rf_coefficient,
    *,
    budget_s,
    refit_budget_s=REFIT_BUDGET_S,
    clock=time.monotonic,
    fitter=fit_compact_bank,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_BUDGET_S:
        raise ValueError("pruning budget must lie in (0, 180]")
    if not np.isfinite(refit_budget_s) or not 0 < refit_budget_s <= REFIT_BUDGET_S:
        raise ValueError("refit budget must lie in (0, 12]")
    started = clock()
    deadline = started + budget_s
    group_count = len(np.unique(data.group))
    current_fit = initial_fit
    current_satellites = np.asarray(satellites, dtype=int).copy()
    current_parameters = np.asarray(initial_fit["parameters"], dtype=float).copy()
    fixed_position = current_parameters[:2].copy()
    current_score = _fit_score(current_fit, group_count, len(current_satellites))
    iterations = []
    termination = "iteration_limit"
    while len(current_satellites) > 1:
        deletion_rows, complete = evaluate_deletions(
            evaluator,
            current_parameters,
            current_satellites,
            deadline,
            clock=clock,
        )
        iteration = {
            "iteration": len(iterations),
            "satellite_count_before": len(current_satellites),
            "penalized_objective_before": current_score["penalized_objective"],
            "deletions_planned": len(current_satellites),
            "deletions_evaluated": len(deletion_rows),
            "deletion_scan_complete": complete,
            "deletions": deletion_rows,
            "accepted": False,
        }
        iterations.append(iteration)
        if not complete:
            termination = "budget_exhausted_during_deletion_scan"
            break
        best = deletion_rows[0]
        best_change = best["penalized_objective"] - current_score["penalized_objective"]
        iteration["best_fixed_nuisance_change"] = best_change
        if best_change >= -IMPROVEMENT_TOLERANCE:
            termination = "no_improving_deletion"
            break
        remaining = deadline - clock()
        refit_budget = min(refit_budget_s, remaining)
        if refit_budget <= 0.25:
            termination = "budget_exhausted_before_refit"
            iteration["refit_attempted"] = False
            break
        retained = np.asarray(best["retained_satellite_indices"], dtype=int)
        refit = fitter(
            data,
            current_parameters,
            retained,
            detection_probability,
            rf_coefficient,
            budget_s=refit_budget,
        )
        if not np.array_equal(np.asarray(refit["parameters"])[:2], fixed_position):
            raise RuntimeError("pruning refit moved the sealed displaced position")
        refit_score = _fit_score(refit, group_count, len(retained))
        refit_change = refit_score["penalized_objective"] - current_score[
            "penalized_objective"
        ]
        iteration.update(
            {
                "refit_attempted": True,
                "proposed_satellite_indices": retained,
                "removed_satellite_index": best["removed_satellite_index"],
                "refit": refit,
                "refit_score": refit_score,
                "refit_penalized_change": refit_change,
            }
        )
        if not np.isfinite(refit_score["penalized_objective"]) or refit_change >= 0:
            termination = "refit_did_not_improve"
            break
        iteration["accepted"] = True
        current_satellites = retained
        current_fit = refit
        current_parameters = np.asarray(refit["parameters"], dtype=float).copy()
        current_score = refit_score
    else:
        termination = "single_satellite_floor"
    last_scan_complete = bool(iterations and iterations[-1]["deletion_scan_complete"])
    deletion_minimal = bool(
        termination == "no_improving_deletion"
        and last_scan_complete
        and current_fit.get("success") is True
    )
    return {
        "fit": current_fit,
        "satellite_indices": current_satellites,
        **current_score,
        "iterations": iterations,
        "accepted_deletion_count": int(
            sum(iteration["accepted"] for iteration in iterations)
        ),
        "termination": termination,
        "deletion_minimal": deletion_minimal,
        "selected_fit_converged": bool(current_fit.get("success", False)),
        "fixed_position_km": fixed_position,
        "elapsed_s": clock() - started,
        "budget_s": budget_s,
    }


def _validate_source(session, receipt):
    selected = receipt.get("selected", {})
    bank = receipt.get("bank", {})
    if (
        receipt.get("schema") != "ds13-compact-satellite-selection/v1"
        or receipt.get("session") != session
        or receipt.get("reference_read_before_seal") is not False
        or bank.get("screening_complete") is not True
        or bank.get("unscreened_candidate_count") != 0
        or selected.get("fit", {}).get("position_fixed") is not True
    ):
        raise ValueError("invalid or incomplete compact-selection source")
    assert_snapshot_unchanged(receipt["source_hashes"])


def run_case(session, *, budget_s=DEFAULT_BUDGET_S):
    if session not in SESSIONS:
        raise ValueError("session outside pruning protocol")
    destination = ROOT / "compact-satellite-pruned" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    source_path = ROOT / "compact-satellite-selection" / f"{session}.json"
    source = json.loads(source_path.read_text())
    _validate_source(session, source)
    data = load_expanded_scan(session)
    selected = source["selected"]
    satellites = np.asarray(selected["satellite_indices"], dtype=int)
    probability = float(selected["detection_probability"])
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    evaluator = FrozenBankEvaluator(
        data,
        prepared,
        probability,
        selected["fit"]["rf_center_hz"],
        selected["fit"]["rf_coefficient_hz_per_ghz"],
        len(np.unique(data.group)),
    )
    dependency_paths = [
        __file__,
        source_path,
        ROOT / "compact_satellite_selection.py",
        ROOT / "all_visible_bank.py",
        ROOT / "all-visible-bank" / session / "receipt.json",
        ROOT / "all-visible-bank" / session / "expanded.npz",
        ROOT / "position-profile-protocol.json",
        ROOT / "position-profile-resource-amendment.json",
    ]
    source_hashes = {**source["source_hashes"], **snapshot_files(dependency_paths)}
    result = iterative_prune(
        data,
        evaluator,
        selected["fit"],
        satellites,
        probability,
        selected["fit"]["rf_coefficient_hz_per_ghz"],
        budget_s=budget_s,
    )
    final_satellites = np.asarray(result["satellite_indices"], dtype=int)
    assert_snapshot_unchanged(source_hashes)
    receipt = {
        "schema": "ds13-compact-satellite-pruned/v1",
        "session": session,
        "selected": {
            "satellite_indices": final_satellites,
            "catalog_numbers": np.asarray(data.numbers)[final_satellites],
            "detection_probability": probability,
            "fit": result["fit"],
            "objective": result["objective"],
            "selection_penalty": result["complexity_penalty"],
            "complexity_penalty": result["complexity_penalty"],
            "penalized_objective": result["penalized_objective"],
        },
        "satellite_indices": final_satellites,
        "catalog_numbers": np.asarray(data.numbers)[final_satellites],
        "detection_probability": probability,
        "fit": result["fit"],
        "selection_penalty": result["complexity_penalty"],
        "pruning": result,
        "resolution": {
            "deletion_minimal": result["deletion_minimal"],
            "selected_fit_converged": result["selected_fit_converged"],
            "termination": result["termination"],
            "global_minimality_claim": False,
        },
        "full_pool_screening": {
            "source_receipt": str(source_path),
            "source_receipt_sha256": _sha256(source_path),
            "screening_complete": source["bank"]["screening_complete"],
            "screened_candidate_count": source["bank"]["screened_candidate_count"],
            "all_visible_candidate_count": source["bank"]["all_visible_candidate_count"],
            "source_selected_satellite_indices": selected["satellite_indices"],
            "source_selected_catalog_numbers": selected["catalog_numbers"],
        },
        "criterion": {
            "probability_rule": "Unchanged fixed 0.8/original_selected_K from source receipt",
            "complexity_penalty": "0.5*log(group_count) per active satellite",
            "position": "Fixed at the sealed displaced common-RF source position",
            "truth_used": False,
        },
        "limitations": (
            "EXPLORATORY iterative greedy leave-one-out pruning. Deletion minimality is reported "
            "only after a complete nonimproving deletion scan at a converged refit. It is not a "
            "global minimality result and does not revisit excluded additions or swaps."
        ),
        "source_hashes": source_hashes,
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "source_count": len(satellites),
        "selected_count": len(final_satellites),
        "accepted_deletions": result["accepted_deletion_count"],
        "deletion_minimal": result["deletion_minimal"],
        "fit_success": result["selected_fit_converged"],
        "termination": result["termination"],
        "elapsed_s": result["elapsed_s"],
    }


def _run(arguments):
    session, budget_s = arguments
    return run_case(session, budget_s=budget_s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", nargs="*", choices=SESSIONS)
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    arguments = parser.parse_args()
    sessions = tuple(arguments.session) or SESSIONS
    with ProcessPoolExecutor(max_workers=min(2, len(sessions))) as executor:
        for result in executor.map(
            _run, [(session, arguments.budget_s) for session in sessions]
        ):
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
