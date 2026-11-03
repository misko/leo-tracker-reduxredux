"""Bounded truth-free compact satellite-set audit over the DS13 visible catalogue."""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import (
    _wrapped_normal_terms,
    circular_residual,
    prepare_finite_set_likelihood,
)
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective, rf_features
from rough_smoke import serializable
from truth_start_diagnostic import optimize

SESSIONS = ("scan-fw-911c4e5db9243281", "scan-fw-ffa1cc19d8d7c09f")
SIGMA_HZ = 200.0
CLUTTER_RATE = 2.0
SCREEN_OFFSETS_S = np.arange(-3.0, 3.0 + 1.0, 1.0)
SCREEN_BATCH_SIZE = 32
SCREEN_SHORTLIST_SIZE = 8
REFIT_SET_COUNT = 4
MAX_REFIT_BUDGET_S = 20.0
DEFAULT_BUDGET_S = 280.0


def fixed_detection_probability(original_selected_count):
    if (
        isinstance(original_selected_count, bool)
        or int(original_selected_count) != original_selected_count
        or original_selected_count < 1
    ):
        raise ValueError("original_selected_count must be a positive integer")
    return 0.8 / int(original_selected_count)


def complexity_penalty(group_count, active_satellite_count):
    if (
        isinstance(group_count, bool)
        or int(group_count) != group_count
        or group_count < 1
    ):
        raise ValueError("group_count must be a positive integer")
    if (
        isinstance(active_satellite_count, bool)
        or int(active_satellite_count) != active_satellite_count
        or active_satellite_count < 1
    ):
        raise ValueError("active_satellite_count must be a positive integer")
    return 0.5 * np.log(int(group_count)) * int(active_satellite_count)


def timing_prior(total_shifts_s):
    shifts = np.asarray(total_shifts_s, dtype=float)
    if shifts.ndim != 1 or not len(shifts) or np.any(~np.isfinite(shifts)):
        raise ValueError("total shifts must be a nonempty finite vector")
    common = float(np.mean(shifts))
    individual = shifts - common
    return 0.5 * float(individual @ individual) + 0.5 * (common / 10.0) ** 2


def fixed_position_bounds(bounds, position_km):
    position = np.asarray(position_km, dtype=float)
    if position.shape != (2,) or np.any(~np.isfinite(position)):
        raise ValueError("fixed position must contain two finite coordinates")
    fixed = list(bounds)
    if len(fixed) < 2:
        raise ValueError("optimizer bounds omit position coordinates")
    fixed[:2] = [(float(value), float(value)) for value in position]
    return fixed


def selected_indices_by_catalog(expanded_numbers, selected_catalog_numbers):
    expanded = np.asarray(expanded_numbers)
    selected = np.asarray(selected_catalog_numbers)
    if expanded.ndim != 1 or selected.ndim != 1 or not len(selected):
        raise ValueError("catalogue numbers must be one-dimensional and selected nonempty")
    if len(np.unique(expanded)) != len(expanded) or len(np.unique(selected)) != len(selected):
        raise ValueError("catalogue numbers must be unique")
    lookup = {int(number): index for index, number in enumerate(expanded)}
    missing = [int(number) for number in selected if int(number) not in lookup]
    if missing:
        raise ValueError(f"expanded bank is missing selected catalogues {missing}")
    return np.asarray([lookup[int(number)] for number in selected], dtype=int)


def remap_parameters(
    source_parameters,
    source_numbers,
    source_satellites,
    expanded_numbers,
):
    source_parameters = np.asarray(source_parameters, dtype=float)
    source_numbers = np.asarray(source_numbers)
    source_satellites = np.asarray(source_satellites, dtype=int)
    expanded_numbers = np.asarray(expanded_numbers)
    if source_parameters.shape != (6 + len(source_numbers),):
        raise ValueError("source parameters do not match source catalogue")
    if np.any(source_satellites < 0) or np.any(source_satellites >= len(source_numbers)):
        raise ValueError("source satellite index outside source catalogue")
    selected = selected_indices_by_catalog(
        expanded_numbers, source_numbers[source_satellites]
    )
    selected_shifts = source_parameters[6 + source_satellites]
    parameters = np.r_[
        source_parameters[:6],
        np.full(len(expanded_numbers), float(np.mean(selected_shifts))),
    ]
    parameters[6 + selected] = selected_shifts
    return parameters, selected


