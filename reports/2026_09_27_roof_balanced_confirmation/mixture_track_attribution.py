"""Additive track-level attribution between two already-chosen positions."""
from __future__ import annotations

import math


def components(scores: dict) -> dict:
    d, detection, joint = (float(scores[name]) for name in
                          ("D", "D_plus_detection", "D_plus_geometry"))
    if not all(math.isfinite(value) for value in (d, detection, joint)):
        raise ValueError("nonfinite track score")
    return {"D": d, "detection_increment": detection - d,
            "ratio_increment": joint - detection, "joint": joint}


def attribute_positions(left: dict, right: dict, variant: str = "mixture") -> dict:
    by_side = []
    for point in (left, right):
        tracks = point["tracks"]
        mapping = {track["track_id"]: track for track in tracks}
        if len(mapping) != len(tracks) or not tracks:
            raise ValueError("duplicate or empty track inventory")
        weights = [float(track["weight_seconds"]) for track in tracks]
        if not all(math.isfinite(weight) and weight > 0 for weight in weights):
            raise ValueError("invalid track weight")
        if not math.isclose(sum(weights), float(point["weight_seconds"]), rel_tol=0, abs_tol=1e-9):
            raise ValueError("aggregate track weight differs")
        by_side.append(mapping)
    a, b = by_side
    if set(a) != set(b) or left["weight_seconds"] != right["weight_seconds"]:
        raise ValueError("position comparison changed track membership or weight")
    total_weight = float(left["weight_seconds"])
    rows = []
    for tid in sorted(a, key=str):
        ta, tb = a[tid], b[tid]
        if ta["weight_seconds"] != tb["weight_seconds"]:
            raise ValueError("position changed a track weight")
        va, vb = ta["variants"][variant], tb["variants"][variant]
        ca, cb = components(va["scores"]), components(vb["scores"])
        fraction = float(ta["weight_seconds"]) / total_weight
        deltas = {name: fraction * (cb[name] - ca[name]) for name in ca}
        rows.append({
            "track_id": tid, "weight_seconds": ta["weight_seconds"],
            "normalized_weight": fraction, "weighted_score_change": deltas,
            "left_candidates": ta["candidate_ids"], "right_candidates": tb["candidate_ids"],
            "shortlist_changed": set(ta["candidate_ids"]) != set(tb["candidate_ids"]),
            "frequency_map_changed": va["frequency_map_candidate_id"] != vb["frequency_map_candidate_id"],
            "joint_map_changed": va["joint_map_candidate_id"] != vb["joint_map_candidate_id"],
            "left_frequency_map": va["frequency_map_candidate_id"],
            "right_frequency_map": vb["frequency_map_candidate_id"],
            "left_joint_map": va["joint_map_candidate_id"],
            "right_joint_map": vb["joint_map_candidate_id"],
            "left_reception_changes_map": va["frequency_map_candidate_id"] != va["joint_map_candidate_id"],
            "right_reception_changes_map": vb["frequency_map_candidate_id"] != vb["joint_map_candidate_id"],
        })
    totals = {name: sum(row["weighted_score_change"][name] for row in rows)
              for name in ("D", "detection_increment", "ratio_increment", "joint")}
    expected_a, expected_b = (components(point["variant_scores"][variant])
                              for point in (left, right))
    for name, value in totals.items():
        if not math.isclose(value, expected_b[name] - expected_a[name], rel_tol=0, abs_tol=1e-9):
            raise ValueError("track contributions do not reproduce aggregate score change")
    return {
        "variant": variant, "tracks": len(rows), "weight_seconds": total_weight,
        "total_score_change": totals,
        "association_change_counts": {name: sum(row[name] for row in rows) for name in
            ("shortlist_changed", "frequency_map_changed", "joint_map_changed",
             "left_reception_changes_map", "right_reception_changes_map")},
        "joint_score_change_by_joint_map_change": {
            name: sum(row["weighted_score_change"]["joint"] for row in rows
                      if row["joint_map_changed"] == changed)
            for name, changed in (("changed", True), ("unchanged", False))},
        "contributions": sorted(rows, key=lambda row: (
            row["weighted_score_change"]["joint"], str(row["track_id"]))),
        "interpretation": "Right minus left score; negative favors right. MAP IDs are model associations, not decoded truth.",
    }
