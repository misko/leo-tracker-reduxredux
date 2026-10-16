"""Original detector-only held windows, with no learned trajectory eligibility."""

import numpy as np

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.regional_position import PositionObservations


def extract_held_windows(source):
    if source.timing is None or not source.qualified or source.capture_mode != "adaptive":
        raise ValueError("qualified original adaptive held probes required")
    winners = {}
    for point in project_scanner_candidates(source):
        previous = winners.get(point.source_group_id)
        key = (-point.margin, point.candidate_rank, point.candidate_id)
        if previous is None or key < (
            -previous.margin,
            previous.candidate_rank,
            previous.candidate_id,
        ):
            winners[point.source_group_id] = point
    points = sorted(
        winners.values(), key=lambda point: (point.support_center_utc_ns, point.source_group_id)
    )
    if not points:
        raise ValueError("no passing original held detector windows")
    origin = source.timing.first_sample_estimate_utc_ns
    return PositionObservations(
        tuple(point.source_group_id for point in points),
        np.array([(point.support_center_utc_ns - origin) / 1e9 for point in points]),
        np.array([point.measured_cfo_hz for point in points]),
        np.array([point.actual_rf_hz for point in points]),
        np.array([point.receiver_id for point in points]),
        np.array([point.channel for point in points]),
        np.array([point.margin for point in points]),
    )