def _same_observations(source, expanded):
    keys = ("times", "measured", "rf", "receiver", "channel", "group")
    mismatched = []
    for key in keys:
        left = np.asarray(getattr(source, key))
        right = np.asarray(getattr(expanded, key))
        if left.shape != right.shape or not np.array_equal(left, right):
            mismatched.append(key)
    if mismatched:
        raise ValueError(
            "expanded bank changed stored grouped observations: " + ", ".join(mismatched)
        )


def _support_receipt(result, satellites, numbers):
    support = np.asarray(result["satellite_support"], dtype=float)
    return {
        "satellite_indices": np.asarray(satellites, dtype=int),
        "catalog_numbers": np.asarray(numbers)[np.asarray(satellites, dtype=int)],
        "expected_group_support": support,
        "satellites_below_support_1": int(np.count_nonzero(support < 1.0)),
        "satellites_below_support_5": int(np.count_nonzero(support < 5.0)),
        "selection_use": "reporting only; support thresholds did not filter or rank sets",
    }


def _predict_matrix(data, parameters, satellites):
    satellites = np.asarray(satellites, dtype=int)
    row_count = len(np.asarray(data.times))
    rows = np.repeat(np.arange(row_count, dtype=int), len(satellites))
    paired = np.tile(satellites, row_count)
    predicted, visible = data.predict(parameters, rows=rows, satellites=paired)
    shape = (row_count, len(satellites))
    return np.asarray(predicted, dtype=float).reshape(shape), np.asarray(visible).reshape(shape)


class FrozenBankEvaluator:
    def __init__(
        self,
        data,
        prepared,
        detection_probability,
        rf_center_hz,
        rf_coefficient_hz_per_ghz,
        group_count,
    ):
        self.data = data
        self.prepared = prepared
        self.detection_probability = float(detection_probability)
        center, features = rf_features(data.rf, data.receiver, False)
        if not np.isclose(center, rf_center_hz, rtol=0.0, atol=1e-6):
            raise ValueError("expanded bank RF center does not reproduce sealed calibration")
        coefficient = np.asarray(rf_coefficient_hz_per_ghz, dtype=float)
        if coefficient.shape != (1,) or np.any(~np.isfinite(coefficient)):
            raise ValueError("common RF coefficient must be one finite value")
        self.correction = features[:, 0] * coefficient[0]
        self.group_count = int(group_count)
        self.last_result = None

    def evaluate_predictions(self, predicted, visible, shifts, satellites):
        predicted = np.asarray(predicted, dtype=float)
        result = self.prepared.evaluate(
            predicted + self.correction[:, None],
            visible,
            sigma_hz=SIGMA_HZ,
            detection_probability=self.detection_probability,
            clutter_rate=CLUTTER_RATE,
            implementation="batched",
            return_gradient=False,
            return_precision=False,
        )
        self.last_result = result
        data_objective = -float(result["total_log_likelihood"])
        prior_objective = timing_prior(shifts)
        objective = data_objective + prior_objective
        penalty = complexity_penalty(self.group_count, predicted.shape[1])
        return {
            "objective": objective,
            "data_objective": data_objective,
            "raw_log_likelihood": float(result["total_log_likelihood"]),
            "prior_objective": prior_objective,
            "complexity_penalty": penalty,
            "penalized_objective": objective + penalty,
            "support": _support_receipt(result, satellites, self.data.numbers),
        }

    def evaluate_bank(self, parameters, satellites):
        satellites = np.asarray(satellites, dtype=int)
        predicted, visible = _predict_matrix(self.data, parameters, satellites)
        shifts = np.asarray(parameters, dtype=float)[6 + satellites]
        return self.evaluate_predictions(predicted, visible, shifts, satellites)


