"""TLE-blind long-scan trajectory reconstruction across scanner RF lanes.

The input rows are already source-bound GLRT observations.  This analyzer
normalizes every CFO to one declared RF reference, finds alias-aware path-local
line segments, and links only strongly compatible segments across RF lanes.
Catalogue contents are deliberately absent from the interface.  The output
``PhysicalEpisodeGraphV1`` can therefore be frozen before any TLE is opened.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from leo.analysis.cfo_lines import CfoPoint, HoughConfig, LineDetectionConfig, weighted_hough_lines
from leo.contracts.catalogue_association import (
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.states import StarlinkEdge

_ALGORITHM_VERSION = "persistent-hop-normalized-hough-episode-graph-v1"


class PersistentHopTrajectoryInputError(ValueError):
    """Long-scan evidence is incomplete, inconsistent, or outside work bounds."""


@dataclass(frozen=True, slots=True)
class PersistentHopTrajectoryConfig:
    """Bounded, provisional geometry controls for 300-second scanner sessions."""

    canonical_rf_hz: float = 11_200_000_000.0
    alias_spacing_hz: float = 1.0 / 4.4e-6
    minimum_slope_hz_per_s: float = -15_000.0
    maximum_slope_hz_per_s: float = 15_000.0
    residual_gate_hz: float = 2_500.0
    maximum_gap_s: float = 2.0
    minimum_span_s: float = 8.0
    minimum_support: int = 8
    minimum_point_weight: float = 0.1
    slope_bins: int = 121
    intercept_bins: int = 512
    peak_candidates: int = 64
    maximum_tracks_per_lane: int = 8
    maximum_input_points: int = 40_000
    maximum_candidates_per_source_group: int = 16
    maximum_trajectory_hypotheses: int = 16
    cross_lane_minimum_overlap_s: float = 8.0
    cross_lane_rate_gate_hz_per_s: float = 250.0

    def __post_init__(self) -> None:
        finite_positive = (
            self.canonical_rf_hz,
            self.alias_spacing_hz,
            self.residual_gate_hz,
            self.maximum_gap_s,
            self.minimum_span_s,
            self.minimum_point_weight,
            self.cross_lane_minimum_overlap_s,
            self.cross_lane_rate_gate_hz_per_s,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in finite_positive):
            raise PersistentHopTrajectoryInputError(
                "trajectory positive controls must be finite"
            )
        if (
            not math.isfinite(self.minimum_slope_hz_per_s)
            or not math.isfinite(self.maximum_slope_hz_per_s)
            or self.minimum_slope_hz_per_s >= self.maximum_slope_hz_per_s
        ):
            raise PersistentHopTrajectoryInputError("trajectory slope range is invalid")
        integer_controls = (
            self.minimum_support,
            self.slope_bins,
            self.intercept_bins,
            self.peak_candidates,
            self.maximum_tracks_per_lane,
            self.maximum_input_points,
            self.maximum_candidates_per_source_group,
            self.maximum_trajectory_hypotheses,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in integer_controls
        ):
            raise PersistentHopTrajectoryInputError(
                "trajectory integer work controls must be positive"
            )

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(
            {name: getattr(self, name) for name in self.__dataclass_fields__}
        )


@dataclass(frozen=True, slots=True)
class PersistentHopCfoCandidate:
    """One fractional, margin-passing GLRT candidate on an actual RF lane."""

    candidate_id: Sha256Digest
    source_group_id: Sha256Digest
    candidate_rank: int
    session_id: str
    input_manifest_digest: Sha256Digest
    raw_recording_authority_digest: Sha256Digest
    radio_id: str
    stream_generation: str
    receiver_id: int
    visit_index: int
    probe_index: int
    channel: int
    edge: StarlinkEdge
    actual_rf_hz: float
    source_sample_start: int
    source_sample_end: int
    support_start_utc_ns: int
    support_center_utc_ns: int
    support_end_utc_ns: int
    measured_cfo_hz: float
    standard_uncertainty_hz: float
    exact_score: float
    control_score: float
    margin: float
    fractional_epoch_used: Literal[True] = True

    def __post_init__(self) -> None:
        if not self.session_id or not self.radio_id or not self.stream_generation:
            raise PersistentHopTrajectoryInputError("trajectory candidate identity is empty")
        if (
            self.candidate_rank < 0
            or self.receiver_id < 0
            or self.visit_index < 0
            or self.probe_index < 0
        ):
            raise PersistentHopTrajectoryInputError("trajectory candidate index is negative")
        if self.channel < 1:
            raise PersistentHopTrajectoryInputError("trajectory channel must be positive")
        if self.source_sample_start < 0 or self.source_sample_end <= self.source_sample_start:
            raise PersistentHopTrajectoryInputError("trajectory source support is invalid")
        if not (
            0 < self.support_start_utc_ns
            <= self.support_center_utc_ns
            < self.support_end_utc_ns
        ):
            raise PersistentHopTrajectoryInputError("trajectory UTC support is invalid")
        values = (
            self.actual_rf_hz,
            self.measured_cfo_hz,
            self.standard_uncertainty_hz,
            self.exact_score,
            self.control_score,
            self.margin,
        )
        if any(not math.isfinite(value) for value in values):
            raise PersistentHopTrajectoryInputError("trajectory candidate values are not finite")
        if self.actual_rf_hz <= 0.0 or self.standard_uncertainty_hz <= 0.0:
            raise PersistentHopTrajectoryInputError(
                "trajectory RF and uncertainty must be positive"
            )
        if self.margin <= 0.0 or not math.isclose(
            self.margin,
            self.exact_score - self.control_score,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise PersistentHopTrajectoryInputError(
                "trajectory candidate must carry a coherent positive margin"
            )

    @property
    def lane_key(self) -> tuple[int, StarlinkEdge, int, float]:
        return self.channel, self.edge, self.receiver_id, self.actual_rf_hz


@dataclass(frozen=True, slots=True)
class PersistentHopTrackPoint:
    candidate_id: Sha256Digest
    relative_alias_index: int
    normalized_raw_cfo_hz: float
    normalized_dealiased_cfo_hz: float


@dataclass(frozen=True, slots=True)
class PersistentHopTracklet:
    tracklet_id: Sha256Digest
    lane_key: tuple[int, StarlinkEdge, int, float]
    start_utc_ns: int
    end_utc_ns: int
    reference_utc_ns: int
    normalized_rate_hz_per_s: float
    normalized_intercept_hz: float
    residual_rms_hz: float
    residual_max_hz: float
    weighted_support: float
    points: tuple[PersistentHopTrackPoint, ...]


@dataclass(frozen=True, slots=True)
class PersistentHopPhysicalGroup:
    group_id: Sha256Digest
    tracklet_ids: tuple[Sha256Digest, ...]
    minimum_pair_overlap_s: float | None
    maximum_pair_rate_difference_hz_per_s: float | None


@dataclass(frozen=True, slots=True)
class PersistentHopTrajectoryHypothesis:
    """One source-disjoint interpretation of competing per-probe candidates."""

    hypothesis_id: Sha256Digest
    graph: PhysicalEpisodeGraphV1
    tracklet_ids: tuple[Sha256Digest, ...]
    physical_groups: tuple[PersistentHopPhysicalGroup, ...]
    aggregate_weighted_support: float
    source_group_count: int


@dataclass(frozen=True, slots=True)
class PersistentHopTrajectoryResult:
    graph: PhysicalEpisodeGraphV1
    tracklets: tuple[PersistentHopTracklet, ...]
    physical_groups: tuple[PersistentHopPhysicalGroup, ...]
    hypotheses: tuple[PersistentHopTrajectoryHypothesis, ...]
    input_candidate_count: int
    used_candidate_count: int
    config_digest: Sha256Digest
    canonical_rf_hz: float
    algorithm_version: Literal[
        "persistent-hop-normalized-hough-episode-graph-v1"
    ] = "persistent-hop-normalized-hough-episode-graph-v1"
    tle_blind: Literal[True] = True
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False


def reconstruct_persistent_hop_trajectories(
    candidates: tuple[PersistentHopCfoCandidate, ...],
    *,
    config: PersistentHopTrajectoryConfig | None = None,
) -> PersistentHopTrajectoryResult:
    """Reconstruct a bounded TLE-blind episode graph from long-scan candidates."""

    selected = config or PersistentHopTrajectoryConfig()
    if len(candidates) > selected.maximum_input_points:
        raise PersistentHopTrajectoryInputError("trajectory input exceeds its work bound")
    if len({item.candidate_id for item in candidates}) != len(candidates):
        raise PersistentHopTrajectoryInputError("trajectory candidate identities are not unique")
    if not candidates:
        raise PersistentHopTrajectoryInputError("trajectory input is empty")
    _validate_source_groups(candidates, selected)
    authority = _shared_authority(candidates)
    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.lane_key,
                item.support_center_utc_ns,
                item.candidate_id,
            ),
        )
    )
    by_lane: dict[tuple[int, StarlinkEdge, int, float], list[PersistentHopCfoCandidate]] = {}
    for candidate in ordered:
        by_lane.setdefault(candidate.lane_key, []).append(candidate)

    tracklets: list[PersistentHopTracklet] = []
    for _lane_key, rows in sorted(by_lane.items(), key=lambda item: item[0]):
        tracklets.extend(_lane_tracklets(tuple(rows), selected))
    tracklets.sort(key=lambda item: (item.start_utc_ns, item.tracklet_id))
    if not tracklets:
        raise PersistentHopTrajectoryInputError(
            "no alias-aware track met the frozen geometry thresholds"
        )

    hypothesis_tracklets = _trajectory_hypothesis_tracklets(tuple(tracklets), ordered, selected)
    hypotheses = tuple(
        _trajectory_hypothesis(
            candidates=ordered,
            tracklets=item,
            config=selected,
            authority=authority,
        )
        for item in hypothesis_tracklets
    )
    graph = hypotheses[0].graph
    groups = hypotheses[0].physical_groups
    used = {point.candidate_id for item in tracklets for point in item.points}
    return PersistentHopTrajectoryResult(
        graph=graph,
        tracklets=tuple(tracklets),
        physical_groups=groups,
        hypotheses=hypotheses,
        input_candidate_count=len(candidates),
        used_candidate_count=len(used),
        config_digest=selected.digest,
        canonical_rf_hz=selected.canonical_rf_hz,
    )


def _validate_source_groups(
    candidates: tuple[PersistentHopCfoCandidate, ...],
    config: PersistentHopTrajectoryConfig,
) -> None:
    groups: dict[Sha256Digest, list[PersistentHopCfoCandidate]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.source_group_id, []).append(candidate)
    for rows in groups.values():
        if len(rows) > config.maximum_candidates_per_source_group:
            raise PersistentHopTrajectoryInputError(
                "trajectory source-group candidate fan-out exceeds its work bound"
            )
        source_bindings = {
            (
                item.session_id,
                item.input_manifest_digest,
                item.raw_recording_authority_digest,
                item.radio_id,
                item.stream_generation,
                item.receiver_id,
                item.visit_index,
                item.probe_index,
                item.channel,
                item.edge,
                item.actual_rf_hz,
                item.source_sample_start,
                item.source_sample_end,
                item.support_start_utc_ns,
                item.support_center_utc_ns,
                item.support_end_utc_ns,
            )
            for item in rows
        }
        if len(source_bindings) != 1:
            raise PersistentHopTrajectoryInputError(
                "trajectory source group does not bind one RF observation"
            )
        ranks = {item.candidate_rank for item in rows}
        if len(ranks) != len(rows):
            raise PersistentHopTrajectoryInputError(
                "trajectory source-group candidate ranks are not unique"
            )


def _shared_authority(
    candidates: tuple[PersistentHopCfoCandidate, ...],
) -> tuple[str, Sha256Digest, Sha256Digest, str, str]:
    values = {
        (
            item.session_id,
            item.input_manifest_digest,
            item.raw_recording_authority_digest,
            item.radio_id,
            item.stream_generation,
        )
        for item in candidates
    }
    if len(values) != 1:
        raise PersistentHopTrajectoryInputError(
            "trajectory candidates do not share one recording authority"
        )
    return values.pop()


def _lane_tracklets(
    candidates: tuple[PersistentHopCfoCandidate, ...],
    config: PersistentHopTrajectoryConfig,
) -> tuple[PersistentHopTracklet, ...]:
    first_utc_ns = min(item.support_center_utc_ns for item in candidates)
    actual_rf_hz = candidates[0].actual_rf_hz
    scale = config.canonical_rf_hz / actual_rf_hz
    points = tuple(
        CfoPoint(
            point_id=item.candidate_id,
            time_s=(item.support_center_utc_ns - first_utc_ns) / 1e9,
            frequency_hz=item.measured_cfo_hz * scale,
            exact_score=item.exact_score,
            control_score=item.control_score,
            margin=item.margin,
        )
        for item in candidates
    )
    common = LineDetectionConfig(
        alias_spacing_hz=config.alias_spacing_hz * scale,
        minimum_slope_hz_per_s=config.minimum_slope_hz_per_s,
        maximum_slope_hz_per_s=config.maximum_slope_hz_per_s,
        residual_gate_hz=config.residual_gate_hz,
        maximum_gap_s=config.maximum_gap_s,
        minimum_span_s=config.minimum_span_s,
        minimum_support=config.minimum_support,
        minimum_point_weight=config.minimum_point_weight,
        maximum_tracks=config.maximum_tracks_per_lane,
    )
    segments = weighted_hough_lines(
        points,
        HoughConfig(
            common=common,
            slope_bins=config.slope_bins,
            intercept_bins=config.intercept_bins,
            peak_candidates=config.peak_candidates,
        ),
    )
    by_id = {item.candidate_id: item for item in candidates}
    point_by_id = {item.point_id: item for item in points}
    output: list[PersistentHopTracklet] = []
    for segment in segments:
        members = tuple(by_id[item] for item in segment.point_ids)
        track_points = []
        for point_id in segment.point_ids:
            point = point_by_id[point_id]
            prediction = segment.slope_hz_per_s * point.time_s + segment.intercept_hz
            alias_index = round(
                (point.frequency_hz - prediction) / common.alias_spacing_hz
            )
            track_points.append(
                PersistentHopTrackPoint(
                    candidate_id=point_id,
                    relative_alias_index=alias_index,
                    normalized_raw_cfo_hz=point.frequency_hz,
                    normalized_dealiased_cfo_hz=(
                        point.frequency_hz - alias_index * common.alias_spacing_hz
                    ),
                )
            )
        output.append(
            PersistentHopTracklet(
                tracklet_id=canonical_digest(
                    {
                        "algorithm_version": _ALGORITHM_VERSION,
                        "config_digest": config.digest,
                        "lane_key": (
                            candidates[0].channel,
                            candidates[0].edge.value,
                            candidates[0].receiver_id,
                            actual_rf_hz,
                        ),
                        "segment_id": segment.segment_id,
                        "point_ids": segment.point_ids,
                    }
                ),
                lane_key=candidates[0].lane_key,
                start_utc_ns=min(item.support_start_utc_ns for item in members),
                end_utc_ns=max(item.support_end_utc_ns for item in members),
                reference_utc_ns=first_utc_ns,
                normalized_rate_hz_per_s=segment.slope_hz_per_s,
                normalized_intercept_hz=segment.intercept_hz,
                residual_rms_hz=segment.residual_rms_hz,
                residual_max_hz=segment.residual_max_hz,
                weighted_support=segment.weighted_support,
                points=tuple(track_points),
            )
        )
    return tuple(output)


def _physical_groups(
    tracklets: tuple[PersistentHopTracklet, ...],
    config: PersistentHopTrajectoryConfig,
) -> tuple[PersistentHopPhysicalGroup, ...]:
    parents = list(range(len(tracklets)))
    lanes = [{tracklets[index].lane_key} for index in range(len(tracklets))]

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    edges: list[tuple[float, float, int, int]] = []
    for left_index, left in enumerate(tracklets):
        for right_index, right in enumerate(tracklets[left_index + 1 :], left_index + 1):
            if left.lane_key == right.lane_key:
                continue
            overlap_ns = min(left.end_utc_ns, right.end_utc_ns) - max(
                left.start_utc_ns, right.start_utc_ns
            )
            overlap_s = overlap_ns / 1e9
            rate_difference = abs(
                left.normalized_rate_hz_per_s - right.normalized_rate_hz_per_s
            )
            if (
                overlap_s >= config.cross_lane_minimum_overlap_s
                and rate_difference <= config.cross_lane_rate_gate_hz_per_s
            ):
                edges.append((rate_difference, -overlap_s, left_index, right_index))
    for _rate, _negative_overlap, left_index, right_index in sorted(edges):
        left_root = root(left_index)
        right_root = root(right_index)
        if left_root == right_root or lanes[left_root] & lanes[right_root]:
            continue
        parents[right_root] = left_root
        lanes[left_root] |= lanes[right_root]

    members: dict[int, list[PersistentHopTracklet]] = {}
    for index, tracklet in enumerate(tracklets):
        members.setdefault(root(index), []).append(tracklet)
    output = []
    for component in members.values():
        ordered = tuple(sorted(component, key=lambda item: item.tracklet_id))
        pair_metrics = [
            (
                (
                    min(left.end_utc_ns, right.end_utc_ns)
                    - max(left.start_utc_ns, right.start_utc_ns)
                )
                / 1e9,
                abs(left.normalized_rate_hz_per_s - right.normalized_rate_hz_per_s),
            )
            for left_index, left in enumerate(ordered)
            for right in ordered[left_index + 1 :]
        ]
        group_id = canonical_digest(
            {
                "algorithm_version": _ALGORITHM_VERSION,
                "relationship": "strict-normalized-rate-overlap-v1",
                "tracklet_ids": tuple(item.tracklet_id for item in ordered),
            }
        )
        output.append(
            PersistentHopPhysicalGroup(
                group_id=group_id,
                tracklet_ids=tuple(item.tracklet_id for item in ordered),
                minimum_pair_overlap_s=(
                    min(item[0] for item in pair_metrics) if pair_metrics else None
                ),
                maximum_pair_rate_difference_hz_per_s=(
                    max(item[1] for item in pair_metrics) if pair_metrics else None
                ),
            )
        )
    return tuple(sorted(output, key=lambda item: item.group_id))


def _trajectory_hypothesis_tracklets(
    tracklets: tuple[PersistentHopTracklet, ...],
    candidates: tuple[PersistentHopCfoCandidate, ...],
    config: PersistentHopTrajectoryConfig,
) -> tuple[tuple[PersistentHopTracklet, ...], ...]:
    """Return bounded maximal sets that never reuse one RF observation.

    The line detector may find several paths through the top-K candidates of a
    single probe.  Each returned set is a separate interpretation: within a
    set, one source group can contribute at most one candidate.  Seeding the
    greedy closure with every ranked tracklet preserves strong alternatives
    without an exponential subset search.
    """

    candidate_by_id = {item.candidate_id: item for item in candidates}
    sources_by_tracklet: dict[Sha256Digest, frozenset[Sha256Digest]] = {}
    for tracklet in tracklets:
        sources = tuple(
            candidate_by_id[point.candidate_id].source_group_id
            for point in tracklet.points
        )
        if len(set(sources)) != len(sources):
            raise PersistentHopTrajectoryInputError(
                "one trajectory tracklet reused a source observation"
            )
        sources_by_tracklet[tracklet.tracklet_id] = frozenset(sources)

    ranked = tuple(
        sorted(
            tracklets,
            key=lambda item: (
                -item.weighted_support,
                -(item.end_utc_ns - item.start_utc_ns),
                item.residual_rms_hz,
                item.tracklet_id,
            ),
        )
    )

    def closure(seed: PersistentHopTracklet | None) -> tuple[PersistentHopTracklet, ...]:
        chosen: list[PersistentHopTracklet] = []
        used_sources: set[Sha256Digest] = set()
        if seed is not None:
            chosen.append(seed)
            used_sources.update(sources_by_tracklet[seed.tracklet_id])
        for tracklet in ranked:
            if seed is not None and tracklet.tracklet_id == seed.tracklet_id:
                continue
            sources = sources_by_tracklet[tracklet.tracklet_id]
            if used_sources.isdisjoint(sources):
                chosen.append(tracklet)
                used_sources.update(sources)
        return tuple(sorted(chosen, key=lambda item: (item.start_utc_ns, item.tracklet_id)))

    distinct: dict[tuple[Sha256Digest, ...], tuple[PersistentHopTracklet, ...]] = {}
    for seed in (None, *ranked):
        chosen = closure(seed)
        key = tuple(item.tracklet_id for item in chosen)
        distinct.setdefault(key, chosen)
    ordered = tuple(
        sorted(
            distinct.values(),
            key=lambda items: (
                -sum(item.weighted_support for item in items),
                -len(
                    {
                        source
                        for item in items
                        for source in sources_by_tracklet[item.tracklet_id]
                    }
                ),
                tuple(item.tracklet_id for item in items),
            ),
        )
    )
    return ordered[: config.maximum_trajectory_hypotheses]


def _trajectory_hypothesis(
    *,
    candidates: tuple[PersistentHopCfoCandidate, ...],
    tracklets: tuple[PersistentHopTracklet, ...],
    config: PersistentHopTrajectoryConfig,
    authority: tuple[str, Sha256Digest, Sha256Digest, str, str],
) -> PersistentHopTrajectoryHypothesis:
    groups = _physical_groups(tracklets, config)
    graph = _episode_graph(
        candidates=candidates,
        tracklets=tracklets,
        groups=groups,
        config=config,
        authority=authority,
    )
    candidate_by_id = {item.candidate_id: item for item in candidates}
    source_groups = {
        candidate_by_id[point.candidate_id].source_group_id
        for item in tracklets
        for point in item.points
    }
    tracklet_ids = tuple(item.tracklet_id for item in tracklets)
    return PersistentHopTrajectoryHypothesis(
        hypothesis_id=canonical_digest(
            {
                "algorithm_version": _ALGORITHM_VERSION,
                "relationship": "source-disjoint-trajectory-hypothesis-v1",
                "tracklet_ids": tracklet_ids,
                "graph_digest": graph.content_digest,
            }
        ),
        graph=graph,
        tracklet_ids=tracklet_ids,
        physical_groups=groups,
        aggregate_weighted_support=sum(item.weighted_support for item in tracklets),
        source_group_count=len(source_groups),
    )


def _episode_graph(
    *,
    candidates: tuple[PersistentHopCfoCandidate, ...],
    tracklets: tuple[PersistentHopTracklet, ...],
    groups: tuple[PersistentHopPhysicalGroup, ...],
    config: PersistentHopTrajectoryConfig,
    authority: tuple[str, Sha256Digest, Sha256Digest, str, str],
) -> PhysicalEpisodeGraphV1:
    session_id, manifest_digest, raw_authority_digest, radio_id, stream_generation = authority
    candidate_by_id = {item.candidate_id: item for item in candidates}
    group_by_tracklet = {
        tracklet_id: group
        for group in groups
        for tracklet_id in group.tracklet_ids
    }
    observations: list[SupportIntegratedCfoObservationV1] = []
    episodes: list[PhysicalCfoEpisodeV1] = []
    dwell_id = canonical_digest(
        {
            "session_id": session_id,
            "input_manifest_digest": manifest_digest,
            "algorithm_version": _ALGORITHM_VERSION,
        }
    )
    for tracklet in tracklets:
        episode_id = canonical_digest(
            {"tracklet_id": tracklet.tracklet_id, "dwell_id": dwell_id}
        )
        channel, edge, receiver_id, actual_rf_hz = tracklet.lane_key
        lane_authority = {
            "radio_id": radio_id,
            "stream_generation": stream_generation,
            "receiver_id": receiver_id,
            "channel": channel,
            "edge": edge.value,
            "actual_rf_hz": actual_rf_hz,
        }
        receiver_path_id = canonical_digest(lane_authority)
        continuity_component_id = canonical_digest(
            {"relationship": "lane-local-frequency-offset-v1", **lane_authority}
        )
        observation_ids = []
        for point in tracklet.points:
            source = candidate_by_id[point.candidate_id]
            scale = config.canonical_rf_hz / source.actual_rf_hz
            moments = _uniform_support_moments(
                source.support_start_utc_ns,
                source.support_center_utc_ns,
                source.support_end_utc_ns,
            )
            observation_id = canonical_digest(
                {
                    "algorithm_version": _ALGORITHM_VERSION,
                    "candidate_id": point.candidate_id,
                    "tracklet_id": tracklet.tracklet_id,
                    "relative_alias_index": point.relative_alias_index,
                    "canonical_rf_hz": config.canonical_rf_hz,
                }
            )
            observations.append(
                SupportIntegratedCfoObservationV1(
                    observation_id=observation_id,
                    source_group_id=source.source_group_id,
                    episode_id=episode_id,
                    receiver_path_id=receiver_path_id,
                    hardware_epoch_id=(
                        "hw-" + canonical_digest(
                            {"radio_id": radio_id, "stream_generation": stream_generation}
                        ).split(":", 1)[1][:32]
                    ),
                    raw_recording_authority_digest=raw_authority_digest,
                    recording_manifest_digest=manifest_digest,
                    stream_id=f"rx-{receiver_id}",
                    source_binding_digest=canonical_digest(
                        {
                            "candidate_id": point.candidate_id,
                            "actual_rf_hz": source.actual_rf_hz,
                            "canonical_rf_hz": config.canonical_rf_hz,
                            "relative_alias_index": point.relative_alias_index,
                            "fractional_epoch_used": True,
                        }
                    ),
                    source_sample_start=source.source_sample_start,
                    source_sample_end=source.source_sample_end,
                    support_start_utc_ns=source.support_start_utc_ns,
                    support_center_utc_ns=source.support_center_utc_ns,
                    support_end_utc_ns=source.support_end_utc_ns,
                    measured_cfo_hz=point.normalized_dealiased_cfo_hz,
                    standard_uncertainty_hz=source.standard_uncertainty_hz * scale,
                    factorial_support_moments_s=moments,
                )
            )
            observation_ids.append(observation_id)
        group = group_by_tracklet[tracklet.tracklet_id]
        episodes.append(
            PhysicalCfoEpisodeV1(
                episode_id=episode_id,
                dwell_id=dwell_id,
                lane_id=canonical_digest(
                    {"receiver_path_id": receiver_path_id, "tracklet_id": tracklet.tracklet_id}
                ),
                order_index=0,
                continuity_component_id=continuity_component_id,
                observation_ids=tuple(observation_ids),
                replica_group_id=(group.group_id if len(group.tracklet_ids) > 1 else None),
            )
        )
    return PhysicalEpisodeGraphV1.create(
        observations=tuple(observations),
        episodes=tuple(episodes),
    )


def _uniform_support_moments(
    start_utc_ns: int,
    center_utc_ns: int,
    end_utc_ns: int,
) -> tuple[float, float, float, float]:
    lower = (start_utc_ns - center_utc_ns) / 1e9
    upper = (end_utc_ns - center_utc_ns) / 1e9
    width = upper - lower
    raw_first = (lower + upper) / 2.0
    if not math.isclose(raw_first, 0.0, rel_tol=0.0, abs_tol=1e-9):
        raise PersistentHopTrajectoryInputError(
            "uniform support center is not the interval midpoint"
        )
    raw_second = (upper**3 - lower**3) / (3.0 * width)
    raw_third = (upper**4 - lower**4) / (4.0 * width)
    return (1.0, 0.0, raw_second / 2.0, raw_third / 6.0)


__all__ = [
    "PersistentHopCfoCandidate",
    "PersistentHopPhysicalGroup",
    "PersistentHopTrackPoint",
    "PersistentHopTracklet",
    "PersistentHopTrajectoryConfig",
    "PersistentHopTrajectoryHypothesis",
    "PersistentHopTrajectoryInputError",
    "PersistentHopTrajectoryResult",
    "reconstruct_persistent_hop_trajectories",
]
