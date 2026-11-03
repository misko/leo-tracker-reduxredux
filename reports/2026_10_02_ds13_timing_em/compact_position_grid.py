"""Nearby-position profiles after frozen all-visible compact satellite selection."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from oracle_position_diagnostic import reference_coordinates
from position_profile_grid import position_grid, run_profile, select_best_attempt
from prepare_scans import ROOT
from rough_smoke import serializable

MAX_SCAN_SECONDS = 385.
STAGE_SECONDS = 6.


def position_receipt(point, attempts):
    index, best = select_best_attempt(attempts)
    compact = [{key: value for key, value in attempt.items()
                if key not in {"group_values", "group_log_likelihood", "satellite_support"}}
               for attempt in attempts]
    return {**point, "fixed_position_km": point["position_km"],
            "best_attempt_index": index, "best": best, "attempts": compact,
            "ranking_resolved": bool(best is not None and best["success"])}


def validate_selection(selection, data):
    indices = np.asarray(selection["satellite_indices"], dtype=int)
    numbers = np.asarray(selection["catalog_numbers"], dtype=int)
    if (indices.ndim != 1 or not len(indices) or len(np.unique(indices)) != len(indices)
            or np.any(indices < 0) or np.any(indices >= len(data.numbers))
            or not np.array_equal(np.asarray(data.numbers)[indices], numbers)):
        raise ValueError("selected satellites do not match expanded bank")
    parameters = np.asarray(selection["fit"]["parameters"], dtype=float)
    if parameters.shape != (6 + len(data.numbers),) or np.any(~np.isfinite(parameters)):
        raise ValueError("selected parameters do not match expanded bank")
    probability = float(selection["detection_probability"])
    if not 0 < probability < 1:
        raise ValueError("selection must declare fixed per-satellite detection probability")
    return indices, parameters, probability


def run_case(session):
    from all_visible_bank import load_expanded_scan

    destination = ROOT / "compact-position-profile-grid" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    selection_path = ROOT / "compact-satellite-selection" / f"{session}.json"
    reference_path = ROOT / "scans" / session / "evaluation.json"
    protocol_path = ROOT / "position-profile-protocol.json"
    selection_record = json.loads(selection_path.read_text())
    selection = selection_record["selected"]
    reference = json.loads(reference_path.read_text())["reference_site"]
    protocol = json.loads(protocol_path.read_text())
    hashes = {**selection_record["source_hashes"], **snapshot_files([
        __file__, selection_path, reference_path, protocol_path,
        ROOT / "position-profile-resource-amendment.json", ROOT / "position_profile_grid.py",
        ROOT / "all_visible_bank.py",
    ])}
    assert_snapshot_unchanged(hashes)
    data = load_expanded_scan(session)
    group_values = np.unique(data.group)
    group_times = np.array([np.median(data.times[data.group == group]) for group in group_values])
    satellites, parameters, probability = validate_selection(selection, data)
    coefficient = selection["fit"]["rf_coefficient_hz_per_ghz"]
    grid = position_grid(reference, protocol["positions"])
    true_position = reference_coordinates(reference["latitude_deg"], reference["longitude_deg"])
    started = time.monotonic()

    def fit(position, current, direction):
        remaining = MAX_SCAN_SECONDS - (time.monotonic() - started)
        if remaining < .25:
            return {"objective": None, "success": False, "status": "scan_budget_not_run",
                    "direction": direction}
        try:
            result = run_profile(data, parameters, satellites, coefficient, position, probability,
                                 start_vector=current, budget_s=min(STAGE_SECONDS, remaining))
            return {**result, "direction": direction}
        except Exception as error:
            return {"objective": None, "success": False, "status": "execution_error",
                    "direction": direction, "error": f"{type(error).__name__}: {error}"}

    displaced = fit(parameters[:2], None, "selected_displaced_start")
    if "vector" not in displaced:
        raise RuntimeError(f"cannot evaluate compact selected state: {displaced}")
    current = np.asarray(displaced["vector"])
    profile_phases = []
    for fraction in (.25, .5, .75, 1.):
        point = (1 - fraction) * parameters[:2] + fraction * true_position
        phase = fit(point, current, "gradual_reference_profile")
        profile_phases.append(phase)
        if "vector" in phase:
            current = np.asarray(phase["vector"])
    truth_attempt = fit(true_position, current, "reference_refinement")
    if "vector" not in truth_attempt:
        raise RuntimeError(f"cannot evaluate compact reference state: {truth_attempt}")
    truth_point = {"label": "truth", "kind": "reference", "bearing_label": None,
                   "bearing_deg": None, "radius_m": 0., "position_km": true_position}
    positions = [position_receipt(truth_point, [truth_attempt])]
    for points in grid.values():
        attempts = {point["label"]: [] for point in points}
        for direction, ordered, initial in (
                ("outward_from_truth", points, truth_attempt["vector"]),
                ("inward_from_displaced", list(reversed(points)), displaced["vector"])):
            current = np.asarray(initial)
            for point in ordered:
                attempt = fit(point["position_km"], current, direction)
                attempts[point["label"]].append(attempt)
                if "vector" in attempt:
                    current = np.asarray(attempt["vector"])
        positions.extend(position_receipt(point, attempts[point["label"]]) for point in points)
    displaced_point = {"label": "displaced_optimum", "kind": "previous_displaced_optimum",
                       "bearing_label": None, "bearing_deg": None, "radius_m": None,
                       "position_km": parameters[:2]}
    positions.append(position_receipt(displaced_point, [displaced]))
    reference_attempts = [truth_attempt]
    reference_starts = [("reference_from_displaced", displaced["vector"])]
    reference_starts.extend(
        (f"reference_from_{point['label']}", point["best"]["vector"])
        for point in positions
        if point.get("radius_m") == 50. and point["best"] is not None)
    for direction, vector in reference_starts:
        reference_attempts.append(fit(true_position, np.asarray(vector), direction))
    positions[0] = position_receipt(truth_point, reference_attempts)
    failed = [point["label"] for point in positions if point["best"] is None]
    result = {
        "schema": "ds13-position-profile-grid/v1", "session": session,
        "model_variant": "compact-all-visible-fixed-set", "positions": positions,
        "source_hashes": hashes, "reference_used_for_fitting": True,
        "sigma_hz": 200., "detection_probability": probability, "clutter_rate": 2.,
        "satellite_indices": satellites, "catalog_numbers": np.asarray(data.numbers)[satellites],
        "row_count": len(data.measured), "group_count": len(np.unique(data.group)),
        "group_values": group_values, "group_time_s": group_times,
        "true_position_km": true_position, "displaced_optimum_position_km": parameters[:2],
        "position_count": len(positions), "completed_position_count": len(positions) - len(failed),
        "complete": not failed, "failed_position_labels": failed,
        "unresolved_position_labels": [point["label"] for point in positions
                                       if not point["ranking_resolved"]],
        "elapsed_s": time.monotonic() - started, "maximum_scan_budget_s": MAX_SCAN_SECONDS,
        "nuisance_profile_phases": profile_phases,
        "set_complexity_constant": selection.get("selection_penalty"),
        "selection_resolution": selection_record.get("resolution"),
        "scope": "Frozen compact set from an all-visible screening and bounded set search. "
                 "Satellite selection is not repeated per position. Per-satellite probability "
                 "is inherited from selection, not renormalized with the new K. The constant "
                 "set penalty cancels in position differences and is excluded from profile NLL. "
                 "Exploratory selection: the count penalty does not correct for identity/timing "
                 "search over hundreds of candidates. Unresolved selection is retained explicitly. "
                 "Reference-informed local diagnostic, not blind validation or global optimality. "
                 "All stored peak frequencies retained; not full GLRT response surfaces.",
    }
    assert_snapshot_unchanged(hashes)
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "complete": result["complete"], "elapsed_s": result["elapsed_s"],
            "unresolved": result["unresolved_position_labels"]}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, sessions):
            print(json.dumps(result), flush=True)
