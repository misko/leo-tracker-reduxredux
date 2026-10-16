"""Metadata-only randomized whole-block partitions before track reconstruction."""

import hashlib
import math
from dataclasses import dataclass, replace
from fractions import Fraction

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.scanner_tracking import TrackingInput


@dataclass(frozen=True)
class GroupedProbeHoldout:
    training: TrackingInput
    held: TrackingInput
    quarantined: TrackingInput
    held_blocks: tuple[int, ...]
    # Original probe index, receive-relative counter start/end, assignment.
    assignments: tuple[tuple[int, int, int, str], ...]
    seed: int
    block_seconds: int


def partition_channel_probes(source, *, seed=20261012, block_seconds=20):
    """Keep overlapping envelopes and cross-RX probe families indivisible.

    Every detector candidate stays with its original probe. Neither CFO nor
    margin nor fitted state influences the partition. Original counters, UTC,
    manifest identity and preprocessing settings remain unchanged in each view.
    """
    if not isinstance(source, TrackingInput) or source.timing is None or not source.qualified:
        raise ValueError("qualified original TrackingInput with counter timing required")
    fs = source.sample_rate_hz
    if (
        not isinstance(block_seconds, int)
        or block_seconds < 1
        or not isinstance(seed, int)
        or fs <= 0
        or source.probe_ms <= 0
        or fs * source.probe_ms % 1000
    ):
        raise ValueError("positive integer block/probe sample durations and integer seed required")
    origin = source.timing.session_start_device_sample_counter
    raw, families = [], {}
    for i, probe in enumerate(source.probes):
        if probe.probe_start_ms < 0 or fs * probe.probe_start_ms % 1000:
            raise ValueError("integer nonnegative probe sample offset required")
        start = probe.valid_start_counter - origin + fs * probe.probe_start_ms // 1000
        if start < 0:
            raise ValueError("probe precedes original counter origin")
        raw.append((i, start, start + fs * source.probe_ms // 1000))
        families.setdefault((probe.visit_index, probe.probe_start_ms), []).append(i)
    width = fs * block_seconds
    extent = max((end for _, _, end in raw), default=0)
    eligible = tuple(range(extent // width))
    if len(eligible) < 2:
        raise ValueError("at least two complete metadata-defined blocks required")
    ranking = sorted(
        eligible,
        key=lambda j: hashlib.sha256(
            f"channel-group-holdout|{seed}|{source.input_manifest_sha256}|{j}".encode()
        ).digest(),
    )
    held = tuple(sorted(ranking[: math.ceil(len(eligible) / 5)]))
    selected = set(held)
    labels = [
        "quarantined"
        if start // width != (end - 1) // width
        else "held"
        if start // width in selected
        else "training"
        for _, start, end in raw
    ]
    parent = list(range(len(raw)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        parent[find(b)] = find(a)

    for family in families.values():
        for i in family[1:]:
            join(family[0], i)
    ordered = sorted(raw, key=lambda row: (row[1], row[2], row[0]))
    representative, _, running_end = ordered[0]
    for i, start, end in ordered[1:]:
        if start < running_end:
            join(representative, i)
            running_end = max(running_end, end)
        else:
            representative, running_end = i, end
    component_labels = {}
    for i, label in enumerate(labels):
        component_labels.setdefault(find(i), set()).add(label)
    for i in range(len(labels)):
        component = component_labels[find(i)]
        if len(component) > 1 or "quarantined" in component:
            labels[i] = "quarantined"

    def view(label):
        return replace(
            source,
            probes=tuple(p for p, role in zip(source.probes, labels, strict=True) if role == label),
        )

    return GroupedProbeHoldout(
        view("training"),
        view("held"),
        view("quarantined"),
        held,
        tuple((i, start, end, labels[i]) for i, start, end in raw),
        seed,
        block_seconds,
    )


def verify_holdout_support(source, split):
    """Check newly unsuppressed child projections, not just full-data winners."""
    lookup = {}
    for index, start, end, role in split.assignments:
        probe = source.probes[index]
        key = (probe.visit_index, probe.receiver_id, probe.probe_index)
        if key in lookup:
            raise ValueError("duplicate original probe identity")
        lookup[key] = (probe, start, end, role)
    fs = source.sample_rate_hz
    origin_utc = source.timing.first_sample_estimate_utc_ns
    counts = {}
    for role, view in (
        ("original", source),
        ("training", split.training),
        ("held", split.held),
        ("quarantined", split.quarantined),
    ):
        points = project_scanner_candidates(view)
        counts[role] = len(points)
        for point in points:
            probe, start, end, assigned = lookup[
                (point.visit_index, point.receiver_id, point.probe_index)
            ]
            if role != "original" and role != assigned:
                raise ValueError("child projection escaped its whole-probe partition")
            payload_start = probe.payload_start_sample + fs * probe.probe_start_ms // 1000
            payload_end = payload_start + fs * source.probe_ms // 1000
            if (
                not payload_start
                <= point.source_sample_start
                < point.source_sample_end
                <= payload_end
            ):
                raise ValueError("projected samples outside original probe envelope")
            start_ns = origin_utc + round(Fraction(start * 10**9, fs))
            end_ns = origin_utc + round(Fraction(end * 10**9, fs))
            if (
                not start_ns - 1
                <= point.support_start_utc_ns
                <= point.support_end_utc_ns
                <= end_ns + 1
            ):
                raise ValueError("projected UTC outside original probe envelope")
    return counts
