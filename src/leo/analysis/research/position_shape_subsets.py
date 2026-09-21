"""Truth-blind nested sample budgets that preserve within-track time separation.

RF metadata only: no residuals, satellite identities, or receiver location.
Tracks are drawn without replacement with probability weighted by time span,
stratified over campaign time. Each contributes a packet of separated points.
"""

from __future__ import annotations

import math
from collections import defaultdict

from leo.analysis.research.position_subsets import Observation, _hash_order


def shape_preserving_order(
    observations: tuple[Observation, ...],
    *,
    seed: int,
    packet_size: int = 3,
    temporal_bins: int = 8,
) -> tuple[str, ...]:
    """Return all training IDs once; prefixes implement exact nested budgets.

    The last packet may be incomplete. Spans determine weights, not an inferred
    position or a post-fit quality score. Subsequent passes fill remaining points.
    """
    if packet_size < 2 or temporal_bins < 1:
        raise ValueError("packet_size >= 2 and temporal_bins >= 1 required")
    ids = [row.observation_id for row in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate observation IDs")
    tracks = defaultdict(list)
    for row in observations:
        if row.fitting:
            tracks[row.track_id].append(row)
    if not tracks:
        return ()
    start = min(row.timestamp_ns for rows in tracks.values() for row in rows)
    end = max(row.timestamp_ns for rows in tracks.values() for row in rows)
    strata = defaultdict(list)
    ordered_points = {}
    for track, rows in tracks.items():
        rows.sort(key=lambda row: (row.timestamp_ns, row.observation_id))
        span = (rows[-1].timestamp_ns - rows[0].timestamp_ns) / 1e9
        midpoint = (rows[0].timestamp_ns + rows[-1].timestamp_ns) // 2
        bin_index = min(
            temporal_bins - 1, (midpoint - start) * temporal_bins // max(1, end - start)
        )
        digest = _hash_order(seed, "shape-track-priority-v1", track)
        uniform = (int.from_bytes(digest[:8], "big") + 1) / (2**64 + 1)
        # Exponential race: span-weighted sampling without replacement.
        priority = -math.log(uniform) / max(span, 1e-9)
        strata[bin_index].append((priority, track))
        # Farthest-point temporal traversal starts with the earliest point;
        # the second is the latest, subsequent points fill the largest gaps.
        remaining = list(rows)
        selected = [remaining.pop(0)]
        while remaining:
            chosen = max(
                range(len(remaining)),
                key=lambda i: (
                    min(abs(remaining[i].timestamp_ns - r.timestamp_ns) for r in selected),
                    _hash_order(seed, "shape-point-tie-v1", remaining[i].observation_id),
                ),
            )
            selected.append(remaining.pop(chosen))
        ordered_points[track] = [r.observation_id for r in selected]
    for rows in strata.values():
        rows.sort()
    bin_order = sorted(strata, key=lambda b: _hash_order(seed, "shape-bin-v1", str(b)))
    track_order = [
        strata[b][i][1]
        for i in range(max(map(len, strata.values())))
        for b in bin_order
        if i < len(strata[b])
    ]
    output = []
    for offset in range(0, max(map(len, ordered_points.values())), packet_size):
        for track in track_order:
            output.extend(ordered_points[track][offset : offset + packet_size])
    return tuple(output)
