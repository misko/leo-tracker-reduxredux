"""Prepare truth-free all-track inputs for adaptive TLE position selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from leo.analysis.adaptive_tle_position import fixed_randomized_training_mask
from leo.analysis.adaptive_tle_prediction import AdaptiveTrackInput
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.catalogue_association import CataloguePredictionSupportV1
from leo.contracts.digests import canonical_digest
from leo.sky.propagation import parse_element_sets

_NS_PER_S = 1_000_000_000


class AdaptiveTleInputUnavailable(RuntimeError):
    """Expected evidence insufficiency, distinct from an integrity failure."""


@dataclass(frozen=True)
class PreparedAdaptiveTleInputs:
    session_id: str
    input_manifest_sha256: str
    analysis_manifest_sha256: str
    start_utc_ns: int
    trajectory_digest: str
    tracks: tuple[AdaptiveTrackInput, ...]
    track_support_digests: tuple[str, ...]
    catalogue: object
    candidate_indices: np.ndarray
    snapshot_digest: str
    snapshot_collected_utc_ns: int
    reconstructed_track_count: int
    eligible_track_count: int
    eligible_observation_count: int
    evidence_sha256: str
    track_evidence: tuple[dict, ...]


def _graphs(trajectory):
    values = {}
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            old = values.get(track_id)
            if old is None and track_id not in values:
                values[track_id] = graph
            elif old is not None and tuple(x.observation_id for x in old.observations) != tuple(
                x.observation_id for x in graph.observations
            ):
                values[track_id] = None
    return tuple((key, value) for key, value in sorted(values.items()) if value is not None)


def _partition_seed(observation_ids, support_digest, trajectory_digest):
    protocol = canonical_digest(
        {
            "algorithm": "scanner-shared-tracking-v12",
            "utc_qualification_limit_ns": 2_000_000_000,
            "trajectory": trajectory_digest,
            "group_limit": 4,
            "selection": "eligible-first-longest-support-v1",
            "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
            "observer": {"mode": "fixed", "salt": "cf510316-fixed-partition-v1"},
        }
    )
    seed = canonical_digest(
        {
            "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
            "response_free_support_digest": support_digest,
            "selection_protocol_digest": protocol,
        }
    )
    return fixed_randomized_training_mask(observation_ids, seed=seed), seed


def prepare_adaptive_tle_position_inputs(session_id: str, *, inputs, archive):
    source = inputs.load(session_id)
    if not timing_is_qualified_for_tle(source.timing):
        raise AdaptiveTleInputUnavailable("qualified UTC is required")
    start = source.timing.first_sample_estimate_utc_ns
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(source), config=config
    )
    graphs = _graphs(trajectory)
    tracks, supports, evidence = [], [], []
    observed: set[str] = set()
    for track_id, graph in graphs:
        rows = tuple(sorted(graph.observations, key=lambda row: row.support_center_utc_ns))
        if len(rows) < 6:
            continue
        times = np.asarray(
            [(row.support_center_utc_ns - start) / _NS_PER_S for row in rows], dtype=float
        )
        if times[-1] - times[0] < 3.0:
            continue
        ids = tuple(row.observation_id for row in rows)
        if len(set(ids)) != len(ids) or observed.intersection(ids):
            raise ValueError("adaptive TLE tracks contain overlapping observation IDs")
        observed.update(ids)
        measured = np.asarray([row.measured_cfo_hz for row in rows], dtype=float)
        support = CataloguePredictionSupportV1.from_graph(graph).content_digest
        mask, seed = _partition_seed(ids, support, config.digest)
        tracks.append(AdaptiveTrackInput(track_id, ids, times, measured, mask))
        supports.append(support)
        evidence.append(
            {
                "track_id": track_id,
                "support_digest": support,
                "observation_ids": ids,
                "times_s": times.tolist(),
                "measured_hz": measured.tolist(),
                "training_mask": mask.tolist(),
                "partition_seed": seed,
            }
        )
    if not tracks:
        raise AdaptiveTleInputUnavailable(
            "no tracks satisfy the three-second six-observation policy"
        )
    cutoff = start - 505 * _NS_PER_S
    snapshot = archive.select_latest_before(cutoff)
    if snapshot.collected_utc_ns >= cutoff:
        raise ValueError("TLE snapshot is not strictly causal")
    payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
    catalogue = parse_element_sets(payload)
    indices = np.asarray(
        [
            index
            for index, name in enumerate(catalogue.names)
            if name.upper().startswith("STARLINK")
        ],
        dtype=int,
    )
    if not len(indices):
        raise AdaptiveTleInputUnavailable("causal catalogue has no eligible Starlink members")
    evidence_sha256 = canonical_digest(
        {
            "session_id": session_id,
            "input_manifest_sha256": source.input_manifest_sha256,
            "analysis_manifest_sha256": source.analysis_manifest_sha256,
            "trajectory_digest": config.digest,
            "snapshot_digest": snapshot.digest,
            "candidate_ids": [catalogue.satellite_numbers[index] for index in indices],
            "tracks": evidence,
        }
    )
    return PreparedAdaptiveTleInputs(
        session_id,
        source.input_manifest_sha256,
        source.analysis_manifest_sha256,
        start,
        config.digest,
        tuple(tracks),
        tuple(supports),
        catalogue,
        indices,
        snapshot.digest,
        snapshot.collected_utc_ns,
        len(trajectory.tracklets),
        len(tracks),
        len(observed),
        evidence_sha256,
        tuple(evidence),
    )