def competitive_addition_scores(
    prepared,
    baseline_result,
    predicted,
    visible,
    detection_probability,
    *,
    sigma_hz=SIGMA_HZ,
):
    """Exact frozen-incumbent likelihood change for independent candidate additions."""

    predicted = np.asarray(predicted, dtype=float)
    visible = np.asarray(visible, dtype=bool)
    if predicted.ndim != 2 or predicted.shape[0] != prepared.row_count:
        raise ValueError("candidate predictions must be rows by candidates")
    if visible.shape != predicted.shape:
        raise ValueError("candidate visibility must match predictions")
    probability = float(detection_probability)
    if not 0.0 <= probability <= 1.0:
        raise ValueError("detection probability must lie in [0,1]")
    for rows in prepared.group_row_indices:
        if np.any(visible[rows] != visible[rows[0]]):
            raise ValueError("candidate visibility must be groupwise constant")

    residual = circular_residual(prepared.measured[:, None], predicted, prepared.alias_hz)
    residual = np.where(visible, residual, 0.0)
    row_log_density, _ = _wrapped_normal_terms(
        residual, sigma_hz, prepared.alias_hz, 4096, False
    )
    row_density = np.where(visible, np.exp(row_log_density), 0.0)
    cluster_sizes = np.asarray([len(rows) for rows in prepared.clusters], dtype=float)
    member_scale = 1.0 / cluster_sizes[prepared.original_to_unique]
    unique_density = np.zeros((prepared.unique_peak_count, predicted.shape[1]))
    np.add.at(
        unique_density,
        prepared.original_to_unique,
        row_density * member_scale[:, None],
    )
    clutter = np.asarray(baseline_result["clutter_probability"], dtype=float)
    if clutter.shape != (prepared.unique_peak_count,):
        raise ValueError("baseline clutter marginals do not match prepared peaks")
    clutter_intensity = float(baseline_result["clutter_rate"]) / prepared.alias_hz
    group_ratio = np.zeros((len(prepared.group_values), predicted.shape[1]))
    np.add.at(
        group_ratio,
        prepared.unique_group_index,
        unique_density * clutter[:, None] / clutter_intensity,
    )
    group_visible = np.stack([visible[rows[0]] for rows in prepared.group_row_indices])
    mixture_ratio = (1.0 - probability) + probability * group_ratio
    mixture_ratio = np.where(group_visible, mixture_ratio, 1.0)
    empty = np.asarray(baseline_result["empty_probability"], dtype=float)[:, None]
    old_nonempty = np.asarray(baseline_result["nonempty_probability"], dtype=float)[:, None]
    new_nonempty = np.where(
        group_visible,
        1.0 - empty * (1.0 - probability),
        old_nonempty,
    )
    group_delta = np.log(mixture_ratio) + np.log(old_nonempty) - np.log(new_nonempty)
    posterior_detection = np.where(
        group_visible,
        probability * group_ratio / mixture_ratio,
        0.0,
    )
    return {
        "log_likelihood_change": np.sum(group_delta, axis=0),
        "candidate_expected_group_support": np.sum(posterior_detection, axis=0),
        "group_log_likelihood_change": group_delta,
    }


