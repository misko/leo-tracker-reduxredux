"""Give the reference position the nuisance starts available to nearby alternatives."""

from __future__ import annotations

import argparse
import copy
import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from position_profile_grid import run_profile, select_best_attempt
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable


def reference_starts(positions):
    return [point for point in positions if point.get("radius_m") == 50.
            or point["label"] == "displaced_optimum"]


def balance(session):
    source_path = ROOT / "position-profile-grid" / f"{session}.json"
    destination = ROOT / "reference-profile-balance" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    source = json.loads(source_path.read_text())
    hashes = {**source["source_hashes"], **snapshot_files([__file__, source_path])}
    assert_snapshot_unchanged(hashes)
    _, data = load_scan(session)
    truth = next(point for point in source["positions"] if point["label"] == "truth")
    attempts = [truth["best"]]
    for point in reference_starts(source["positions"]):
        seed = point["best"]
        try:
            fit = run_profile(
                data, seed["parameters"], source["satellite_indices"],
                seed["rf_coefficient_hz_per_ghz"], truth["fixed_position_km"],
                start_vector=np.asarray(seed["vector"]), budget_s=6.)
            attempts.append({**fit, "direction": f"reference_from_{point['label']}"})
        except Exception as error:
            attempts.append({"objective": None, "success": False, "status": "execution_error",
                             "error": f"{type(error).__name__}: {error}",
                             "direction": f"reference_from_{point['label']}"})
    index, best = select_best_attempt(attempts)
    result = {"schema": "ds13-reference-profile-balance/v1", "session": session,
              "source_hashes": hashes, "best": best, "best_attempt_index": index,
              "attempts": attempts, "original_objective": truth["best"]["objective"],
              "reference_objective_improvement": truth["best"]["objective"] - best["objective"],
              "scope": "Same reference is profiled from each ray's retained 50m state and the "
                       "displaced state, retaining its original gradually profiled state too. "
                       "This balances tested nuisance starts, not all possible nuisance basins."}
    assert_snapshot_unchanged(hashes)
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "improvement": result["reference_objective_improvement"],
            "success": best["success"], "attempts": len(attempts)}


def merge_positions(original, balanced, refined):
    result = copy.deepcopy(original)
    updates = {point["label"]: point for point in refined.get("positions", [])}
    for point in result["positions"]:
        if point["label"] in updates:
            update = updates[point["label"]]
            point["best"] = update["best"]
            point["attempts"].extend(update["refinement_attempts"])
            point["ranking_resolved"] = update["ranking_resolved"]
            point["refinement_selected_from"] = update["selected_from"]
        if point["label"] == "truth":
            point["best"] = balanced["best"]
            point["attempts"] = balanced["attempts"]
            point["best_attempt_index"] = balanced["best_attempt_index"]
            point["ranking_resolved"] = bool(balanced["best"]["success"])
    result["unresolved_position_labels"] = [point["label"] for point in result["positions"]
                                             if not point["ranking_resolved"]]
    return result


def merge(session):
    original_path = ROOT / "position-profile-grid" / f"{session}.json"
    balanced_path = ROOT / "reference-profile-balance" / f"{session}.json"
    refined_path = ROOT / "position-profile-refinement" / f"{session}.json"
    destination = ROOT / "position-profile-balanced" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    paths = [original_path, balanced_path]
    original, balanced = [json.loads(path.read_text()) for path in paths]
    refined = {}
    if session.endswith("c09f"):
        refined = json.loads(refined_path.read_text())
        paths.append(refined_path)
    hashes = {}
    for record in (original, balanced, refined):
        hashes.update(record.get("source_hashes", {}))
    hashes.update(snapshot_files([__file__, *paths]))
    assert_snapshot_unchanged(hashes)
    result = merge_positions(original, balanced, refined)
    result.update(source_hashes=hashes, reference_search_balanced=True,
                  reference_objective_improvement=balanced["reference_objective_improvement"])
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "unresolved": result["unresolved_position_labels"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("balance", "merge"))
    args = parser.parse_args()
    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for row in executor.map(balance if args.action == "balance" else merge, sessions):
            print(json.dumps(row), flush=True)
