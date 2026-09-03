"""Bounded orchestration for long-scan trajectories and causal TLE matching."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from leo.analysis.persistent_hop_tle_match import (
    PersistentHopTleMatchConfig,
    PersistentHopTleMatchInputError,
    PersistentHopTleMatchResult,
    match_persistent_hop_track_to_tles,
)
from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopPhysicalGroup,
    PersistentHopTracklet,
    PersistentHopTrajectoryConfig,
    PersistentHopTrajectoryHypothesis,
    PersistentHopTrajectoryInputError,
    PersistentHopTrajectoryResult,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.persistent_hop_trajectory import (
    PersistentHopTrajectoryProjection,
    PersistentHopTrajectoryProjectionConfig,
    PersistentHopTrajectoryProjectionError,
    project_fractional_persistent_hop_candidates,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.operations.tle_archive import TleArchiveReader, TleSnapshotRef
from leo.scanner.persistent_hop_tracking import (
    PersistentHopTleCandidateV1,
    PersistentHopTrackingArtifactV1,
    PersistentHopTrackingManifestV1,
    PersistentHopTrackingStatusV1,
    PersistentHopTrajectoryTrackletV1,
    PersistentHopUnscoredGroupV1,
)
from leo.sky.propagation import parse_element_sets
from leo.storage.persistent_hop import PersistentHopIqSessionManifestV2, PersistentHopIqStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore

_NS_PER_S = 1_000_000_000


class PersistentHopTrackingRenderer(Protocol):
    def __call__(
        self,
        trajectory: PersistentHopTrajectoryResult,
        candidates: tuple[PersistentHopCfoCandidate, ...],
        associations: tuple[PersistentHopTleCandidateV1, ...],
    ) -> bytes: ...


PersistentHopTleMatcher = Callable[..., PersistentHopTleMatchResult]


@dataclass(frozen=True, slots=True)
class PersistentHopTrackingRunSummaryV1:
    requested_session_count: int
    completed_session_ids: tuple[str, ...]
    unsupported_session_ids: tuple[str, ...]
    skipped_session_ids: tuple[str, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _GroupWork:
    hypothesis_rank: int
    hypothesis: PersistentHopTrajectoryHypothesis
    group: PersistentHopPhysicalGroup
    representative: PersistentHopTracklet


class PersistentHopTrackingService:
    """Create one immutable, bounded tracking publication per complete V2 scan."""

    def __init__(
        self,
        *,
        captures: PersistentHopIqStore,
        analyses: PersistentHopAnalysisStoreV2,
        products: PersistentHopTrackingStore,
        tle_archive: TleArchiveReader,
        observer_site: ObserverSiteV1,
        renderer: PersistentHopTrackingRenderer,
        projection_config: PersistentHopTrajectoryProjectionConfig | None = None,
        trajectory_config: PersistentHopTrajectoryConfig | None = None,
        maximum_physical_groups: int = 4,
        matcher: PersistentHopTleMatcher = match_persistent_hop_track_to_tles,
    ) -> None:
        if not 1 <= maximum_physical_groups <= 32:
            raise ValueError("tracking physical-group bound must lie in 1..32")
        self._captures = captures
        self._analyses = analyses
        self._products = products
        self._tle_archive = tle_archive
        self._observer_site = ObserverSiteV1.model_validate(observer_site.model_dump(mode="json"))
        self._renderer = renderer
        self._projection_config = projection_config or PersistentHopTrajectoryProjectionConfig()
        self._trajectory_config = trajectory_config or PersistentHopTrajectoryConfig()
        self._maximum_physical_groups = maximum_physical_groups
        self._matcher = matcher

    def track_session(self, session_id: str) -> PersistentHopTrackingManifestV1:
        if self._products.is_terminal(session_id):
            return self._products.inspect(session_id).manifest
        capture = self._captures.inspect(session_id)
        analysis = self._analyses.inspect(session_id)
        created_at = datetime.now(tz=UTC)
        self._status(session_id, "running", "projection")
        if not isinstance(capture.manifest, PersistentHopIqSessionManifestV2):
            return self._terminal_without_trajectory(
                session_id=session_id,
                created_at=created_at,
                capture_manifest_sha256=capture.manifest_sha256,
                analysis_manifest_sha256=analysis.manifest_sha256,
                outcome="unsupported",
                reason="utc-timing-authority-unavailable-in-capture-manifest-v1",
            )
        if analysis.manifest.input_manifest_sha256 != capture.manifest_sha256:
            raise ValueError(
                "fractional analysis input digest does not match the inspected capture"
            )
        try:
            projection = project_fractional_persistent_hop_candidates(
                capture.manifest,
                self._analyses.published_chunks(session_id),
                input_manifest_sha256=capture.manifest_sha256,
                config=self._projection_config,
            )
        except PersistentHopTrajectoryProjectionError as error:
            return self._terminal_without_trajectory(
                session_id=session_id,
                created_at=created_at,
                capture_manifest_sha256=capture.manifest_sha256,
                analysis_manifest_sha256=analysis.manifest_sha256,
                outcome="unsupported",
                reason=f"trajectory-projection-unavailable: {error}",
            )
        if not projection.candidates:
            return self._terminal_without_trajectory(
                session_id=session_id,
                created_at=created_at,
                capture_manifest_sha256=capture.manifest_sha256,
                analysis_manifest_sha256=analysis.manifest_sha256,
                outcome="no-trajectory",
                reason="no-passing-fractional-candidates",
                projection=projection,
            )
        self._status(session_id, "running", "trajectory")
        try:
            trajectory = reconstruct_persistent_hop_trajectories(
                projection.candidates,
                config=self._trajectory_config,
            )
        except PersistentHopTrajectoryInputError as error:
            if "no alias-aware track" not in str(error):
                raise
            return self._terminal_without_trajectory(
                session_id=session_id,
                created_at=created_at,
                capture_manifest_sha256=capture.manifest_sha256,
                analysis_manifest_sha256=analysis.manifest_sha256,
                outcome="no-trajectory",
                reason=f"no-track-met-frozen-geometry: {error}",
                projection=projection,
            )

        group_work, total_group_count = self._select_groups(trajectory)
        self._status(
            session_id,
            "running",
            "tle-matching",
            total_groups=len(group_work),
        )
        earliest_utc_ns = min(item.support_start_utc_ns for item in trajectory.graph.observations)
        snapshot = self._tle_archive.select_latest_before(earliest_utc_ns - 500 * _NS_PER_S)
        snapshot_payload = self._tle_archive.read(snapshot)
        tle_snapshot = self._snapshot_contract(snapshot, snapshot_payload)
        match_config = PersistentHopTleMatchConfig(
            selection_protocol_digest=canonical_digest(
                {
                    "protocol": "persistent-hop-full-starlink-horizon-before-response-v1",
                    "observer_site": self._observer_site.model_dump(mode="json"),
                    "trajectory_config_digest": self._trajectory_config.digest,
                    "tle_matching_group_limit": self._maximum_physical_groups,
                }
            ),
            nominal_rf_hz=self._trajectory_config.canonical_rf_hz,
        )
        matched: list[PersistentHopTleCandidateV1] = []
        unscored: list[PersistentHopUnscoredGroupV1] = []
        for index, work in enumerate(group_work):
            graph = persistent_hop_tracklet_graph(
                work.hypothesis,
                work.representative.tracklet_id,
            )
            try:
                result = self._matcher(
                    graph,
                    snapshot_payload,
                    tle_snapshot=tle_snapshot,
                    observer_site=self._observer_site,
                    config=match_config,
                )
            except PersistentHopTleMatchInputError as error:
                unscored.append(self._unscored(work, str(error)))
            else:
                matched.append(self._candidate_summary(work, result))
            self._status(
                session_id,
                "running",
                "tle-matching",
                completed_groups=index + 1,
                total_groups=len(group_work),
            )
        tracklets = tuple(self._tracklet_summary(item) for item in trajectory.tracklets)
        artifact_payload = self._renderer(trajectory, projection.candidates, tuple(matched))
        artifact = PersistentHopTrackingArtifactV1(
            sha256=sha256_digest(artifact_payload),
            byte_count=len(artifact_payload),
        )
        manifest = PersistentHopTrackingManifestV1.create(
            session_id=session_id,
            created_at=created_at,
            completed_at=datetime.now(tz=UTC),
            input_manifest_sha256=capture.manifest_sha256,
            fractional_analysis_manifest_sha256=analysis.manifest_sha256,
            projection_config_digest=self._projection_config.digest,
            trajectory_config_digest=self._trajectory_config.digest,
            tle_match_config_digest=match_config.digest,
            observer_site=self._observer_site,
            tle_snapshot=tle_snapshot,
            terminal_outcome="complete",
            terminal_reasons=(),
            input_probe_count=projection.input_probe_count,
            nonoverlapping_probe_count=projection.nonoverlapping_probe_count,
            passing_fractional_candidate_count=projection.passing_fractional_candidate_count,
            projected_candidate_count=projection.projected_candidate_count,
            trajectory_hypothesis_count=len(trajectory.hypotheses),
            physical_group_count=total_group_count,
            tle_matching_group_limit=self._maximum_physical_groups,
            tle_matching_attempted_group_count=len(group_work),
            tracklets=tracklets,
            tle_candidates=tuple(matched),
            unscored_groups=tuple(unscored),
            unscored_physical_group_count=(total_group_count - len(matched)),
            artifact=artifact,
        )
        return self._products.publish(manifest, artifact=artifact_payload).manifest

    def run_pending(
        self,
        *,
        maximum_sessions: int = 1,
        session_id: str | None = None,
    ) -> PersistentHopTrackingRunSummaryV1:
        if not 1 <= maximum_sessions <= 100:
            raise ValueError("tracking session bound must lie in 1..100")
        candidates = (session_id,) if session_id is not None else self._captures.session_ids()
        ready = tuple(
            item
            for item in candidates
            if self._analyses.is_complete(item)
            and not self._products.is_terminal(item)
            and (session_id is not None or self._products.status(item).state != "failed")
        )
        selected = ready[:maximum_sessions]
        completed: list[str] = []
        unsupported: list[str] = []
        failures: list[str] = []
        for candidate in selected:
            try:
                manifest = self.track_session(candidate)
            except Exception as error:
                self._products.write_status(
                    PersistentHopTrackingStatusV1(
                        session_id=candidate,
                        state="failed",
                        phase="waiting",
                        updated_at=datetime.now(tz=UTC),
                        failure_summary=f"{type(error).__name__}: {error}"[:512],
                    )
                )
                failures.append(f"{candidate}: {type(error).__name__}: {error}")
            else:
                if manifest.terminal_outcome == "complete":
                    completed.append(candidate)
                else:
                    unsupported.append(candidate)
        return PersistentHopTrackingRunSummaryV1(
            requested_session_count=len(selected),
            completed_session_ids=tuple(completed),
            unsupported_session_ids=tuple(unsupported),
            skipped_session_ids=tuple(item for item in candidates if item not in selected),
            failures=tuple(failures),
        )

    def _terminal_without_trajectory(
        self,
        *,
        session_id: str,
        created_at: datetime,
        capture_manifest_sha256: str,
        analysis_manifest_sha256: str,
        outcome: str,
        reason: str,
        projection: PersistentHopTrajectoryProjection | None = None,
    ) -> PersistentHopTrackingManifestV1:
        manifest = PersistentHopTrackingManifestV1.create(
            session_id=session_id,
            created_at=created_at,
            completed_at=datetime.now(tz=UTC),
            input_manifest_sha256=capture_manifest_sha256,
            fractional_analysis_manifest_sha256=analysis_manifest_sha256,
            projection_config_digest=self._projection_config.digest,
            trajectory_config_digest=self._trajectory_config.digest,
            terminal_outcome=outcome,
            terminal_reasons=(reason,),
            input_probe_count=0 if projection is None else projection.input_probe_count,
            nonoverlapping_probe_count=(
                0 if projection is None else projection.nonoverlapping_probe_count
            ),
            passing_fractional_candidate_count=(
                0 if projection is None else projection.passing_fractional_candidate_count
            ),
            projected_candidate_count=(
                0 if projection is None else projection.projected_candidate_count
            ),
            tle_matching_group_limit=self._maximum_physical_groups,
        )
        return self._products.publish(manifest, artifact=None).manifest

    def _select_groups(
        self,
        trajectory: PersistentHopTrajectoryResult,
    ) -> tuple[tuple[_GroupWork, ...], int]:
        tracklet_by_id = {item.tracklet_id: item for item in trajectory.tracklets}
        work: list[_GroupWork] = []
        total = 0
        for hypothesis_rank, hypothesis in enumerate(trajectory.hypotheses, start=1):
            for group in hypothesis.physical_groups:
                total += 1
                if len(work) >= self._maximum_physical_groups:
                    continue
                members = tuple(tracklet_by_id[item] for item in group.tracklet_ids)
                representative = max(
                    members,
                    key=lambda item: (
                        len(item.points),
                        item.end_utc_ns - item.start_utc_ns,
                        item.weighted_support,
                        item.tracklet_id,
                    ),
                )
                work.append(
                    _GroupWork(
                        hypothesis_rank=hypothesis_rank,
                        hypothesis=hypothesis,
                        group=group,
                        representative=representative,
                    )
                )
        return tuple(work), total

    @staticmethod
    def _snapshot_contract(snapshot: TleSnapshotRef, payload: str) -> TleSnapshotRefV1:
        catalogue = parse_element_sets(payload)
        if snapshot.provider not in ("space-track", "huggingface"):
            raise ValueError("TLE snapshot provider is unsupported")
        return TleSnapshotRefV1(
            provider=cast(Literal["space-track", "huggingface"], snapshot.provider),
            collected_utc_ns=snapshot.collected_utc_ns,
            digest=snapshot.digest,
            object_count=len(catalogue),
        )

    @staticmethod
    def _tracklet_summary(tracklet: PersistentHopTracklet) -> PersistentHopTrajectoryTrackletV1:
        channel, edge, receiver_id, actual_rf_hz = tracklet.lane_key
        return PersistentHopTrajectoryTrackletV1(
            tracklet_id=tracklet.tracklet_id,
            channel=channel,
            edge=edge.value,
            receiver_id=receiver_id,
            actual_rf_hz=actual_rf_hz,
            start_utc_ns=tracklet.start_utc_ns,
            end_utc_ns=tracklet.end_utc_ns,
            observation_count=len(tracklet.points),
            normalized_rate_hz_per_s=tracklet.normalized_rate_hz_per_s,
            residual_rms_hz=tracklet.residual_rms_hz,
        )

    @staticmethod
    def _unscored(work: _GroupWork, reason: str) -> PersistentHopUnscoredGroupV1:
        return PersistentHopUnscoredGroupV1(
            hypothesis_rank=work.hypothesis_rank,
            hypothesis_id=work.hypothesis.hypothesis_id,
            physical_group_id=work.group.group_id,
            representative_tracklet_id=work.representative.tracklet_id,
            reason=reason[:512],
        )

    @staticmethod
    def _candidate_summary(
        work: _GroupWork,
        result: PersistentHopTleMatchResult,
    ) -> PersistentHopTleCandidateV1:
        nominal = next(item for item in result.field_matches if item.field_delta_s == 0)
        minus = next(item for item in result.field_matches if item.field_delta_s == -500)
        plus = next(item for item in result.field_matches if item.field_delta_s == 500)
        association = nominal.association
        winner = association.scores[0]
        return PersistentHopTleCandidateV1(
            hypothesis_rank=work.hypothesis_rank,
            hypothesis_id=work.hypothesis.hypothesis_id,
            physical_group_id=work.group.group_id,
            representative_tracklet_id=work.representative.tracklet_id,
            tracklet_ids=work.group.tracklet_ids,
            source_observation_count=result.source_observation_count,
            scored_observation_count=result.scored_observation_count,
            support_span_s=result.support_span_s,
            nominal_candidate_count=nominal.candidate_count,
            leading_catalog_number=result.leading_catalog_number,
            selected_tau_s=winner.selected_tau_s,
            training_runner_negative_log_score_margin=(
                association.training_runner_negative_log_score_margin
            ),
            training_leader_heldout_rank=association.training_nearest_heldout_rank,
            heldout_runner_negative_log_score_margin=(
                association.heldout_runner_negative_log_score_margin
            ),
            nominal_heldout_negative_log_score=(winner.heldout_predictive_negative_log_score),
            radio_null_heldout_negative_log_score=min(
                item.evaluation_predictive_negative_log_likelihood
                for item in result.radio_polynomial_null.scores
            ),
            wrong_time_minus_500_heldout_negative_log_score=(
                minus.association.scores[0].heldout_predictive_negative_log_score
            ),
            wrong_time_plus_500_heldout_negative_log_score=(
                plus.association.scores[0].heldout_predictive_negative_log_score
            ),
            leading_candidate_persisted_on_heldout=(result.leading_candidate_persisted_on_heldout),
            abstention_recommended=result.abstention_recommended,
            abstention_reasons=result.abstention_reasons,
            match_content_digest=result.content_digest,
        )

    def _status(
        self,
        session_id: str,
        state: Literal["running"],
        phase: Literal["projection", "trajectory", "tle-matching"],
        *,
        completed_groups: int = 0,
        total_groups: int = 0,
    ) -> None:
        self._products.write_status(
            PersistentHopTrackingStatusV1(
                session_id=session_id,
                state=state,
                phase=phase,
                completed_groups=completed_groups,
                total_groups=total_groups,
                updated_at=datetime.now(tz=UTC),
            )
        )


__all__ = ["PersistentHopTrackingRunSummaryV1", "PersistentHopTrackingService"]