def fit_compact_bank(
    data,
    initial_parameters,
    satellites,
    detection_probability,
    rf_coefficient,
    *,
    budget_s,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_REFIT_BUDGET_S:
        raise ValueError("compact refit budget must lie in (0, 20]")
    objective = CalibrationObjective(
        data, initial_parameters, satellites, False, budget_s
    )
    objective.likelihood.detection_probability = float(detection_probability)
    coefficient = np.asarray(rf_coefficient, dtype=float)
    if coefficient.shape != (1,) or np.any(~np.isfinite(coefficient)):
        raise ValueError("common RF coefficient must contain one finite value")
    start = np.r_[objective.base.initial_vector, coefficient]
    position = np.asarray(initial_parameters, dtype=float)[:2].copy()
    bounds = fixed_position_bounds(objective.bounds, position)
    fitted = optimize(objective, start, bounds, budget_s=budget_s)
    current = np.asarray(fitted["vector"], dtype=float)
    if not np.array_equal(current[:2], position):
        raise RuntimeError("compact nuisance refit moved the fixed displaced position")
    state = objective.base.state(current[: objective.size])
    result = objective.likelihood.last_result
    return {
        **state,
        "vector": current[: objective.size],
        "objective": float(fitted["objective"]),
        "data_objective": -float(result["total_log_likelihood"]),
        "raw_log_likelihood": float(result["total_log_likelihood"]),
        "prior_objective": timing_prior(state["total_shifts_s"]),
        "success": bool(fitted["success"]),
        "status": fitted["status"],
        "projected_gradient_inf_norm": fitted["projected_gradient_inf_norm"],
        "rf_center_hz": objective.center,
        "rf_coefficient_hz_per_ghz": current[objective.size :],
        "satellite_indices": np.asarray(satellites, dtype=int),
        "support": _support_receipt(result, satellites, data.numbers),
        "calls": int(objective.base.calls),
        "trace": fitted["trace"],
        "elapsed_s": fitted["elapsed_s"],
        "budget_s": float(budget_s),
        "optimizer": "existing complete-data Fisher curvature with monotone line search",
        "position_fixed": True,
        "fixed_position_km": position,
    }


def _screen_candidates(
    data,
    evaluator,
    parameters,
    selected,
    candidates,
    deadline,
    *,
    clock=time.monotonic,
):
    selected = np.asarray(selected, dtype=int)
    candidates = np.asarray(candidates, dtype=int)
    baseline_predicted, baseline_visible = _predict_matrix(data, parameters, selected)
    baseline_shifts = np.asarray(parameters)[6 + selected]
    baseline = evaluator.evaluate_predictions(
        baseline_predicted, baseline_visible, baseline_shifts, selected
    )
    baseline_result = evaluator.last_result
    common_shift = float(np.mean(baseline_shifts))
    rows = []
    stopped = False
    for start in range(0, len(candidates), SCREEN_BATCH_SIZE):
        if clock() >= deadline:
            stopped = True
            break
        batch = candidates[start : start + SCREEN_BATCH_SIZE]
        grids = []
        for offset in SCREEN_OFFSETS_S:
            trial = np.asarray(parameters, dtype=float).copy()
            trial[6 + batch] = common_shift + offset
            prediction, visibility = _predict_matrix(data, trial, batch)
            score = competitive_addition_scores(
                evaluator.prepared,
                baseline_result,
                prediction + evaluator.correction[:, None],
                visibility,
                evaluator.detection_probability,
            )
            grids.append((prediction, visibility, score))
        for column, candidate in enumerate(batch):
            if clock() >= deadline:
                stopped = True
                break
            trials = []
            bank = np.r_[selected, candidate]
            for offset, (_prediction, _visibility, score) in zip(
                SCREEN_OFFSETS_S, grids, strict=True
            ):
                shifts = np.r_[baseline_shifts, common_shift + offset]
                raw_change = float(score["log_likelihood_change"][column])
                data_objective = baseline["data_objective"] - raw_change
                prior_objective = timing_prior(shifts)
                objective = data_objective + prior_objective
                penalty = complexity_penalty(evaluator.group_count, len(bank))
                trials.append(
                    {
                        "objective": objective,
                        "data_objective": data_objective,
                        "raw_log_likelihood": baseline["raw_log_likelihood"] + raw_change,
                        "raw_log_likelihood_change": raw_change,
                        "prior_objective": prior_objective,
                        "complexity_penalty": penalty,
                        "penalized_objective": objective + penalty,
                        "candidate_expected_group_support": float(
                            score["candidate_expected_group_support"][column]
                        ),
                        "offset_s": float(offset),
                    }
                )
            best = min(trials, key=lambda item: (item["penalized_objective"], item["offset_s"]))
            rows.append(
                {
                    "satellite_index": int(candidate),
                    "catalog_number": int(np.asarray(data.numbers)[candidate]),
                    "best_offset_s": best["offset_s"],
                    "best_total_shift_s": common_shift + best["offset_s"],
                    "penalized_improvement_vs_baseline": (
                        baseline["penalized_objective"] - best["penalized_objective"]
                    ),
                    "best": best,
                    "grid": trials,
                }
            )
        if stopped:
            break
    rows.sort(
        key=lambda item: (
            -item["penalized_improvement_vs_baseline"],
            item["catalog_number"],
        )
    )
    return baseline, rows, stopped


def _candidate_parameter_map(parameters, selected, screening):
    values = {int(index): float(parameters[6 + index]) for index in selected}
    values.update(
        {
            int(row["satellite_index"]): float(row["best_total_shift_s"])
            for row in screening
        }
    )
    return values


def neighborhood_sets(selected, screening, shortlist_size=SCREEN_SHORTLIST_SIZE):
    selected = tuple(int(value) for value in selected)
    outsiders = tuple(
        int(row["satellite_index"]) for row in screening[: int(shortlist_size)]
    )
    rows = [("baseline", selected)]
    rows.extend(
        (f"drop:{old}", tuple(value for value in selected if value != old))
        for old in selected
    )
    rows.extend((f"add:{new}", (*selected, new)) for new in outsiders)
    rows.extend(
        (
            f"swap:{old}->{new}",
            tuple(new if value == old else value for value in selected),
        )
        for new in outsiders
        for old in selected
    )
    unique = []
    seen = set()
    for move, bank in rows:
        if not bank or len(set(bank)) != len(bank):
            continue
        key = tuple(sorted(bank))
        if key not in seen:
            unique.append((move, bank))
            seen.add(key)
    return unique


def _evaluate_neighborhood(
    data,
    evaluator,
    parameters,
    selected,
    screening,
    deadline,
    *,
    clock=time.monotonic,
):
    shifts = _candidate_parameter_map(parameters, selected, screening)
    rows = []
    stopped = False
    for move, bank in neighborhood_sets(selected, screening):
        if clock() >= deadline:
            stopped = True
            break
        trial = np.asarray(parameters, dtype=float).copy()
        for satellite in bank:
            trial[6 + satellite] = shifts[satellite]
        evaluated = evaluator.evaluate_bank(trial, bank)
        rows.append({"move": move, "satellite_indices": bank, "parameters": trial, **evaluated})
    rows.sort(
        key=lambda item: (
            item["penalized_objective"],
            len(item["satellite_indices"]),
            item["move"],
        )
    )
    return rows, stopped


def _refit_shortlist(
    data,
    neighborhood,
    baseline_selected,
    detection_probability,
    rf_coefficient,
    deadline,
    *,
    clock=time.monotonic,
    fitter=fit_compact_bank,
):
    baseline = next(row for row in neighborhood if row["move"] == "baseline")
    finalists = [baseline]
    finalists.extend(row for row in neighborhood if row is not baseline)
    finalists = finalists[:REFIT_SET_COUNT]
    if baseline not in finalists:
        finalists[-1] = baseline
    rows = []
    for index, candidate in enumerate(finalists):
        remaining = deadline - clock()
        remaining_sets = len(finalists) - index
        budget = min(MAX_REFIT_BUDGET_S, remaining / remaining_sets)
        if budget <= 0.25:
            rows.append(
                {
                    "move": candidate["move"],
                    "satellite_indices": candidate["satellite_indices"],
                    "attempted": False,
                    "status": "overall_budget_exhausted",
                }
            )
            continue
        fit = fitter(
            data,
            candidate["parameters"],
            np.asarray(candidate["satellite_indices"], dtype=int),
            detection_probability,
            rf_coefficient,
            budget_s=budget,
        )
        penalty = complexity_penalty(
            len(np.unique(data.group)), len(candidate["satellite_indices"])
        )
        rows.append(
            {
                "move": candidate["move"],
                "satellite_indices": candidate["satellite_indices"],
                "attempted": True,
                "fit": fit,
                "complexity_penalty": penalty,
                "penalized_objective": fit["objective"] + penalty,
            }
        )
    finite = [
        row
        for row in rows
        if row.get("attempted") and np.isfinite(row["penalized_objective"])
    ]
    if not finite:
        raise RuntimeError("no compact finalist produced a finite objective")
    selected = min(
        finite,
        key=lambda item: (
            item["penalized_objective"],
            len(item["satellite_indices"]),
            item["move"],
        ),
    )
    return rows, selected


def _unpack_expanded(loaded):
    if hasattr(loaded, "numbers"):
        return loaded, {}
    if isinstance(loaded, tuple) and len(loaded) == 2:
        left, right = loaded
        if hasattr(left, "numbers"):
            return left, right
        if hasattr(right, "numbers"):
            return right, left
    if isinstance(loaded, dict) and hasattr(loaded.get("data"), "numbers"):
        return loaded["data"], {key: value for key, value in loaded.items() if key != "data"}
    raise TypeError("load_expanded_scan must return data, (data, receipt), or {'data': data}")


def _source_records(session):
    calibration_path = ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
    parent_path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    calibration = json.loads(calibration_path.read_text())
    parent = json.loads(parent_path.read_text())
    fit = calibration.get("fit", {})
    if (
        calibration.get("session") != session
        or calibration.get("variant") != "common"
        or calibration.get("reference_read_in_fitter") is not False
        or fit.get("success") is not True
        or fit.get("sigma_hz") != SIGMA_HZ
        or parent.get("session") != session
        or parent.get("tolerance") != "medium"
    ):
        raise ValueError("invalid sealed displaced common-RF source")
    assert_snapshot_unchanged(calibration["source_hashes"])
    assert_snapshot_unchanged(parent["source_hashes"])
    return calibration_path, calibration, parent_path, parent


def run_case(session, *, budget_s=DEFAULT_BUDGET_S, clock=time.monotonic):
    if session not in SESSIONS:
        raise ValueError("session outside compact-selection protocol")
    if not np.isfinite(budget_s) or not 0 < budget_s <= 300.0:
        raise ValueError("compact-selection budget must lie in (0, 300]")
    destination = ROOT / "compact-satellite-selection" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol_path = ROOT / "position-profile-protocol.json"
    amendment_path = ROOT / "position-profile-resource-amendment.json"
    calibration_path, calibration, parent_path, parent = _source_records(session)
    from all_visible_bank import load_expanded_scan

    source, grouped = load_scan(session)
    del source
    expanded, bank_receipt = _unpack_expanded(load_expanded_scan(session))
    if not bank_receipt:
        bank_receipt = getattr(expanded, "bank_receipt", {})
    if (
        bank_receipt.get("schema") != "ds13-all-visible-bank/v1"
        or bank_receipt.get("session_id") != session
        or bank_receipt.get("reference_read") is not False
        or bank_receipt.get("status") != "complete"
    ):
        raise ValueError("invalid all-visible bank receipt")
    _same_observations(grouped, expanded)
    source_satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    initial, selected = remap_parameters(
        calibration["fit"]["parameters"],
        grouped.numbers,
        source_satellites,
        expanded.numbers,
    )
    original_count = len(selected)
    probability = fixed_detection_probability(original_count)
    group_count = len(np.unique(expanded.group))
    prepared = prepare_finite_set_likelihood(expanded.measured, expanded.group)
    evaluator = FrozenBankEvaluator(
        expanded,
        prepared,
        probability,
        calibration["fit"]["rf_center_hz"],
        calibration["fit"]["rf_coefficient_hz_per_ghz"],
        group_count,
    )
    all_indices = np.arange(len(expanded.numbers), dtype=int)
    inactive = all_indices[~np.isin(all_indices, selected)]
    inactive = inactive[np.argsort(np.asarray(expanded.numbers)[inactive], kind="stable")]
    dependency_paths = [
        __file__,
        protocol_path,
        amendment_path,
        calibration_path,
        parent_path,
        ROOT / "all_visible_bank.py",
        ROOT / "all-visible-bank" / session / "receipt.json",
        ROOT / "all-visible-bank" / session / "expanded.npz",
        ROOT / "timing_model.py",
        ROOT / "solvers.py",
        ROOT / "soft_likelihood.py",
        ROOT / "rf_calibration_diagnostic.py",
        ROOT / "truth_start_diagnostic.py",
        ROOT / "soft_solvers.py",
        ROOT.parent / "2026_10_02_multiscan_localization" / "finite_set_likelihood.py",
        ROOT.parent / "2026_10_02_multiscan_localization" / "prediction_plan.py",
        ROOT.parent / "2026_10_02_multiscan_localization" / "prediction_jacobian.py",
    ]
    source_hashes = {
        **calibration["source_hashes"],
        **parent["source_hashes"],
        **snapshot_files(dependency_paths),
    }
    started = clock()
    screen_deadline = started + 0.58 * budget_s
    neighborhood_deadline = started + 0.74 * budget_s
    overall_deadline = started + budget_s
    baseline, screening, screen_stopped = _screen_candidates(
        expanded,
        evaluator,
        initial,
        selected,
        inactive,
        screen_deadline,
        clock=clock,
    )
    if not np.isclose(
        baseline["objective"], calibration["fit"]["objective"], rtol=0.0, atol=1e-5
    ):
        raise ValueError("expanded-bank baseline does not reproduce sealed displaced fit")
    neighborhood, neighborhood_stopped = _evaluate_neighborhood(
        expanded,
        evaluator,
        initial,
        selected,
        screening,
        neighborhood_deadline,
        clock=clock,
    )
    refits, winner = _refit_shortlist(
        expanded,
        neighborhood,
        selected,
        probability,
        calibration["fit"]["rf_coefficient_hz_per_ghz"],
        overall_deadline,
        clock=clock,
    )
    selected_fit = winner["fit"]
    assert_snapshot_unchanged(source_hashes)
    receipt = {
        "schema": "ds13-compact-satellite-selection/v1",
        "session": session,
        "criterion": {
            "per_satellite_detection_probability": probability,
            "probability_rule": (
                "Fixed at 0.8/original_selected_K for every active candidate-set comparison; "
                "all inactive all-visible candidates have p=0, represented exactly by omitting "
                "their zero-contribution columns. This is an extension, not the original p=0.8/K "
                "model for changed K."
            ),
            "complexity_penalty": "0.5*log(independent_group_count) per active satellite",
            "complexity_penalty_status": (
                "Tentative predeclared sparsity penalty; not an exact BIC because source groups "
                "remain correlated and the bounded set search is discrete and local."
            ),
            "ranking": "objective including timing prior plus complexity penalty",
            "raw_likelihood_reported_separately": True,
            "truth_used_for_selection": False,
            "position_rule": (
                "Every screening and finalist comparison fixes position at the sealed displaced "
                "common-RF optimum; only RX, timing, and common-RF nuisance terms are refitted."
            ),
        },
        "observations": {
            "row_count": int(len(expanded.measured)),
            "independent_group_count": group_count,
            "preserved_all_grouped_observations": True,
            "matched_track_only_filter": False,
        },
        "bank": {
            "all_visible_candidate_count": int(len(expanded.numbers)),
            "original_selected_count": original_count,
            "inactive_candidate_count": int(len(inactive)),
            "screened_candidate_count": len(screening),
            "unscreened_candidate_count": int(len(inactive) - len(screening)),
            "screening_complete": not screen_stopped and len(screening) == len(inactive),
            "loader_receipt": bank_receipt,
        },
        "screening": {
            "state": "sealed displaced common-RF fit; position and existing nuisances frozen",
            "candidate_timing_grid_s_relative_to_existing_global_mean": SCREEN_OFFSETS_S,
            "batch_size": SCREEN_BATCH_SIZE,
            "rows": screening,
            "stopped_by_budget": screen_stopped,
        },
        "baseline": {
            "satellite_indices": selected,
            "catalog_numbers": np.asarray(expanded.numbers)[selected],
            **baseline,
        },
        "competitive_neighborhood": {
            "moves": "one bounded pass over incumbent, drops, shortlisted adds, and swaps",
            "shortlist_size": min(SCREEN_SHORTLIST_SIZE, len(screening)),
            "evaluated": neighborhood,
            "stopped_by_budget": neighborhood_stopped,
        },
        "refits": refits,
        "selected": {
            "move": winner["move"],
            "satellite_indices": np.asarray(winner["satellite_indices"], dtype=int),
            "catalog_numbers": np.asarray(expanded.numbers)[
                np.asarray(winner["satellite_indices"], dtype=int)
            ],
            "fit": selected_fit,
            "parameters": selected_fit["parameters"],
            "vector": selected_fit["vector"],
            "rf_coefficient_hz_per_ghz": selected_fit["rf_coefficient_hz_per_ghz"],
            "detection_probability": probability,
            "objective": selected_fit["objective"],
            "selection_penalty": winner["complexity_penalty"],
            "complexity_penalty": winner["complexity_penalty"],
            "penalized_objective": winner["penalized_objective"],
        },
        "satellite_indices": np.asarray(winner["satellite_indices"], dtype=int),
        "catalog_numbers": np.asarray(expanded.numbers)[
            np.asarray(winner["satellite_indices"], dtype=int)
        ],
        "detection_probability": probability,
        "fit": selected_fit,
        "selection_penalty": winner["complexity_penalty"],
        "profile_inputs": {
            "satellite_indices": np.asarray(winner["satellite_indices"], dtype=int),
            "initial_parameters": selected_fit["parameters"],
            "start_vector": selected_fit["vector"],
            "rf_coefficient_hz_per_ghz": selected_fit["rf_coefficient_hz_per_ghz"],
            "probability_override": probability,
            "objective": selected_fit["objective"],
            "selection_penalty": winner["complexity_penalty"],
            "semantics": (
                "Fixed compact set and its selected truth-free fitted state for a later nearby "
                "position profile; selection must not be repeated using profile truth results."
            ),
        },
        "resolution": {
            "all_finalists_attempted": all(row.get("attempted") for row in refits),
            "all_attempted_finalists_converged": all(
                row.get("fit", {}).get("success", False)
                for row in refits
                if row.get("attempted")
            ),
            "selected_fit_converged": bool(selected_fit["success"]),
            "ranking_resolved": bool(
                not screen_stopped
                and not neighborhood_stopped
                and all(row.get("attempted") for row in refits)
                and all(row.get("fit", {}).get("success", False) for row in refits)
            ),
        },
        "limitations": (
            "Truth-free bounded local compact explanation, not an exhaustive profile or proof of "
            "a globally minimal satellite set. Screening tests additions at one displaced nuisance "
            "state and a seven-point timing grid; one add/drop/swap neighborhood is refitted. Weak "
            "or false matches can survive, and low expected support is reported but never used to "
            "cherry-pick."
        ),
        "source_hashes": source_hashes,
        "protocol_sha256": digest(protocol_path),
        "resource_amendment_sha256": digest(amendment_path),
        "source_calibration_sha256": digest(calibration_path),
        "source_parent_sha256": digest(parent_path),
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "budget_s": budget_s,
        "elapsed_s": clock() - started,
        "sealed_utc": datetime.now(UTC).isoformat(),
    }
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(receipt), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "selected_count": len(winner["satellite_indices"]),
        "screened_count": len(screening),
        "candidate_count": len(expanded.numbers),
        "status": selected_fit["status"],
        "ranking_resolved": receipt["resolution"]["ranking_resolved"],
        "elapsed_s": receipt["elapsed_s"],
    }


