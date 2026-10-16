"""Exact native detector branches through the public scanner projection port."""

from collections import defaultdict

import numpy as np

from leo.analysis.joint_association_score import NativeBranchEvidence
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.application.scanner_trajectory import project_scanner_candidates


def native_branch_inputs(source, observations, *, waveform_rows=()):
    """Bind all passing native CFO proposals to fixed physical ambiguity slots.

    Slot labels are nearest integers on the original OFDM ambiguity lattice,
    after canonicalizing only the sampling ambiguity. Within the same ambiguity
    cell, original margin/rank/ID selects a single acquisition hypothesis. This
    policy uses neither ephemerides nor fitted frequencies nor held evidence.
    """
    points = defaultdict(list)
    for point in project_scanner_candidates(source):
        points[point.source_group_id].append(point)
    selected = []
    all_labels = set()
    for window_id in observations.window_ids:
        branches = {}
        for point in points[window_id]:
            cfo = point.measured_cfo_hz
            canonical = (cfo + source.sample_rate_hz / 2) % source.sample_rate_hz
            canonical -= source.sample_rate_hz / 2
            label = int(np.floor(canonical / ALIAS_HZ + 0.5))
            old = branches.get(label)
            if old is None or (-point.margin, point.candidate_rank, point.candidate_id) < (
                -old.margin,
                old.candidate_rank,
                old.candidate_id,
            ):
                branches[label] = point
        if not branches:
            raise ValueError("original observation lacks its bound native candidates")
        selected.append(branches)
        all_labels.update(branches)
    labels = sorted(all_labels)
    shape = len(selected), len(labels)
    ids = [[""] * len(labels) for _ in selected]
    cfo = np.zeros(shape)
    times = np.repeat(observations.times_s[:, None], len(labels), axis=1)
    waveform = np.zeros(shape)
    measured = np.zeros(shape, bool)
    evidence = {}
    for row in waveform_rows:
        key = row["candidate_id"]
        if key in evidence:
            raise ValueError("duplicate candidate waveform evidence")
        evidence[key] = row
    used = set()
    families = []
    for i, branches in enumerate(selected):
        representative = next(iter(branches.values()))
        families.append(
            (
                representative.receiver_id,
                representative.channel,
                representative.visit_index,
                representative.actual_rf_hz,
            )
        )
        for j, label in enumerate(labels):
            if label not in branches:
                continue
            point = branches[label]
            ids[i][j] = point.candidate_id
            cfo[i, j] = point.measured_cfo_hz
            times[i, j] = (
                point.support_center_utc_ns - source.timing.first_sample_estimate_utc_ns
            ) / 1e9
            row = evidence.get(point.candidate_id)
            if row is not None:
                if (
                    row["window_id"] != observations.window_ids[i]
                    or row["native_cfo_hz"] != point.measured_cfo_hz
                ):
                    raise ValueError("waveform evidence is not bound to the exact native branch")
                waveform[i, j] = row["log_weight"]
                measured[i, j] = True
                used.add(point.candidate_id)
    if used != set(evidence):
        raise ValueError("waveform evidence contains branches outside this native input view")
    return (
        NativeBranchEvidence(tuple(map(tuple, ids)), cfo, waveform, measured, times),
        families,
        labels,
    )
