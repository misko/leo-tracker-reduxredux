"""Prepare bounded, causal saved scanner evidence for positioning methods."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.research.formal_orbit import doppler_hz, phase_state
from leo.analysis.scan_position_methods import ScanPositionEpisode
from leo.application.scanner_trajectory import (
    project_scanner_candidates,
    timing_is_qualified_for_tle,
)
from leo.contracts.catalogue_association import CataloguePredictionSupportV1
from leo.contracts.digests import canonical_digest
from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets
from leo.sky.sites import SITE_PRESETS

_NS_PER_S = 1_000_000_000
_NS_PER_H = 3_600 * _NS_PER_S


@dataclass(frozen=True)
class PositionInputExclusion:
    session_id: str
    tracklet_id: str | None
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class PositionInputProvenance:
    session_id: str
    input_manifest_sha256: str
    analysis_sha256: str
    tracking_product_sha256: str | None
    snapshot_digest: str | None
    snapshot_collected_utc_ns: int | None
    selection_protocol_digest: str | None
    site_conditioned: bool = True
    shortlist_calibrated_probabilities: bool = False


@dataclass(frozen=True)
class PositionInputCoverage:
    eligible_session_count: int
    selected_session_count: int
    saved_review_count: int
    selected_track_count: int
    target_track_count: int
    history_track_count: int
    observation_count: int
    training_observation_count: int
    heldout_observation_count: int
    exclusion_count: int


@dataclass(frozen=True)
class PositionTargetSource:
    session_id: str
    radio_id: str
    capture_start_utc_ns: int
    input_manifest_sha256: str
    analysis_sha256: str


@dataclass(frozen=True)
class _RuntimeEpisode:
    session_id: str
    observation_utc_ns: np.ndarray
    satellites: tuple[Any, ...]


@dataclass(frozen=True)
class PreparedScanPositionInputs:
    target_episodes: tuple[ScanPositionEpisode, ...]
    episodes: tuple[ScanPositionEpisode, ...]
    provenance: tuple[PositionInputProvenance, ...]
    exclusions: tuple[PositionInputExclusion, ...]
    coverage: PositionInputCoverage
    target_source: PositionTargetSource
    source_manifest: tuple[dict[str, Any], ...]
    _runtime: tuple[_RuntimeEpisode, ...] = field(repr=False, compare=False)


def _capture_start(source) -> int:
    if not timing_is_qualified_for_tle(source.timing):
        raise ValueError("qualified UTC is required")
    return source.capture_start_utc_ns or source.timing.first_sample_estimate_utc_ns


def _review_site(observer_site):
    observer = observer_site.model_dump(mode="json")
    matches = [
        preset
        for preset in SITE_PRESETS.values()
        if all(
            observer.get(key) == value
            for key, value in preset.model_dump(mode="json").items()
            if key in observer
        )
    ]
    if len(matches) != 1:
        raise ValueError("saved observer does not uniquely match a reviewed site preset")
    return matches[0]


def _selection_digest(site) -> str:
    config = PersistentHopTrajectoryConfig()
    return canonical_digest(
        {
            "algorithm": "scanner-shared-tracking-v12",
            "utc_qualification_limit_ns": 2_000_000_000,
            "trajectory": config.digest,
            "group_limit": 4,
            "selection": "eligible-first-longest-support-v1",
            "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
            "observer": site.model_dump(mode="json"),
        }
    )


def _graph_by_tracklet(trajectory) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for hypothesis in trajectory.hypotheses:
        for tracklet_id in hypothesis.tracklet_ids:
            graph = persistent_hop_tracklet_graph(hypothesis, tracklet_id)
            old = result.get(tracklet_id)
            if old is not None:
                old_ids = tuple(row.observation_id for row in old.observations)
                new_ids = tuple(row.observation_id for row in graph.observations)
                if old_ids != new_ids:
                    # Ambiguous alternative hypotheses are deliberately unavailable.
                    result[tracklet_id] = None
            else:
                result[tracklet_id] = graph
    return result


def _rank_reviews(reviews, graphs) -> list[Any]:
    def key(review):
        graph = graphs.get(review.tracklet_id)
        rows = () if graph is None else graph.observations
        span = (
            0
            if not rows
            else max(r.support_end_utc_ns for r in rows) - min(r.support_start_utc_ns for r in rows)
        )
        return (-span, -len(rows), review.tracklet_id)

    return sorted(reviews, key=key)


def _saved_track_reviews(product) -> tuple[Any, ...] | None:
    """Return persisted review evidence, or None for pre-review product contracts."""
    reviews = getattr(product, "track_reviews", None)
    return None if reviews is None else tuple(reviews)


def _propagate(satellite, utc_ns: np.ndarray, orbit_shift_s: float = 0.0):
    shifted = utc_ns + round(orbit_shift_s * _NS_PER_S)
    jd, fraction = julian_day_from_utc_ns(shifted)
    errors, position, velocity = satellite.sgp4_array(jd, fraction)
    if np.any(errors):
        raise ValueError(f"SGP4 error codes {tuple(sorted(set(map(int, errors[errors != 0]))))}")
    # Orbit time moves while Earth orientation remains anchored to receive UTC.
    original_jd, original_fraction = julian_day_from_utc_ns(utc_ns)
    return teme_to_ecef(
        position,
        velocity,
        greenwich_mean_sidereal_time_rad(original_jd, original_fraction),
    )


def prepare_scan_position_inputs(
    target_session_id: str,
    *,
    inputs,
    products,
    archive,
    maximum_target_tracks: int = 64,
    history_hours: float = 8.0,
    maximum_history_sessions: int = 16,
    maximum_total_tracks: int = 128,
    maximum_observations_per_track: int = 512,
) -> PreparedScanPositionInputs:
    """Prepare saved reviews without reranking identities or repartitioning rows."""
    if not 1 <= maximum_target_tracks <= 64:
        raise ValueError("maximum_target_tracks must be between 1 and 64")
    if not 0 < history_hours <= 24 or not 0 <= maximum_history_sessions <= 16:
        raise ValueError("history window bounds are invalid")
    if not maximum_target_tracks <= maximum_total_tracks <= 128:
        raise ValueError("maximum_total_tracks must be between target bound and 128")
    if not 14 <= maximum_observations_per_track <= 512:
        raise ValueError("maximum_observations_per_track must be between 14 and 512")

    exclusions: list[PositionInputExclusion] = []
    target_source_value = inputs.load(target_session_id)
    if not timing_is_qualified_for_tle(target_source_value.timing):
        target_status = products.status(target_session_id)
        if target_status.state == "complete" and target_status.product is None:
            raise ValueError("complete tracking status lacks its immutable product")
        if target_status.state == "complete" and (
            target_status.product.input_manifest_sha256 != target_source_value.input_manifest_sha256
            or target_status.product.analysis_manifest_sha256
            != target_source_value.analysis_manifest_sha256
        ):
            raise ValueError("tracking product source digest mismatch")
        target_product_digest = (
            canonical_digest(target_status.product.model_dump(mode="json"))
            if target_status.state == "complete" and target_status.product is not None
            else None
        )
        estimated_start = target_source_value.capture_start_utc_ns or (
            target_source_value.timing.first_sample_estimate_utc_ns
            if target_source_value.timing is not None
            else 0
        )
        target_provenance = PositionInputProvenance(
            target_session_id,
            target_source_value.input_manifest_sha256,
            target_source_value.analysis_manifest_sha256,
            target_product_digest,
            None,
            None,
            None,
        )
        exclusion = PositionInputExclusion(
            target_session_id,
            None,
            "utc-unqualified",
            "qualified absolute UTC is required for causal orbit states",
        )
        return PreparedScanPositionInputs(
            target_episodes=(),
            episodes=(),
            provenance=(target_provenance,),
            exclusions=(exclusion,),
            coverage=PositionInputCoverage(0, 0, 0, 0, 0, 0, 0, 0, 0, 1),
            target_source=PositionTargetSource(
                target_session_id,
                target_source_value.radio_id,
                estimated_start,
                target_source_value.input_manifest_sha256,
                target_source_value.analysis_manifest_sha256,
            ),
            source_manifest=(
                {
                    "session_id": target_session_id,
                    "input_manifest_sha256": target_source_value.input_manifest_sha256,
                    "analysis_sha256": target_source_value.analysis_manifest_sha256,
                    "tracking_product_sha256": target_product_digest,
                },
            ),
            _runtime=(),
        )
    target_start = _capture_start(target_source_value)
    target_radio = target_source_value.radio_id
    candidates: list[tuple[str, int]] = []
    lower = target_start - round(history_hours * _NS_PER_H)
    for session_id in inputs.session_ids():
        try:
            captured = inputs.captured_at(session_id)
        except Exception as error:
            exclusions.append(
                PositionInputExclusion(session_id, None, "capture-time-unavailable", str(error))
            )
            continue
        if session_id != target_session_id and lower <= captured < target_start:
            candidates.append((session_id, captured))
    histories: list[tuple[str, int, Any]] = []
    for session_id, _captured in sorted(candidates, key=lambda item: (-item[1], item[0])):
        if len(histories) >= maximum_history_sessions:
            break
        try:
            source = inputs.load(session_id)
            start = _capture_start(source)
        except Exception as error:
            exclusions.append(
                PositionInputExclusion(session_id, None, "source-unavailable", str(error))
            )
            continue
        if source.radio_id == target_radio and lower <= start < target_start:
            history_status = products.status(session_id)
            history_reviews = (
                _saved_track_reviews(history_status.product)
                if history_status.product is not None
                else None
            )
            if (
                history_status.state != "complete"
                or history_status.product is None
                or not history_reviews
            ):
                exclusions.append(
                    PositionInputExclusion(
                        session_id,
                        None,
                        (
                            "history-tracking-review-contract-unavailable"
                            if history_status.state == "complete"
                            and history_status.product is not None
                            and history_reviews is None
                            else "history-tracking-review-not-complete"
                        ),
                    )
                )
                continue
            histories.append((session_id, start, source))
    selected_sessions = [(target_session_id, target_start, target_source_value), *histories]

    prepared_sessions: list[tuple[Any, ...]] = []
    provenance: list[PositionInputProvenance] = []
    saved_review_count = 0
    for session_id, start, source in selected_sessions:
        status = products.status(session_id)
        product_digest = (
            canonical_digest(status.product.model_dump(mode="json"))
            if status.product is not None
            else None
        )
        provenance_index = len(provenance)
        provenance.append(
            PositionInputProvenance(
                session_id,
                source.input_manifest_sha256,
                source.analysis_manifest_sha256,
                product_digest,
                None,
                None,
                None,
            )
        )
        if status.state != "complete" or status.product is None:
            exclusions.append(
                PositionInputExclusion(session_id, None, "tracking-product-not-complete")
            )
            continue
        product = status.product
        if (
            product.input_manifest_sha256 != source.input_manifest_sha256
            or product.analysis_manifest_sha256 != source.analysis_manifest_sha256
        ):
            exclusions.append(
                PositionInputExclusion(session_id, None, "tracking-product-source-digest-mismatch")
            )
            continue
        reviews = _saved_track_reviews(product)
        if reviews is None:
            exclusions.append(
                PositionInputExclusion(
                    session_id, None, "tracking-review-contract-unavailable"
                )
            )
            continue
        if not reviews or product.original_tle_snapshot is None:
            exclusions.append(
                PositionInputExclusion(session_id, None, "saved-review-or-snapshot-unavailable")
            )
            continue
        try:
            snapshot = archive.select_latest_before(start - 505 * _NS_PER_S)
            if snapshot.digest != product.original_tle_snapshot.digest:
                raise ValueError(
                    "saved original snapshot digest differs from causal archive selection"
                )
            payload = archive.read(snapshot)
            catalogue = parse_element_sets(payload)
            trajectory = reconstruct_persistent_hop_trajectories(
                project_scanner_candidates(source), config=PersistentHopTrajectoryConfig()
            )
        except Exception as error:
            exclusions.append(
                PositionInputExclusion(session_id, None, "session-preparation-failed", str(error))
            )
            continue
        graphs = _graph_by_tracklet(trajectory)
        ranked_reviews = _rank_reviews(reviews, graphs)
        saved_review_count += len(ranked_reviews)
        try:
            digest = _selection_digest(_review_site(product.observer_site))
        except ValueError as error:
            exclusions.append(
                PositionInputExclusion(
                    session_id, None, "review-site-preset-unavailable", str(error)
                )
            )
            continue
        provenance[provenance_index] = PositionInputProvenance(
            session_id,
            source.input_manifest_sha256,
            source.analysis_manifest_sha256,
            product_digest,
            snapshot.digest,
            snapshot.collected_utc_ns,
            digest,
        )
        prepared_sessions.append(
            (session_id, start, source, product, catalogue, graphs, ranked_reviews, digest)
        )

    target_tracks: list[tuple[tuple[Any, ...], Any]] = []
    history_by_session: list[list[tuple[tuple[Any, ...], Any]]] = []
    for item in prepared_sessions:
        if item[0] == target_session_id:
            target_tracks = [(item, review) for review in item[6][:maximum_target_tracks]]
        else:
            history_by_session.append([(item, review) for review in item[6]])
    chosen = list(target_tracks)
    cursor = 0
    while len(chosen) < maximum_total_tracks and any(
        cursor < len(session_tracks) for session_tracks in history_by_session
    ):
        for session_tracks in history_by_session:
            if len(chosen) >= maximum_total_tracks:
                break
            if cursor < len(session_tracks):
                chosen.append(session_tracks[cursor])
        cursor += 1

    episodes: list[ScanPositionEpisode] = []
    runtime: list[_RuntimeEpisode] = []
    target_episode_count = 0
    seen_observations: set[str] = set()
    for session, review in chosen:
        session_id, start, _source, _product, catalogue, graphs, _reviews, selection_digest = (
            session
        )
        graph = graphs.get(review.tracklet_id)
        if graph is None:
            exclusions.append(
                PositionInputExclusion(
                    session_id, review.tracklet_id, "ambiguous-or-missing-tracklet"
                )
            )
            continue
        observation_rows = sorted(
            graph.observations, key=lambda row: (row.support_center_utc_ns, row.observation_id)
        )
        ids = tuple(row.observation_id for row in observation_rows)
        if len(observation_rows) > maximum_observations_per_track:
            exclusions.append(
                PositionInputExclusion(
                    session_id,
                    review.tracklet_id,
                    "observation-bound-exceeded",
                    str(len(observation_rows)),
                )
            )
            continue
        overlap = tuple(sorted(set(ids) & seen_observations))
        if overlap:
            exclusions.append(
                PositionInputExclusion(
                    session_id,
                    review.tracklet_id,
                    "overlapping-alternative-hypothesis",
                    f"{len(overlap)} duplicate observation IDs",
                )
            )
            continue
        support = CataloguePredictionSupportV1.from_graph(graph)
        seed = canonical_digest(
            {
                "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
                "response_free_support_digest": support.content_digest,
                "selection_protocol_digest": selection_digest,
            }
        )
        training_ids, evaluation_ids = deterministic_randomized_observation_partition(
            ids, training_fraction=0.6, split_seed=seed
        )
        if (len(training_ids), len(evaluation_ids)) != (
            review.fit_observation_count,
            review.randomized_evaluation_observation_count,
        ):
            exclusions.append(
                PositionInputExclusion(
                    session_id, review.tracklet_id, "saved-partition-count-mismatch"
                )
            )
            continue
        by_number = {number: index for index, number in enumerate(catalogue.satellite_numbers)}
        epochs = catalogue.element_epoch_utc_ns()
        candidate_indices = []
        accepted_candidates = []
        bad = None
        for rank, candidate in enumerate(review.candidates):
            index = by_number.get(candidate.catalog_number)
            reason = (
                "absent from snapshot"
                if index is None
                else "element epoch is not before capture"
                if epochs[index] >= start
                else None
            )
            if reason is not None:
                detail = f"candidate {candidate.catalog_number} {reason}"
                if rank == 0:
                    bad = detail
                    break
                exclusions.append(
                    PositionInputExclusion(
                        session_id,
                        review.tracklet_id,
                        "alternative-candidate-not-causal",
                        detail,
                    )
                )
                continue
            assert index is not None
            candidate_indices.append(index)
            accepted_candidates.append(candidate)
        if bad is not None:
            exclusions.append(
                PositionInputExclusion(session_id, review.tracklet_id, "candidate-not-causal", bad)
            )
            continue
        utc_ns = np.asarray([row.support_center_utc_ns for row in observation_rows], dtype=np.int64)
        positions, velocities = [], []
        minus_p, minus_v, plus_p, plus_v = [], [], [], []
        minus2_p, minus2_v, plus2_p, plus2_v = [], [], [], []
        try:
            for index in candidate_indices:
                p, v = _propagate(catalogue.satellites[index], utc_ns)
                pm, vm = _propagate(catalogue.satellites[index], utc_ns, -1.0)
                pp, vp = _propagate(catalogue.satellites[index], utc_ns, 1.0)
                pm2, vm2 = _propagate(catalogue.satellites[index], utc_ns, -2.0)
                pp2, vp2 = _propagate(catalogue.satellites[index], utc_ns, 2.0)
                positions.append(p)
                velocities.append(v)
                minus_p.append(pm)
                minus_v.append(vm)
                plus_p.append(pp)
                plus_v.append(vp)
                minus2_p.append(pm2)
                minus2_v.append(vm2)
                plus2_p.append(pp2)
                plus2_v.append(vp2)
        except ValueError as error:
            exclusions.append(
                PositionInputExclusion(
                    session_id, review.tracklet_id, "candidate-propagation-failed", str(error)
                )
            )
            continue
        training_set = set(training_ids)
        episode = ScanPositionEpisode(
            track_id=f"{session_id}:{review.tracklet_id}",
            pass_id=f"{session_id}:{review.candidates[0].catalog_number}",
            observation_id=np.asarray(ids),
            observed_hz=np.asarray([row.measured_cfo_hz for row in observation_rows], dtype=float),
            training=np.asarray([identity in training_set for identity in ids], dtype=bool),
            time_s=(utc_ns - start).astype(float) / _NS_PER_S,
            candidate_id=np.asarray(
                [candidate.catalog_number for candidate in accepted_candidates]
            ),
            position_ecef_km=np.asarray(positions),
            velocity_ecef_km_s=np.asarray(velocities),
            catalogue_size=len(catalogue),
            visible=np.ones(len(candidate_indices), dtype=bool),
            orbit_age_h=np.asarray(
                [
                    [(instant - epochs[index]) / _NS_PER_H for instant in utc_ns]
                    for index in candidate_indices
                ]
            ),
            phase_position_minus_ecef_km=np.asarray(minus_p),
            phase_velocity_minus_ecef_km_s=np.asarray(minus_v),
            phase_position_plus_ecef_km=np.asarray(plus_p),
            phase_velocity_plus_ecef_km_s=np.asarray(plus_v),
            phase_position_minus2_ecef_km=np.asarray(minus2_p),
            phase_velocity_minus2_ecef_km_s=np.asarray(minus2_v),
            phase_position_plus2_ecef_km=np.asarray(plus2_p),
            phase_velocity_plus2_ecef_km_s=np.asarray(plus2_v),
        )
        seen_observations.update(ids)
        episodes.append(episode)
        runtime.append(
            _RuntimeEpisode(
                session_id,
                utc_ns,
                tuple(catalogue.satellites[index] for index in candidate_indices),
            )
        )
        if session_id == target_session_id:
            target_episode_count += 1

    all_episodes = tuple(episodes)
    observations = sum(len(item.observed_hz) for item in all_episodes)
    training = sum(int(np.sum(item.training)) for item in all_episodes)
    manifest = tuple(
        {
            "session_id": item.session_id,
            "input_manifest_sha256": item.input_manifest_sha256,
            "analysis_sha256": item.analysis_sha256,
            "tracking_product_sha256": item.tracking_product_sha256,
        }
        for item in provenance
    )
    return PreparedScanPositionInputs(
        target_episodes=all_episodes[:target_episode_count],
        episodes=all_episodes,
        provenance=tuple(provenance),
        exclusions=tuple(exclusions),
        coverage=PositionInputCoverage(
            1 + len(histories),
            len(prepared_sessions),
            saved_review_count,
            len(all_episodes),
            target_episode_count,
            len(all_episodes) - target_episode_count,
            observations,
            training,
            observations - training,
            len(exclusions),
        ),
        target_source=PositionTargetSource(
            target_session_id,
            target_radio,
            target_start,
            target_source_value.input_manifest_sha256,
            target_source_value.analysis_manifest_sha256,
        ),
        source_manifest=manifest,
        _runtime=tuple(runtime),
    )


def verify_orbit_fit(
    prepared: PreparedScanPositionInputs, result, *, altitude_m: float = 0.0
) -> dict[str, Any]:
    """Audit interpolated fitted orbit corrections against exact SGP4 replay."""
    if isinstance(result, dict):
        corrections = result.get("diagnostics", {}).get("rate_corrections_s_h", {})
        latitude, longitude = result["latitude_deg"], result["longitude_deg"]
    else:
        corrections = result.diagnostics.get("rate_corrections_s_h", {})
        latitude, longitude = result.latitude_deg, result.longitude_deg
    receiver = geodetic_to_ecef_km(latitude, longitude, altitude_m)
    errors: list[float] = []
    compared = 0
    for episode, runtime in zip(prepared.episodes, prepared._runtime, strict=True):
        source = str(episode.candidate_id[0])
        rate = corrections.get(source, corrections.get(int(episode.candidate_id[0]), 0.0))
        age_states = episode.orbit_age_h
        position_minus = episode.phase_position_minus_ecef_km
        position_plus = episode.phase_position_plus_ecef_km
        velocity_minus = episode.phase_velocity_minus_ecef_km_s
        velocity_plus = episode.phase_velocity_plus_ecef_km_s
        if (
            age_states is None
            or position_minus is None
            or position_plus is None
            or velocity_minus is None
            or velocity_plus is None
        ):
            raise ValueError("orbit-fit audit requires ages and phase states")
        age = age_states[0]
        shift = np.asarray(age) * float(rate)
        satellite = runtime.satellites[0]
        exact_p: list[np.ndarray] = []
        exact_v: list[np.ndarray] = []
        for utc, seconds in zip(runtime.observation_utc_ns, shift, strict=True):
            p, v = _propagate(satellite, np.asarray([utc]), float(seconds))
            exact_p.append(p[0])
            exact_v.append(v[0])
        centre_p = episode.position_ecef_km[0]
        centre_v = episode.velocity_ecef_km_s[0]
        approximate_p = phase_state(
            centre_p,
            position_minus[0],
            position_plus[0],
            shift,
            1.0,
            minus2=(
                episode.phase_position_minus2_ecef_km[0]
                if episode.phase_position_minus2_ecef_km is not None
                else None
            ),
            plus2=(
                episode.phase_position_plus2_ecef_km[0]
                if episode.phase_position_plus2_ecef_km is not None
                else None
            ),
        )
        approximate_v = phase_state(
            centre_v,
            velocity_minus[0],
            velocity_plus[0],
            shift,
            1.0,
            minus2=(
                episode.phase_velocity_minus2_ecef_km_s[0]
                if episode.phase_velocity_minus2_ecef_km_s is not None
                else None
            ),
            plus2=(
                episode.phase_velocity_plus2_ecef_km_s[0]
                if episode.phase_velocity_plus2_ecef_km_s is not None
                else None
            ),
        )
        difference = doppler_hz(receiver, np.asarray(exact_p), np.asarray(exact_v)) - doppler_hz(
            receiver, approximate_p, approximate_v
        )
        errors.extend(map(float, difference))
        compared += len(difference)
    values: np.ndarray = np.asarray(errors, dtype=np.float64)
    return {
        "schema": "scan-position-orbit-phase-state-exact-audit-v1",
        "compared_observation_count": compared,
        "maximum_absolute_doppler_error_hz": float(np.max(np.abs(values))) if len(values) else None,
        "rms_doppler_error_hz": (
            float(np.sqrt(np.mean(np.square(values)))) if len(values) else None
        ),
        "earth_rotation_time_basis": "original-observation-utc",
        "truth_used": False,
    }
