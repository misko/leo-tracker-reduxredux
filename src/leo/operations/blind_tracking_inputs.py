"""Prepare bounded, truth-free scanner tracks and causal orbit states.

This adapter is deliberately upstream of satellite association.  It rebuilds
RF tracks from the scanner GLRT source and exposes the complete eligible
Starlink catalogue; saved TLE reviews, candidate identities, and observer sites
are not inputs to this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np

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
from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_tracking import ScannerTrackingInputs
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets

_NS_PER_S = 1_000_000_000


class CausalTleArchive(Protocol):
    """Narrow read-only port needed by blind input preparation."""

    def select_latest_before(self, measurement_start_utc_ns: int): ...
    def read(self, snapshot) -> str: ...


class BlindInputUnavailable(RuntimeError):
    """Expected scientific insufficiency, distinct from an implementation error."""

    def __init__(self, reason: str, *, accounting: dict[str, int] | None = None) -> None:
        self.reason = reason
        self.accounting = dict(accounting or {})
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BlindRegion:
    center_latitude_deg: float = 39.7392
    center_longitude_deg: float = -104.9903
    width_km: float = 14_484.096
    height_km: float = 14_484.096
    altitude_m: float = 0.0

    def __post_init__(self) -> None:
        if not (-90 <= self.center_latitude_deg <= 90):
            raise ValueError("region latitude is invalid")
        if not (-180 <= self.center_longitude_deg <= 180):
            raise ValueError("region longitude is invalid")
        if not (0 < self.width_km <= 20_000 and 0 < self.height_km <= 20_000):
            raise ValueError("region dimensions must be in (0, 20000] km")


@dataclass(frozen=True, slots=True)
class BlindInputLimits:
    maximum_tracks: int = 32
    maximum_observations_per_track: int = 128
    minimum_observations_per_track: int = 14
    minimum_track_span_seconds: float = 7.0
    causal_guard_seconds: float = 505.0
    orbit_phase_offsets_s: tuple[float, ...] = (0.0,)

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_tracks <= 64:
            raise ValueError("maximum_tracks must be between 1 and 64")
        if (
            not 14
            <= self.minimum_observations_per_track
            <= self.maximum_observations_per_track
            <= 512
        ):
            raise ValueError("observation bounds are invalid")
        if not 0 <= self.minimum_track_span_seconds <= 3_600:
            raise ValueError("minimum track span must be between 0 and 3600 seconds")
        if not 0 <= self.causal_guard_seconds <= 3_600:
            raise ValueError("causal guard must be between 0 and 3600 seconds")
        if not self.orbit_phase_offsets_s or len(self.orbit_phase_offsets_s) > 9:
            raise ValueError("one to nine orbit phase offsets are required")


@dataclass(frozen=True, slots=True)
class BlindInputExclusion:
    scope: str
    identity: str
    reason: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class BlindRfTrack:
    track_id: str
    observation_id: tuple[str, ...]
    support_center_utc_ns: np.ndarray
    measured_cfo_hz: np.ndarray
    training: np.ndarray
    source_digest: str
    original_observation_count: int


@dataclass(frozen=True, slots=True)
class BlindOrbitCatalogue:
    snapshot_digest: str
    snapshot_collected_utc_ns: int
    provider: str
    catalogue_digest: str
    catalog_number: np.ndarray
    element_epoch_utc_ns: np.ndarray
    phase_offsets_s: tuple[float, ...]
    # Per track: candidate x observation x phase-offset x Cartesian component.
    position_ecef_km: tuple[np.ndarray, ...]
    velocity_ecef_km_s: tuple[np.ndarray, ...]


@dataclass(frozen=True, slots=True)
class PreparedBlindTrackingInputs:
    session_id: str
    input_manifest_sha256: str
    analysis_manifest_sha256: str
    region: BlindRegion
    tracks: tuple[BlindRfTrack, ...]
    catalogue: BlindOrbitCatalogue
    exclusions: tuple[BlindInputExclusion, ...]
    source_digest: str
    configuration_digest: str
    reconstructed_track_count: int
    reconstructed_observation_count: int
    eligible_track_count: int
    eligible_observation_count: int
    selected_observation_count: int
    omitted_observation_count: int
    known_position_used_for_track_construction: bool = False
    known_position_used_for_catalogue_selection: bool = False
    site_conditioned_candidates: bool = False

    def numerical_tracks(self):
        """Adapt prepared states to the pure numerical association boundary."""
        from leo.analysis.blind_regional_association import BlindRegionalTrack

        nominal = self.catalogue.phase_offsets_s.index(0.0)
        return tuple(
            BlindRegionalTrack(
                track_id=track.track_id,
                observation_id=track.observation_id,
                utc_ns=track.support_center_utc_ns,
                measured_hz=track.measured_cfo_hz,
                training=track.training,
                catalog_number=self.catalogue.catalog_number,
                position_ecef_km=self.catalogue.position_ecef_km[index][:, :, nominal, :],
                velocity_ecef_km_s=self.catalogue.velocity_ecef_km_s[index][:, :, nominal, :],
                full_catalogue_size=len(self.catalogue.catalog_number),
                catalogue_universe_digest=self.catalogue.catalogue_digest,
                source_support_digest=track.source_digest,
            )
            for index, track in enumerate(self.tracks)
        )


def _balanced(rows: tuple, maximum: int) -> tuple:
    """Retain endpoints and deterministic coverage across the full arc."""
    if len(rows) <= maximum:
        return rows
    indices = np.linspace(0, len(rows) - 1, maximum, dtype=np.int64)
    return tuple(rows[int(index)] for index in indices)


def _track_graphs(trajectory) -> tuple[tuple[tuple[str, Any], ...], tuple[str, ...]]:
    graphs: dict[str, Any | None] = {}
    for hypothesis in trajectory.hypotheses:
        for track_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, track_id)
            prior = graphs.get(track_id)
            if prior is None and track_id not in graphs:
                graphs[track_id] = graph
            elif prior is not None and tuple(r.observation_id for r in prior.observations) != tuple(
                r.observation_id for r in graph.observations
            ):
                graphs[track_id] = None
    valid = tuple((key, value) for key, value in sorted(graphs.items()) if value is not None)
    ambiguous = tuple(key for key, value in sorted(graphs.items()) if value is None)
    return valid, ambiguous


def _training_partition(observation_id: tuple[str, ...]) -> np.ndarray:
    """Deterministic 60% split with at least two rows on either side."""
    training_count = min(len(observation_id) - 2, max(2, round(0.6 * len(observation_id))))
    ranked = sorted(
        range(len(observation_id)),
        key=lambda index: (canonical_digest({"split": observation_id[index]}), index),
    )
    result = np.zeros(len(observation_id), dtype=np.bool_)
    result[ranked[:training_count]] = True
    return result


def _propagate(satellite, receive_utc_ns: np.ndarray, phase_offsets_s: tuple[float, ...]):
    positions, velocities = [], []
    receive_jd, receive_fraction = julian_day_from_utc_ns(receive_utc_ns)
    earth_angle = greenwich_mean_sidereal_time_rad(receive_jd, receive_fraction)
    for offset_s in phase_offsets_s:
        orbit_utc_ns = receive_utc_ns + round(offset_s * _NS_PER_S)
        jd, fraction = julian_day_from_utc_ns(orbit_utc_ns)
        errors, position, velocity = satellite.sgp4_array(jd, fraction)
        if np.any(errors):
            codes = tuple(sorted({int(value) for value in errors if int(value)}))
            raise ValueError(f"SGP4 error codes {codes}")
        position, velocity = teme_to_ecef(position, velocity, earth_angle)
        positions.append(position)
        velocities.append(velocity)
    return np.stack(positions, axis=1), np.stack(velocities, axis=1)


def prepare_blind_tracking_inputs(
    session_id: str,
    *,
    inputs: ScannerTrackingInputs,
    archive: CausalTleArchive,
    region: BlindRegion | None = None,
    limits: BlindInputLimits | None = None,
) -> PreparedBlindTrackingInputs:
    """Reconstruct GLRT tracks and propagate a full causal Starlink universe."""
    region = region or BlindRegion()
    limits = limits or BlindInputLimits()
    source = inputs.load(session_id)
    if not timing_is_qualified_for_tle(source.timing):
        raise BlindInputUnavailable("utc-unqualified")
    trajectory_config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(
        project_scanner_candidates(source), config=trajectory_config
    )
    exclusions: list[BlindInputExclusion] = []
    tracks: list[BlindRfTrack] = []
    seen: set[str] = set()
    graphs, ambiguous_track_ids = _track_graphs(trajectory)
    exclusions.extend(
        BlindInputExclusion("track", track_id, "ambiguous-hypothesis-graph")
        for track_id in ambiguous_track_ids
    )
    ranked = sorted(
        graphs,
        key=lambda item: (
            -len(item[1].observations),
            min(row.support_center_utc_ns for row in item[1].observations),
            item[0],
        ),
    )
    reconstructed_observation_count = sum((len(graph.observations) for _, graph in ranked), start=0)
    eligible_track_count = 0
    eligible_observation_count = 0
    for track_id, graph in ranked:
        rows = tuple(
            sorted(
                graph.observations, key=lambda row: (row.support_center_utc_ns, row.observation_id)
            )
        )
        ids_all = tuple(row.observation_id for row in rows)
        utc_all = np.asarray([row.support_center_utc_ns for row in rows], dtype=np.int64)
        cfo_all = np.asarray([row.measured_cfo_hz for row in rows], dtype=np.float64)
        if (
            len(set(ids_all)) != len(ids_all)
            or any(not identity or len(identity) > 256 for identity in ids_all)
            or np.any(np.diff(utc_all) <= 0)
            or not np.all(np.isfinite(cfo_all))
        ):
            exclusions.append(BlindInputExclusion("track", track_id, "invalid-observations"))
            continue
        if len(rows) < limits.minimum_observations_per_track:
            exclusions.append(BlindInputExclusion("track", track_id, "insufficient-observations"))
            continue
        span_s = (rows[-1].support_center_utc_ns - rows[0].support_center_utc_ns) / _NS_PER_S
        if span_s < limits.minimum_track_span_seconds:
            exclusions.append(
                BlindInputExclusion("track", track_id, "insufficient-time-span", f"{span_s:.9g} s")
            )
            continue
        if any(row.observation_id in seen for row in rows):
            exclusions.append(BlindInputExclusion("track", track_id, "overlapping-observation-ids"))
            continue
        eligible_track_count += 1
        eligible_observation_count += len(rows)
        if len(tracks) >= limits.maximum_tracks:
            exclusions.append(BlindInputExclusion("track", track_id, "track-limit"))
            continue
        original_count = len(rows)
        rows = _balanced(rows, limits.maximum_observations_per_track)
        if len(rows) < original_count:
            exclusions.append(
                BlindInputExclusion(
                    "track",
                    track_id,
                    "observation-limit",
                    f"retained {len(rows)} of {original_count}",
                )
            )
        seen.update(row.observation_id for row in rows)
        ids = tuple(row.observation_id for row in rows)
        training = _training_partition(ids)
        track_source = {
            "track_id": track_id,
            "observation_id": ids,
            "support_center_utc_ns": [row.support_center_utc_ns for row in rows],
            "measured_cfo_hz": [row.measured_cfo_hz for row in rows],
            "training": training.tolist(),
        }
        tracks.append(
            BlindRfTrack(
                track_id=track_id,
                observation_id=ids,
                support_center_utc_ns=np.asarray(
                    track_source["support_center_utc_ns"], dtype=np.int64
                ),
                measured_cfo_hz=np.asarray(track_source["measured_cfo_hz"], dtype=np.float64),
                training=training,
                source_digest=canonical_digest(track_source),
                original_observation_count=original_count,
            )
        )
    if not tracks:
        raise BlindInputUnavailable(
            "no-eligible-rf-tracks",
            accounting={
                "reconstructed_track_count": len(ranked),
                "reconstructed_observation_count": reconstructed_observation_count,
                "eligible_track_count": eligible_track_count,
                "eligible_observation_count": eligible_observation_count,
            },
        )

    earliest = min(int(track.support_center_utc_ns.min()) for track in tracks)
    causal_cutoff = earliest - round(limits.causal_guard_seconds * _NS_PER_S)
    snapshot = archive.select_latest_before(causal_cutoff)
    if snapshot.collected_utc_ns >= causal_cutoff:
        raise ValueError("TLE snapshot is not causal at the declared guard")
    payload, debris = exclude_labelled_starlink_debris(archive.read(snapshot))
    exclusions.extend(
        BlindInputExclusion("catalogue", str(item.catalog_number), "labelled-debris", item.name)
        for item in debris
    )
    catalogue = parse_element_sets(payload)
    if len(set(catalogue.satellite_numbers)) != len(catalogue.satellite_numbers):
        raise ValueError("TLE catalogue contains duplicate catalogue numbers")
    starlink = [i for i, name in enumerate(catalogue.names) if name.upper().startswith("STARLINK")]
    epochs = catalogue.element_epoch_utc_ns()
    eligible = [i for i in starlink if epochs[i] < earliest]
    for index in starlink:
        if epochs[index] >= earliest:
            exclusions.append(
                BlindInputExclusion(
                    "catalogue", str(catalogue.satellite_numbers[index]), "noncausal-element-epoch"
                )
            )

    retained: list[int] = []
    position_by_track: list[list[np.ndarray]] = [[] for _ in tracks]
    velocity_by_track: list[list[np.ndarray]] = [[] for _ in tracks]
    for index in eligible:
        states = []
        try:
            for track in tracks:
                states.append(
                    _propagate(
                        catalogue.satellites[index],
                        track.support_center_utc_ns,
                        limits.orbit_phase_offsets_s,
                    )
                )
        except ValueError as error:
            exclusions.append(
                BlindInputExclusion(
                    "catalogue",
                    str(catalogue.satellite_numbers[index]),
                    "propagation-failed",
                    str(error),
                )
            )
            continue
        retained.append(index)
        for track_index, (position, velocity) in enumerate(states):
            position_by_track[track_index].append(position)
            velocity_by_track[track_index].append(velocity)
    if not retained:
        raise BlindInputUnavailable(
            "no-causal-propagatable-starlink-members",
            accounting={
                "eligible_catalogue_member_count": len(eligible),
                "propagation_exclusion_count": sum(
                    item.reason == "propagation-failed" for item in exclusions
                ),
            },
        )
    numbers = np.asarray([catalogue.satellite_numbers[index] for index in retained], dtype=np.int64)
    retained_epochs = np.asarray([epochs[index] for index in retained], dtype=np.int64)
    catalogue_digest = canonical_digest(
        {
            "snapshot": snapshot.digest,
            "catalog_number": numbers.tolist(),
            "element_epoch_utc_ns": retained_epochs.tolist(),
        }
    )
    orbit_catalogue = BlindOrbitCatalogue(
        snapshot_digest=snapshot.digest,
        snapshot_collected_utc_ns=snapshot.collected_utc_ns,
        provider=snapshot.provider,
        catalogue_digest=catalogue_digest,
        catalog_number=numbers,
        element_epoch_utc_ns=retained_epochs,
        phase_offsets_s=limits.orbit_phase_offsets_s,
        position_ecef_km=tuple(np.stack(items) for items in position_by_track),
        velocity_ecef_km_s=tuple(np.stack(items) for items in velocity_by_track),
    )
    configuration_digest = canonical_digest(
        {
            "algorithm": "blind-tracking-inputs-v1",
            "region": asdict(region),
            "limits": asdict(limits),
            "trajectory": trajectory_config.digest,
        }
    )
    source_digest = canonical_digest(
        {
            "session_id": session_id,
            "input": source.input_manifest_sha256,
            "analysis": source.analysis_manifest_sha256,
            "tracks": [track.source_digest for track in tracks],
            "catalogue": catalogue_digest,
            "configuration": configuration_digest,
        }
    )
    return PreparedBlindTrackingInputs(
        session_id=session_id,
        input_manifest_sha256=source.input_manifest_sha256,
        analysis_manifest_sha256=source.analysis_manifest_sha256,
        region=region,
        tracks=tuple(tracks),
        catalogue=orbit_catalogue,
        exclusions=tuple(exclusions),
        source_digest=source_digest,
        configuration_digest=configuration_digest,
        reconstructed_track_count=len(ranked),
        reconstructed_observation_count=reconstructed_observation_count,
        eligible_track_count=eligible_track_count,
        eligible_observation_count=eligible_observation_count,
        selected_observation_count=sum(len(track.observation_id) for track in tracks),
        omitted_observation_count=eligible_observation_count
        - sum(len(track.observation_id) for track in tracks),
    )
