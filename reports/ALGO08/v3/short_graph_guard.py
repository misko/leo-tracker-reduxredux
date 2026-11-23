"""Sufficient lane-count proof for the pinned installed track graph."""

from collections import Counter, defaultdict
from hashlib import sha256
import hashlib
import json
from math import isfinite
from pathlib import Path


RELEASE_PINS = {
    "leo/analysis/glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
    "leo/analysis/graph_tracklets.py": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "leo/analysis/polynomial_tracklets.py": "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922",
    "leo/analysis/tracklet_fitting.py": "8e3917e1bb94bf59e37d97a7a3782254612e459d36075f67acfdfe15b3a19414",
    "leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
}
TRACKS = "leo/analysis/localization_v3/tracks.py"
TRACK_CONFIG = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"


def lane_counts(rows, minimum):
    """The installed graph never receives points from two different keys."""
    if type(minimum) is not int or minimum < 3:
        raise ValueError("The installed graph needs a reviewed minimum point count")
    counts = Counter((r["actual_rf_hz"], r["receiver"], r["channel"]) for r in rows)
    return dict(proven=all(n < minimum for n in counts.values()), minimum_points=minimum,
                winning_rows=len(rows), lanes=[dict(actual_rf_hz=rf, receiver=rx, channel=ch, rows=n)
                                               for (rf, rx, ch), n in sorted(counts.items())])


def time_support(rows, minimum, min_span_s, max_gap_s):
    """Upper bound on each graph seed under the pinned time-only edge constraints."""
    if (type(minimum) is not int or minimum < 3 or not isfinite(min_span_s)
            or not isfinite(max_gap_s) or min_span_s <= 0 or max_gap_s <= 0):
        raise ValueError("Invalid graph time constraints")
    lanes = defaultdict(list)
    for row in rows:
        t = float(row["time_s"])
        if not isfinite(t):
            raise ValueError("Invalid observation time")
        lanes[row["actual_rf_hz"], row["receiver"], row["channel"]].append(t)
    largest_span = 0.0
    for times in lanes.values():
        if len(times) < minimum:
            continue
        times.sort()
        start = 0
        for index, t in enumerate(times):
            # Match searchsorted(t, t[target] - max_gap_s) in the pinned graph.
            if index and times[index - 1] < t - max_gap_s:
                start = index
            if index - start + 1 >= minimum:
                span = t - times[start]
                largest_span = max(largest_span, span)
                if span >= min_span_s:
                    return dict(proven=False, possible_time_support=True)
    return dict(proven=True, possible_time_support=False, largest_eligible_count_span_s=largest_span)


def prove(native, assets, *, use_time_support=False):
    import numpy as np
    import empty_bootstrap as staged
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.digests import canonical_digest

    src = staged.RELEASE / "src"
    try:
        if Path(frequency_evidence.__code__.co_filename).resolve() != src / "leo/analysis/glrt_frequency_input.py":
            raise ValueError("Unrecognized frequency adapter")
        sources = {name: staged.checked(src / name, pin) for name, pin in RELEASE_PINS.items()}
        config = json.loads(staged.checked(assets / "tracks.json", TRACK_CONFIG))["config"]
        scope = dict(np=np, hashlib=hashlib, frequency_evidence=frequency_evidence)
        staged.load_definitions(sources[TRACKS], src / TRACKS, ("winning_observations",), scope)
        rows, metadata = scope["winning_observations"](native)
        counts = lane_counts(rows, config["min_points"])
        if use_time_support and not counts["proven"] and len(rows) <= 256:
            bounds = {key: config[key] for key in ("min_span_s", "max_gap_s")}
            counts.update(time_support(rows, config["min_points"], **bounds), **bounds)
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        return dict(proven=False, reason=f"could not certify installed graph: {exc}")
    return dict(counts, causal_cutoff_utc_ns=metadata["causal_cutoff_utc_ns"],
                native_sha256=canonical_digest(native) if counts["proven"] else None,
                release_sources=RELEASE_PINS, track_config_sha256=TRACK_CONFIG,
                implementation_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
