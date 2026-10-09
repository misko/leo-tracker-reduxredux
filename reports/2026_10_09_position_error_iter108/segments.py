"""Reference-free bootstrap-track segmentation; no orbit or assignment inputs."""

import numpy as np


def prepare_segments(bootstrap_tracks, observations):
    """Pack each unique observation once; link only adjacent eligible track rows.

    Overlap/uncovered rows are singleton independent segments. Excluded overlap
    rows break their original tracks, so removal cannot invent a bridging edge.
    Returned inverse_permutation scatters packed outputs to original row order.
    """
    times = np.asarray(observations.times_s, float)
    receiver = np.asarray(observations.receiver)
    channel = np.asarray(observations.channel)
    rf = np.asarray(observations.rf_hz, float)
    n = len(times)
    if n == 0 or any(x.shape != (n,) for x in (times, receiver, channel, rf)):
        raise ValueError("Nonempty equal-length one-dimensional observation arrays required")
    if not all(np.isfinite(x).all() for x in (times, receiver, channel, rf)):
        raise ValueError("Finite observation metadata required")
    tracks = []
    membership = np.zeros(n, dtype=int)
    for track in bootstrap_tracks:
        rows = list(track)
        if any(
            isinstance(i, (bool, np.bool_)) or not isinstance(i, (int, np.integer)) for i in rows
        ):
            raise ValueError("Track memberships must be integer row indices")
        if len(rows) != len(set(rows)) or any(i < 0 or i >= n for i in rows):
            raise ValueError("Track memberships must be unique and in range")
        rows = tuple(sorted(rows, key=lambda i: (times[i], i)))
        tracks.append(rows)
        membership[list(rows)] += 1
    # Canonical ordering makes packing invariant to supplied track enumeration.
    tracks.sort()
    segments = []
    breaks = dict(overlap=0, receiver=0, channel=0, rf=0, nonpositive_gap=0, gap_over_2s=0)
    links = 0
    for rows in tracks:
        current = []
        for row in rows:
            if membership[row] != 1:
                breaks["overlap"] += 1
                if current:
                    segments.append(tuple(current))
                    current = []
                continue
            reasons = []
            if current:
                previous = current[-1]
                gap = times[row] - times[previous]
                if receiver[row] != receiver[previous]:
                    reasons.append("receiver")
                if channel[row] != channel[previous]:
                    reasons.append("channel")
                if rf[row] != rf[previous]:
                    reasons.append("rf")
                if gap <= 0:
                    reasons.append("nonpositive_gap")
                if gap > 2:
                    reasons.append("gap_over_2s")
                if reasons:
                    for reason in reasons:
                        breaks[reason] += 1
                    segments.append(tuple(current))
                    current = []
                else:
                    links += 1
            current.append(row)
        if current:
            segments.append(tuple(current))
    segments.extend((int(row),) for row in np.flatnonzero(membership != 1))
    segments.sort(key=lambda rows: (times[rows[0]], rows[0], rows))
    permutation = np.asarray([row for segment in segments for row in segment], dtype=int)
    assert np.array_equal(np.sort(permutation), np.arange(n))
    reset = np.zeros(n, dtype=bool)
    offset = 0
    for segment in segments:
        reset[offset] = True
        offset += len(segment)
    inverse = np.argsort(permutation)
    counts = dict(
        observations=n,
        tracks=len(tracks),
        uncovered_rows=int(sum(membership == 0)),
        overlapping_rows=int(sum(membership > 1)),
        unique_membership_rows=int(sum(membership == 1)),
        segments=len(segments),
        singleton_segments=sum(len(s) == 1 for s in segments),
        linked_segments=sum(len(s) > 1 for s in segments),
        eligible_links=links,
        eligible_rows=sum(len(s) for s in segments if len(s) > 1),
        independent_rows=sum(len(s) == 1 for s in segments),
        boundaries=breaks,
        boundary_count_convention="Reasons can overlap; overlap counts per-track occurrences",
    )
    assert links == sum(len(s) - 1 for s in segments)
    return dict(
        permutation=permutation,
        inverse_permutation=inverse,
        reset=reset,
        segments=tuple(segments),
        counts=counts,
    )
