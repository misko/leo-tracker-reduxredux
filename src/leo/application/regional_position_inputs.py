"""Original GLRT windows and orbit-blind calibration seeds through public ports."""

from dataclasses import dataclass

import numpy as np

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionObservations
from leo.contracts.scanner_tracking import TrackingInput


class PositionInputUnavailable(ValueError):
    """A valid capture lacks the observations needed for a position diagnostic."""


@dataclass(frozen=True)
class PreparedPositionWindows:
    observations: PositionObservations
    candidate_ids: tuple[str, ...]
    bootstrap_tracks: tuple[tuple[int, ...], ...]
    start_utc_ns: int
    evidence_sha256: str
    trajectory_configuration_sha256: str


def prepare_position_windows(source: TrackingInput) -> PreparedPositionWindows:
    if source.capture_mode != "adaptive" or not source.qualified:
        raise PositionInputUnavailable("qualified adaptive capture required")
    if source.timing is None or not timing_is_qualified_for_tle(source.timing):
        raise PositionInputUnavailable("qualified UTC required")
    winners: dict[str, PersistentHopCfoCandidate] = {}
    for point in project_scanner_candidates(source):
        previous = winners.get(point.source_group_id)
        key = (-point.margin, point.candidate_rank, point.candidate_id)
        if previous is None or key < (
            -previous.margin,
            previous.candidate_rank,
            previous.candidate_id,
        ):
            winners[point.source_group_id] = point
    points = tuple(
        sorted(winners.values(), key=lambda p: (p.support_center_utc_ns, p.source_group_id))
    )
    if len(points) < 20:
        raise PositionInputUnavailable("fewer than twenty passing original GLRT windows")
    origin = source.timing.first_sample_estimate_utc_ns
    observations = PositionObservations(
        tuple(p.source_group_id for p in points),
        np.asarray([(p.support_center_utc_ns - origin) / 1e9 for p in points]),
        np.asarray([p.measured_cfo_hz for p in points]),
        np.asarray([p.actual_rf_hz for p in points]),
        np.asarray([p.receiver_id for p in points]),
        np.asarray([p.channel for p in points]),
        np.asarray([p.margin for p in points]),
    )
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(
        tuple(p for p in points if p.margin > 0), config=config
    )
    lookup = {p.candidate_id: i for i, p in enumerate(points)}
    tracks = []
    for track in trajectory.tracklets:
        rows = tuple(sorted({lookup[p.candidate_id] for p in track.points}))
        if len(rows) >= 15 and np.ptp(observations.times_s[list(rows)]) >= 15:
            tracks.append(rows)
    selected = []
    for rx in (0, 1):
        matches = [rows for rows in tracks if observations.receiver[rows[0]] == rx]
        selected.extend(
            sorted(matches, key=lambda rows: (-np.ptp(observations.times_s[list(rows)]), rows))[:12]
        )
    if {int(observations.receiver[rows[0]]) for rows in selected} != {0, 1}:
        raise PositionInputUnavailable("calibration bootstrap requires tracks on both receivers")
    candidate_ids = tuple(p.candidate_id for p in points)
    evidence = canonical_digest(
        {
            "capture": source.input_manifest_sha256,
            "analysis": source.analysis_manifest_sha256,
            "refinement": "off",
            "selection": "highest-original-margin-rank-id-v1",
            "candidate_ids": candidate_ids,
            "window_ids": observations.window_ids,
            "times_s": observations.times_s.tolist(),
            "measured_hz": observations.measured_hz.tolist(),
            "rf_hz": observations.rf_hz.tolist(),
            "receiver": observations.receiver.tolist(),
            "channel": observations.channel.tolist(),
            "margin": observations.margin.tolist(),
            "bootstrap_tracks": selected,
            "trajectory_configuration": config.digest,
        }
    )
    return PreparedPositionWindows(
        observations, candidate_ids, tuple(selected), origin, evidence, config.digest
    )
