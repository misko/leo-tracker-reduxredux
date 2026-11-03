"""Parallel fixed-set position profiles after bounded iterative satellite pruning."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

from compact_position_grid import position_receipt, validate_selection
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from position_profile_grid import run_profile
from prepare_scans import ROOT
from rough_smoke import serializable


def profile_seeds(point, selection):
    return [("previous_compact_at_position", point["best"]),
            ("pruned_at_displaced_position", selection["fit"])]


@lru_cache(maxsize=2)
def inputs(session):
    from all_visible_bank import load_expanded_scan

    selection_path = ROOT / "compact-satellite-pruned" / f"{session}.json"
    previous_path = ROOT / "compact-position-profile-grid" / f"{session}.json"
    selection = json.loads(selection_path.read_text())
    previous = json.loads(previous_path.read_text())
    hashes = {**selection["source_hashes"], **previous["source_hashes"], **snapshot_files([
        __file__, selection_path, previous_path, ROOT / "compact_position_grid.py",
        ROOT / "position-profile-resource-amendment.json",
    ])}
    assert_snapshot_unchanged(hashes)
    data = load_expanded_scan(session)
    validate_selection(selection["selected"], data)
    return data, selection, previous, hashes


def run_cell(cell):
    session, label = cell
    data, selection, previous, _ = inputs(session)
    selected = selection["selected"]
    point = next(point for point in previous["positions"] if point["label"] == label)
    attempts = []
    for direction, seed in profile_seeds(point, selected):
        try:
            fitted = run_profile(
                data, seed["parameters"], selected["satellite_indices"],
                seed["rf_coefficient_hz_per_ghz"], point["fixed_position_km"],
                selected["detection_probability"], budget_s=6.)
            attempts.append({**fitted, "direction": direction})
        except Exception as error:
            attempts.append({"objective": None, "success": False, "status": "execution_error",
                             "direction": direction, "error": f"{type(error).__name__}: {error}"})
    point = {key: point[key] for key in (
        "label", "kind", "bearing_label", "bearing_deg", "radius_m", "position_km")}
    return session, position_receipt(point, attempts)


def main():
    sessions = json.loads((ROOT / "position-profile-protocol.json").read_text())["sessions"]
    directory = ROOT / "pruned-position-profile-grid"
    tasks = []
    for session in sessions:
        if (directory / f"{session}.json").exists():
            raise FileExistsError(directory / f"{session}.json")
        _, _, previous, _ = inputs(session)
        tasks.extend((session, point["label"]) for point in previous["positions"])
    started = time.monotonic()
    results = {session: [] for session in sessions}
    with ProcessPoolExecutor(max_workers=8) as executor:
        for session, point in executor.map(run_cell, tasks):
            results[session].append(point)
    directory.mkdir(exist_ok=True)
    for session in sessions:
        _, selection, previous, hashes = inputs(session)
        selected = selection["selected"]
        positions = results[session]
        failed = [point["label"] for point in positions if point["best"] is None]
        result = {**previous, "positions": positions, "source_hashes": hashes,
                  "model_variant": "all-visible-iteratively-pruned-fixed-set",
                  "satellite_indices": selected["satellite_indices"],
                  "catalog_numbers": selected["catalog_numbers"],
                  "detection_probability": selected["detection_probability"],
                  "set_complexity_constant": selected.get("selection_penalty"),
                  "selection_resolution": selection.get("resolution"),
                  "completed_position_count": len(positions) - len(failed),
                  "complete": not failed, "failed_position_labels": failed,
                  "unresolved_position_labels": [point["label"] for point in positions
                                                 if not point["ranking_resolved"]],
                  "elapsed_s": time.monotonic() - started, "maximum_numerical_workers": 8,
                  "profile_initialization": "Every position including reference gets two starts: "
                                            "previous compact solution at that position, and the "
                                            "pruned displaced fit; no global claim."}
        result.pop("nuisance_profile_phases", None)
        result.pop("maximum_scan_budget_s", None)
        result["maximum_fit_seconds_per_cell"] = 12.
        assert_snapshot_unchanged(hashes)
        with (directory / f"{session}.json").open("x") as stream:
            json.dump(serializable(result), stream, indent=2, allow_nan=False)
        print(json.dumps({"session": session, "satellites": len(selected["satellite_indices"]),
                          "unresolved": result["unresolved_position_labels"],
                          "elapsed_s": result["elapsed_s"]}), flush=True)


if __name__ == "__main__":
    main()
