"""Training-only source grouping and starts for cross-dataset position fits."""

import math


def layout(groups, omitted=None):
    identifiers = [g["dataset_id"] for g in groups]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate dataset")
    if omitted is not None and omitted not in identifiers:
        raise ValueError("unknown excluded dataset")
    selected = [g for g in groups if g["dataset_id"] != omitted]
    if len(selected) < 2:
        raise ValueError("at least two source datasets required")
    sessions, timings = [], []
    for group in selected:
        point = group["point"]
        if len(point) != 2 + len(group["session_ids"]) or not all(math.isfinite(v) for v in point):
            raise ValueError("source point dimensions or values invalid")
        sessions.extend(group["session_ids"])
        timings.extend(point[2:])
    if len(set(sessions)) != len(sessions):
        raise ValueError("duplicate source recording")
    return {
        "source_datasets": [g["dataset_id"] for g in selected],
        "session_ids": sessions,
        "starts": [
            {"source_dataset": g["dataset_id"], "x": list(g["point"][:2]) + timings}
            for g in selected
        ],
    }
