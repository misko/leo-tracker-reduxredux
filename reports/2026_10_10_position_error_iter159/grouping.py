"""Metadata-only acquisition grouping; disjoint folds do not imply independence."""

import hashlib
import json
from numbers import Integral


IDENTITY_FIELDS = (
    "session_id", "input_manifest_sha256", "raw_recording_authority_digest",
    "radio_id", "stream_generation", "sample_rate_hz",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError("Invalid integer: " + name)
    return int(value)


def fold_for(group_id, seed):
    return int(digest(dict(policy="visit-overlap-two-fold-v1", seed=seed,
                           group_id=group_id)), 16) % 2


def group_support(support, identity, *, seed, maximum_rows=100_000):
    """Group all visits and true half-open interval overlaps, retaining row order.

    The caller must bind identity to the public support adapter's single stream.
    No measured frequency, margin, satellite label or position enters this API.
    Missing authority rejects the entire recording. A single empty fold rejects
    preparation; callers must not search for another seed on recording outcomes.
    """
    maximum_rows = integer(maximum_rows, "maximum_rows", 1)
    if not isinstance(seed, str) or not seed:
        raise ValueError("A predeclared nonempty seed is required")
    bound = {}
    for key in IDENTITY_FIELDS:
        value = identity[key]
        if key == "sample_rate_hz":
            value = integer(value, key, 1)
        elif not isinstance(value, str) or not value:
            raise ValueError("Missing authoritative identity: " + key)
        bound[key] = value
    rows = support["rows"]
    if not isinstance(rows, (list, tuple)) or not 0 < len(rows) <= maximum_rows:
        raise ValueError("Empty or oversized row inventory")
    if integer(support["observations"], "observations") != len(rows):
        raise ValueError("Observation count differs")
    if integer(support["available"], "available") != len(rows):
        raise ValueError("Incomplete support: entire recording rejected")
    if support.get("unavailable_reasons"):
        raise ValueError("Support failure reasons present")
    visits, intervals, windows, candidates, probes = {}, [], set(), set(), set()
    for index, row in enumerate(rows):
        if integer(row["index"], "index") != index:
            raise ValueError("Row index/order differs")
        if row["support_status"] != "available" or row.get("support_reason") is not None:
            raise ValueError("Unavailable support: entire recording rejected")
        visit = integer(row["visit_index"], "visit_index")
        receiver = integer(row["receiver"], "receiver")
        if receiver not in (0, 1):
            raise ValueError("Unsupported receiver")
        probe = integer(row["probe_index"], "probe_index")
        for key, seen in (("window_id", windows), ("candidate_id", candidates)):
            value = row[key]
            if not isinstance(value, str) or not value or value in seen:
                raise ValueError("Missing or duplicate " + key)
            seen.add(value)
        if (visit, receiver, probe) in probes:
            raise ValueError("Duplicate original probe")
        probes.add((visit, receiver, probe))
        start = integer(row["device_sample_start"], "device_sample_start")
        end = integer(row["device_sample_end"], "device_sample_end")
        if end <= start:
            raise ValueError("Empty or reversed support")
        visits.setdefault(visit, []).append(index)
        intervals.append((start, end, visit))

    parent = {visit: visit for visit in visits}

    def find(visit):
        while parent[visit] != visit:
            parent[visit] = parent[parent[visit]]
            visit = parent[visit]
        return visit

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    # Sweep original segments, never the convex hull of a visit's intervals.
    frontier_end, frontier_visit = -1, None
    for start, end, visit in sorted(intervals):
        if start < frontier_end:
            union(visit, frontier_visit)
        if end > frontier_end:
            frontier_end, frontier_visit = end, visit

    components = {}
    for visit in sorted(visits):
        components.setdefault(find(visit), []).append(visit)
    assignments = [None] * len(rows)
    groups = []
    for members in components.values():
        indices = sorted(index for visit in members for index in visits[visit])
        group_id = digest(dict(identity=bound, visits=members,
                               windows=sorted(rows[i]["window_id"] for i in indices),
                               segments=sorted((int(rows[i]["device_sample_start"]),
                                                int(rows[i]["device_sample_end"])) for i in indices)))
        fold = fold_for(group_id, seed)
        groups.append(dict(group_id=group_id, visits=members, row_indices=indices, fold=fold))
        for index in indices:
            assignments[index] = fold
    if set(assignments) != {0, 1}:
        raise ValueError("Both folds must be nonempty; no automatic reseeding")
    return dict(policy="visit-overlap-two-fold-v1", seed=seed, identity=bound,
                groups=groups, row_fold=assignments,
                folds={str(f): [i for i, v in enumerate(assignments) if v == f] for f in (0, 1)},
                observations=len(rows), visits=len(visits), group_count=len(groups),
                scope="Physical overlap isolation, not statistical independence")