def load_compact_profile_inputs(session, output_dir=None):
    from all_visible_bank import load_expanded_scan

    output_dir = ROOT / "compact-satellite-selection" if output_dir is None else Path(output_dir)
    path = output_dir / f"{session}.json"
    receipt = json.loads(path.read_text())
    if (
        receipt.get("schema") != "ds13-compact-satellite-selection/v1"
        or receipt.get("session") != session
        or receipt.get("reference_read_before_seal") is not False
    ):
        raise ValueError("invalid compact selection receipt")
    assert_snapshot_unchanged(receipt["source_hashes"])
    data, _ = _unpack_expanded(load_expanded_scan(session))
    satellites = np.asarray(receipt["profile_inputs"]["satellite_indices"], dtype=int)
    parameters = np.asarray(receipt["profile_inputs"]["initial_parameters"], dtype=float)
    if parameters.shape != (6 + len(data.numbers),):
        raise ValueError("compact profile parameters do not match expanded bank")
    np.testing.assert_array_equal(
        np.asarray(data.numbers)[satellites],
        np.asarray(receipt["selected"]["catalog_numbers"]),
    )
    return data, satellites, parameters, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", nargs="*", choices=SESSIONS)
    parser.add_argument("--budget-s", type=float, default=DEFAULT_BUDGET_S)
    args = parser.parse_args()
    sessions = tuple(args.session) or SESSIONS
    with ProcessPoolExecutor(max_workers=min(2, len(sessions))) as executor:
        for result in executor.map(
            _run_case_arguments, [(session, args.budget_s) for session in sessions]
        ):
            print(json.dumps(result), flush=True)


def _run_case_arguments(arguments):
    session, budget_s = arguments
    return run_case(session, budget_s=budget_s)


if __name__ == "__main__":
    main()
