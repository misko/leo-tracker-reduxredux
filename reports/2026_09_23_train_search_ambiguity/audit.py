#!/usr/bin/env python3
"""Audit ambiguity in saved TRAIN blind-search traces without fitting."""

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
HERE = Path(__file__).parent
LEVELS = (100.0, 50.0, 25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125)


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def diverse(rows, spacing, count=3):
    retained = []
    for row in sorted(rows, key=lambda x: (x["objective_rmse_hz"], x["east_km"], x["north_km"])):
        if all(
            np.hypot(row["east_km"] - old["east_km"], row["north_km"] - old["north_km"]) >= spacing
            for old in retained
        ):
            retained.append(row)
        if len(retained) == count:
            break
    return retained


def replay(trace):
    beam = []
    history = []
    for level in LEVELS:
        new = [row for row in trace if row["level_km"] == level]
        beam = diverse(new if not beam else beam + new, level)
        history.append({"level_km": level, "retained_count": len(beam), "beam": beam})
    return history


def identity_map(search):
    if "scans" not in search["selected"]:
        return {
            ("single", track["track_id"]): track["candidate_id"]
            for track in search["selected"]["tracks"]
        }
    return {
        (scan["session_id"], track["track_id"]): track["candidate_id"]
        for scan in search["selected"]["scans"]
        for track in scan["tracks"]
    }


def rows_from_inputs(first, second):
    rows = []
    for search in first["searches"]:
        rows.append(("first_train", 1, search))
    for view in first.get("views", []):
        for search in view["searches"]:
            rows.append(("first_train", view["scan_count"], search))
    for arm in second["arms"]:
        if arm["scan_count"] in (1, 6, 16):
            rows.append(("second_train", arm["scan_count"], arm["search"]))
    return rows


def main():
    first_one_path = ROOT / "reports/2026_09_23_long_training_search/results/results.json"
    first_multi_path = ROOT / "reports/2026_09_23_long_training_search_multi/results/results.json"
    second_path = ROOT / "reports/2026_09_23_long_second8h_training_baseline/results/results.json"
    first_one = json.loads(first_one_path.read_text())
    first_multi = json.loads(first_multi_path.read_text())
    second = json.loads(second_path.read_text())
    packed = {"searches": first_one["searches"], "views": first_multi["views"]}
    source = rows_from_inputs(packed, second)
    arms = []
    for group, count, search in source:
        history = replay(search["trace"])
        beam = history[-1]["beam"]
        best = beam[0]
        arms.append(
            {
                "group": group,
                "scan_count": count,
                "prior": search["prior"],
                "evaluations": search["evaluations"],
                "selected_latitude_deg": search["selected"]["latitude_deg"],
                "selected_longitude_deg": search["selected"]["longitude_deg"],
                "selected_objective_rmse_hz": search["selected"]["objective_rmse_hz"],
                "selected_origin_level_km": next(
                    row["level_km"]
                    for row in search["trace"]
                    if row["east_km"] == search["selected"]["east_km"]
                    and row["north_km"] == search["selected"]["north_km"]
                ),
                "new_evaluation_count_by_level": {
                    str(level): sum(row["level_km"] == level for row in search["trace"])
                    for level in LEVELS
                },
                "final_beam": [
                    {
                        **row,
                        "objective_gap_hz": row["objective_rmse_hz"] - best["objective_rmse_hz"],
                        "separation_from_best_km": float(
                            np.hypot(
                                row["east_km"] - best["east_km"], row["north_km"] - best["north_km"]
                            )
                        ),
                    }
                    for row in beam
                ],
                "beam_history": history,
                "identities": identity_map(search),
            }
        )
    comparisons = []
    for group in ("first_train", "second_train"):
        for count in (1, 6, 16):
            pair = [row for row in arms if row["group"] == group and row["scan_count"] == count]
            if len(pair) != 2:
                continue
            a, b = sorted(pair, key=lambda row: row["prior"])
            common = set(a["identities"]) & set(b["identities"])
            same = sum(a["identities"][key] == b["identities"][key] for key in common)
            comparisons.append(
                {
                    "group": group,
                    "scan_count": count,
                    "coordinate_separation_km": float(
                        6371.0088
                        * 2
                        * np.arcsin(
                            np.sqrt(
                                np.sin(
                                    np.radians(
                                        b["selected_latitude_deg"] - a["selected_latitude_deg"]
                                    )
                                    / 2
                                )
                                ** 2
                                + np.cos(np.radians(a["selected_latitude_deg"]))
                                * np.cos(np.radians(b["selected_latitude_deg"]))
                                * np.sin(
                                    np.radians(
                                        b["selected_longitude_deg"] - a["selected_longitude_deg"]
                                    )
                                    / 2
                                )
                                ** 2
                            )
                        )
                    ),
                    "common_track_count": len(common),
                    "same_candidate_fraction": same / len(common) if common else None,
                    "objective_difference_hz": abs(
                        a["selected_objective_rmse_hz"] - b["selected_objective_rmse_hz"]
                    ),
                }
            )
    for arm in arms:
        arm.pop("identities")
    result = {
        "schema": "train-saved-search-ambiguity/v1",
        "truth_used": False,
        "model_fits_run": False,
        "arms": arms,
        "prior_comparisons": comparisons,
        "bindings": {
            "first_one": digest(first_one_path),
            "first_multi": digest(first_multi_path),
            "second": digest(second_path),
            "tool": digest(Path(__file__)),
            "protocol": digest(HERE / "PROTOCOL.md"),
            "geometry_notes": digest(ROOT / "deploy/station/GEOMETRY_NOTES.md"),
            "geometry_manifest": digest(
                ROOT / "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json"
            ),
        },
    }
    path = HERE / "results.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (HERE / "results.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


if __name__ == "__main__":
    main()
