"""Exact descriptive track attribution between independently fitted positions."""
import math

ARMS = ("D", "D_plus_detection", "D_plus_geometry", "D_plus_reversed_geometry")


def inventory(point, variant):
    rows = point.get("tracks", [])
    tracks = {row["track_id"]: row for row in rows}
    if not rows or len(tracks) != len(rows):
        raise ValueError("missing or duplicate diagnostic tracks")
    total = sum(float(row["weight_seconds"]) for row in rows)
    if not math.isfinite(total) or total <= 0 or total != point["weight_seconds"]:
        raise ValueError("invalid diagnostic total weight")
    scores = point["variant_scores"][variant]
    if set(scores) != set(ARMS):
        raise ValueError("invalid aggregate score inventory")
    for row in rows:
        weight = float(row["weight_seconds"])
        values = row["variants"][variant]["scores"]
        if (not math.isfinite(weight) or weight <= 0 or
                row["reserve_observations"] <= 0 or set(values) != set(ARMS) or
                not all(math.isfinite(float(v)) for v in values.values())):
            raise ValueError("invalid track weight/count/scores")
    for arm in ARMS:
        reconstructed = math.fsum(float(row["weight_seconds"]) *
                                  row["variants"][variant]["scores"][arm]
                                  for row in rows) / total
        if not math.isfinite(scores[arm]) or abs(reconstructed - scores[arm]) > 1e-10:
            raise ValueError("track scores do not reconstruct aggregate")
    return tracks, total


def compare(left, right, variant="dual"):
    """Right-minus-left; a negative joint delta favors the right position."""
    a, wa = inventory(left, variant); b, wb = inventory(right, variant)
    if set(a) != set(b) or wa != wb:
        raise ValueError("point track inventory or weights changed")
    rows = []
    for tid, before in a.items():
        after = b[tid]
        if (before["weight_seconds"] != after["weight_seconds"] or
                before["reserve_observations"] != after["reserve_observations"]):
            raise ValueError("track weight/reserve count changed")
        av = before["variants"][variant]; bv = after["variants"][variant]
        w = before["weight_seconds"] / wa
        delta = {arm: w * (bv["scores"][arm] - av["scores"][arm]) for arm in ARMS}
        rows.append({"track_id": tid, "normalized_weight": w,
            "shortlist_changed": set(before["candidate_ids"]) != set(after["candidate_ids"]),
            "training_map_changed": before["training_prior"]["map_candidate_id"] !=
                                    after["training_prior"]["map_candidate_id"],
            "frequency_map_changed": av["frequency_map_candidate_id"] != bv["frequency_map_candidate_id"],
            "joint_map_changed": av["joint_map_candidate_id"] != bv["joint_map_candidate_id"],
            "frequency_map_ids": [av["frequency_map_candidate_id"], bv["frequency_map_candidate_id"]],
            "joint_map_ids": [av["joint_map_candidate_id"], bv["joint_map_candidate_id"]],
            "delta_D": delta["D"],
            "delta_detection_increment": delta["D_plus_detection"] - delta["D"],
            "delta_conditional_ratio_increment": delta["D_plus_geometry"] - delta["D_plus_detection"],
            "delta_joint": delta["D_plus_geometry"],
            "delta_reversed_joint": delta["D_plus_reversed_geometry"]})
    totals = {key: math.fsum(row[key] for row in rows) for key in (
        "delta_D", "delta_detection_increment", "delta_conditional_ratio_increment",
        "delta_joint", "delta_reversed_joint")}
    expected = right["variant_scores"][variant]["D_plus_geometry"] - left["variant_scores"][variant]["D_plus_geometry"]
    if abs(totals["delta_joint"] - expected) > 1e-10:
        raise ValueError("delta attribution does not reconstruct joint score")
    groups = {}
    for changed in (False, True):
        selected = [r for r in rows if r["joint_map_changed"] == changed]
        groups["joint_map_changed" if changed else "joint_map_stable"] = {
            "tracks": len(selected),
            **{key: math.fsum(row[key] for row in selected) for key in totals}}
    return {"variant": variant, "track_count": len(rows),
            "changes": {key: sum(row[key] for row in rows) for key in (
                "shortlist_changed", "training_map_changed", "frequency_map_changed", "joint_map_changed")},
            "totals": totals, "groups": groups, "tracks": rows,
            "caveat": "Stable MAP does not imply fixed mixture weights or decoded identity; increments are telescoping joint-likelihood terms."}
