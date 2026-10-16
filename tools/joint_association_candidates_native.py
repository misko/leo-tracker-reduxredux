"""All passing native proposals through the original scanner projection port."""

from collections import defaultdict

import numpy as np

from leo.analysis.joint_association_score import NativeBranchEvidence
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.application.scanner_trajectory import project_scanner_candidates

POLICY = "all-passing-native-within-cell-alternatives-v1"


def all_native_candidate_inputs(source, observations):
    """Preserve exact IDs/CFOs/times; packed slots assert no across-window identity.

    Only the caller's original window inventory is used. Ordering is fixed by
    sampling-canonical OFDM cell, original candidate rank and candidate ID.
    Waveform remains explicitly unmeasured; fixed cell priors belong to the
    separate candidate objective, not the waveform-evidence field.
    """
    fs = source.sample_rate_hz
    if not np.isfinite(fs) or fs <= 0 or not observations.window_ids or len(
        set(observations.window_ids)
    ) != len(observations.window_ids):
        raise ValueError("finite native sampling rate and unique original windows required")
    points = defaultdict(list)
    allowed = set(observations.window_ids)
    for point in project_scanner_candidates(source):
        if point.source_group_id in allowed:
            points[point.source_group_id].append(point)

    def cell(point):
        canonical = (point.measured_cfo_hz + fs / 2) % fs - fs / 2
        return int(np.floor(canonical / ALIAS_HZ + 0.5))

    selected = [sorted(points[window], key=lambda p: (cell(p), p.candidate_rank, p.candidate_id))
                for window in observations.window_ids]
    if any(not row for row in selected):
        raise ValueError("original observation lacks its bound eligible native candidates")
    width = max(map(len, selected))
    shape = len(selected), width
    cfo, ids = np.zeros(shape), [[""] * width for _ in selected]
    times = np.repeat(observations.times_s[:, None], width, axis=1)
    families, winners = [], []
    for i, row in enumerate(selected):
        p = row[0]
        family = p.receiver_id, p.channel, p.visit_index, p.actual_rf_hz
        if (p.receiver_id != observations.receiver[i] or p.channel != observations.channel[i]
                or p.actual_rf_hz != observations.rf_hz[i]):
            raise ValueError("native candidates differ from aligned original observation metadata")
        if any((x.receiver_id, x.channel, x.visit_index, x.actual_rf_hz) != family for x in row):
            raise ValueError(
                "original window spans incompatible receiver/channel/visit/RF metadata"
            )
        families.append(family)
        per_cell = defaultdict(list)
        for j, point in enumerate(row):
            ids[i][j], cfo[i, j] = point.candidate_id, point.measured_cfo_hz
            times[i, j] = (
                point.support_center_utc_ns - source.timing.first_sample_estimate_utc_ns
            ) / 1e9
            per_cell[cell(point)].append(point)
        winners.append(tuple(
            min(group, key=lambda x: (-x.margin, x.candidate_rank, x.candidate_id)).candidate_id
            for group in per_cell.values()
        ))
    evidence = NativeBranchEvidence(
        tuple(map(tuple, ids)), cfo, np.zeros(shape), np.zeros(shape, bool), times
    )
    return evidence, families, dict(
        policy=POLICY, slot_layout="per-window cell/rank/ID; singleton families required",
        original_windows=len(selected), native_candidates=sum(map(len, selected)),
        collapsed_candidates=sum(map(len, winners)), collapsed_winner_ids=tuple(winners),
        padded_slots=width, waveform="neutral; no measured evidence",
        prior="Separate fixed metadata prior 1/(available cells * candidates in this cell)",
    )
