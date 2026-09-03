"""Additive contracts for long-scan trajectories and causal TLE candidates."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.scanner.models import ScannerModel

TrackingState = Literal["pending", "running", "complete", "unsupported", "failed"]


class PersistentHopTrackingStatusV1(ScannerModel):
    """Mutable operational status; only a sealed manifest is scientific output."""

    schema_version: Literal[1] = 1
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    analysis_id: Literal["persistent-hop-causal-tle-tracking-v1"] = (
        "persistent-hop-causal-tle-tracking-v1"
    )
    state: TrackingState
    phase: Literal["waiting", "projection", "trajectory", "tle-matching", "complete"]
    completed_groups: Annotated[int, Field(ge=0, le=32)] = 0
    total_groups: Annotated[int, Field(ge=0, le=32)] = 0
    updated_at: datetime
    failure_summary: Annotated[str | None, Field(max_length=512)] = None

    @model_validator(mode="after")
    def _state_is_coherent(self) -> Self:
        if self.completed_groups > self.total_groups:
            raise ValueError("tracking completed groups exceed the total")
        if self.state in ("complete", "unsupported") and self.phase != "complete":
            raise ValueError("terminal tracking status must be in the complete phase")
        if self.state == "complete" and self.completed_groups != self.total_groups:
            raise ValueError("complete tracking status has unfinished groups")
        if self.state == "failed" and not self.failure_summary:
            raise ValueError("failed tracking status lacks an error summary")
        if self.state != "failed" and self.failure_summary is not None:
            raise ValueError("non-failed tracking status carries an error summary")
        return self


class PersistentHopTrajectoryTrackletV1(ScannerModel):
    """Compact, source-bound summary of one TLE-blind path-local tracklet."""

    schema_version: Literal[1] = 1
    tracklet_id: Sha256Digest
    channel: Annotated[int, Field(ge=1, le=4)]
    edge: Literal["lower", "upper"]
    receiver_id: Annotated[int, Field(ge=0, le=16)]
    actual_rf_hz: Annotated[float, Field(gt=0)]
    start_utc_ns: Annotated[int, Field(gt=0)]
    end_utc_ns: Annotated[int, Field(gt=0)]
    observation_count: Annotated[int, Field(ge=2, le=4096)]
    normalized_rate_hz_per_s: float
    residual_rms_hz: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _geometry_is_finite(self) -> Self:
        if self.end_utc_ns <= self.start_utc_ns:
            raise ValueError("trajectory tracklet ends before it starts")
        if any(
            not math.isfinite(value)
            for value in (
                self.actual_rf_hz,
                self.normalized_rate_hz_per_s,
                self.residual_rms_hz,
            )
        ):
            raise ValueError("trajectory tracklet geometry is not finite")
        return self


class PersistentHopTleCandidateV1(ScannerModel):
    """Heldout and negative-control diagnostics for one physical group."""

    schema_version: Literal[1] = 1
    hypothesis_rank: Annotated[int, Field(ge=1, le=16)]
    hypothesis_id: Sha256Digest
    physical_group_id: Sha256Digest
    representative_tracklet_id: Sha256Digest
    tracklet_ids: Annotated[tuple[Sha256Digest, ...], Field(min_length=1, max_length=16)]
    source_observation_count: Annotated[int, Field(ge=2, le=4096)]
    scored_observation_count: Annotated[int, Field(ge=2, le=1024)]
    support_span_s: Annotated[float, Field(gt=0)]
    nominal_candidate_count: Annotated[int, Field(ge=1, le=100_000)]
    leading_catalog_number: Annotated[int | None, Field(ge=1)] = None
    selected_tau_s: float | None = None
    training_runner_negative_log_score_margin: Annotated[float | None, Field(ge=0)] = None
    training_leader_heldout_rank: Annotated[int, Field(ge=1, le=100_001)]
    heldout_runner_negative_log_score_margin: Annotated[float | None, Field(ge=0)] = None
    nominal_heldout_negative_log_score: float
    radio_null_heldout_negative_log_score: float
    wrong_time_minus_500_heldout_negative_log_score: float
    wrong_time_plus_500_heldout_negative_log_score: float
    leading_candidate_persisted_on_heldout: bool
    abstention_recommended: bool
    abstention_reasons: Annotated[tuple[str, ...], Field(max_length=32)]
    match_content_digest: Sha256Digest
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _candidate_summary_is_coherent(self) -> Self:
        if len(set(self.tracklet_ids)) != len(self.tracklet_ids):
            raise ValueError("TLE candidate tracklets are not unique")
        if self.representative_tracklet_id not in self.tracklet_ids:
            raise ValueError("TLE candidate representative is absent")
        scalars = [
            self.support_span_s,
            self.nominal_heldout_negative_log_score,
            self.radio_null_heldout_negative_log_score,
            self.wrong_time_minus_500_heldout_negative_log_score,
            self.wrong_time_plus_500_heldout_negative_log_score,
        ]
        if self.selected_tau_s is not None:
            scalars.append(self.selected_tau_s)
        if any(not math.isfinite(value) for value in scalars):
            raise ValueError("TLE candidate diagnostics are not finite")
        if self.abstention_recommended != bool(self.abstention_reasons):
            raise ValueError("TLE candidate abstention flag disagrees with reasons")
        return self


class PersistentHopTrackingArtifactV1(ScannerModel):
    schema_version: Literal[1] = 1
    name: Literal["trajectory-tle"] = "trajectory-tle"
    relative_path: Literal["presentation/persistent-hop-trajectory-tle.v1.png"] = (
        "presentation/persistent-hop-trajectory-tle.v1.png"
    )
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class PersistentHopUnscoredGroupV1(ScannerModel):
    """A bounded explanation for a selected group that could not be matched."""

    schema_version: Literal[1] = 1
    hypothesis_rank: Annotated[int, Field(ge=1, le=16)]
    hypothesis_id: Sha256Digest
    physical_group_id: Sha256Digest
    representative_tracklet_id: Sha256Digest
    reason: Annotated[str, Field(min_length=1, max_length=512)]


class PersistentHopTrackingManifestV1(ScannerModel):
    """Sealed per-scan trajectory reconstruction and candidate-only TLE result."""

    schema_version: Literal[1] = 1
    kind: Literal["persistent_hop_causal_tle_tracking"] = "persistent_hop_causal_tle_tracking"
    analysis_id: Literal["persistent-hop-causal-tle-tracking-v1"] = (
        "persistent-hop-causal-tle-tracking-v1"
    )
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
    created_at: datetime
    completed_at: datetime
    input_manifest_sha256: Sha256Digest
    fractional_analysis_manifest_sha256: Sha256Digest
    projection_config_digest: Sha256Digest
    trajectory_config_digest: Sha256Digest
    tle_match_config_digest: Sha256Digest | None = None
    observer_site: ObserverSiteV1 | None = None
    tle_snapshot: TleSnapshotRefV1 | None = None
    terminal_outcome: Literal["complete", "no-trajectory", "unsupported"]
    terminal_reasons: Annotated[tuple[str, ...], Field(max_length=32)] = ()
    input_probe_count: Annotated[int, Field(ge=0)] = 0
    nonoverlapping_probe_count: Annotated[int, Field(ge=0)] = 0
    passing_fractional_candidate_count: Annotated[int, Field(ge=0)] = 0
    projected_candidate_count: Annotated[int, Field(ge=0)] = 0
    trajectory_hypothesis_count: Annotated[int, Field(ge=0, le=16)] = 0
    physical_group_count: Annotated[int, Field(ge=0, le=4096)] = 0
    tle_matching_group_limit: Annotated[int, Field(ge=1, le=32)] = 8
    tle_matching_attempted_group_count: Annotated[int, Field(ge=0, le=32)] = 0
    tracklets: Annotated[tuple[PersistentHopTrajectoryTrackletV1, ...], Field(max_length=128)] = ()
    tle_candidates: Annotated[tuple[PersistentHopTleCandidateV1, ...], Field(max_length=32)] = ()
    unscored_groups: Annotated[tuple[PersistentHopUnscoredGroupV1, ...], Field(max_length=32)] = ()
    unscored_physical_group_count: Annotated[int, Field(ge=0, le=4096)] = 0
    artifact: PersistentHopTrackingArtifactV1 | None = None
    content_digest: Sha256Digest
    fractional_epoch_required: Literal[True] = True
    utc_authority_required: Literal[True] = True
    tle_blind_trajectory_reconstruction: Literal[True] = True
    catalogue_selected_without_cfo_response: Literal[True] = True
    chronological_heldout_scoring: Literal[True] = True
    wrong_time_controls_included: Literal[True] = True
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False

    @classmethod
    def create(cls, **values: object) -> PersistentHopTrackingManifestV1:
        payload = {
            **values,
            "schema_version": 1,
            "kind": "persistent_hop_causal_tle_tracking",
            "analysis_id": "persistent-hop-causal-tle-tracking-v1",
            "fractional_epoch_required": True,
            "utc_authority_required": True,
            "tle_blind_trajectory_reconstruction": True,
            "catalogue_selected_without_cfo_response": True,
            "chronological_heldout_scoring": True,
            "wrong_time_controls_included": True,
            "candidate_only": True,
            "identity_claimed": False,
        }
        normalized = cls.model_construct(
            _fields_set=None,
            **payload,
            content_digest="sha256:" + "0" * 64,
        ).model_dump(mode="json", exclude={"content_digest"})
        return cls.model_validate({**normalized, "content_digest": canonical_digest(normalized)})

    @model_validator(mode="after")
    def _manifest_is_closed(self) -> Self:
        if self.completed_at < self.created_at:
            raise ValueError("tracking completion precedes creation")
        scientific_authority = (
            self.tle_match_config_digest,
            self.observer_site,
            self.tle_snapshot,
        )
        if self.terminal_outcome == "complete" and any(
            item is None for item in scientific_authority
        ):
            raise ValueError("complete tracking lacks TLE authority")
        if self.terminal_outcome != "complete" and self.tle_candidates:
            raise ValueError("non-complete tracking exposes TLE candidates")
        if self.terminal_outcome == "complete" and self.terminal_reasons:
            raise ValueError("complete tracking carries terminal failure reasons")
        if self.terminal_outcome != "complete" and not self.terminal_reasons:
            raise ValueError("non-complete tracking lacks a terminal reason")
        if self.nonoverlapping_probe_count > self.input_probe_count:
            raise ValueError("tracking non-overlap count exceeds input probes")
        if self.projected_candidate_count > self.passing_fractional_candidate_count:
            raise ValueError("tracking projected count exceeds passing candidates")
        if self.artifact is None and self.tracklets:
            raise ValueError("tracking tracklets lack their sealed visualization")
        if self.tle_matching_attempted_group_count > self.physical_group_count:
            raise ValueError("tracking attempted more TLE matches than physical groups")
        if self.tle_matching_attempted_group_count > self.tle_matching_group_limit:
            raise ValueError("tracking attempted TLE matches beyond its declared bound")
        if (
            len(self.tle_candidates) + len(self.unscored_groups)
            != self.tle_matching_attempted_group_count
        ):
            raise ValueError("tracking attempted-group disposition is incomplete")
        if self.unscored_physical_group_count != (
            self.physical_group_count - len(self.tle_candidates)
        ):
            raise ValueError("tracking unscored group count disagrees with its dispositions")
        if len(self.unscored_groups) > self.unscored_physical_group_count:
            raise ValueError("tracking unscored detail exceeds its group count")
        payload = self.model_dump(mode="json", exclude={"content_digest"})
        if canonical_digest(payload) != self.content_digest:
            raise ValueError("tracking manifest digest disagrees with content")
        return self


class PersistentHopTrackingDetailV1(ScannerModel):
    """Selectable monitoring view; pending work is a successful response."""

    schema_version: Literal[1] = 1
    status: PersistentHopTrackingStatusV1
    product: PersistentHopTrackingManifestV1 | None = None

    @model_validator(mode="after")
    def _detail_is_coherent(self) -> Self:
        if self.product is not None and self.product.session_id != self.status.session_id:
            raise ValueError("tracking detail product disagrees with status")
        if (self.status.state in ("complete", "unsupported")) != (self.product is not None):
            raise ValueError("tracking detail readiness disagrees with product")
        return self


class PersistentHopCandidateRecurrenceV1(ScannerModel):
    """Descriptive recurrence across independent scans, never an identity gate."""

    schema_version: Literal[1] = 1
    catalog_number: Annotated[int, Field(ge=1)]
    session_ids: Annotated[tuple[str, ...], Field(min_length=1, max_length=256)]
    scan_count: Annotated[int, Field(ge=1, le=256)]
    heldout_persistent_scan_count: Annotated[int, Field(ge=0, le=256)]
    nonabstaining_scan_count: Annotated[int, Field(ge=0, le=256)]
    first_support_utc_ns: Annotated[int, Field(gt=0)]
    last_support_utc_ns: Annotated[int, Field(gt=0)]
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _recurrence_is_coherent(self) -> Self:
        if self.scan_count != len(self.session_ids) or len(set(self.session_ids)) != len(
            self.session_ids
        ):
            raise ValueError("TLE recurrence scan inventory is inconsistent")
        if (
            self.heldout_persistent_scan_count > self.scan_count
            or self.nonabstaining_scan_count > self.scan_count
            or self.last_support_utc_ns < self.first_support_utc_ns
        ):
            raise ValueError("TLE recurrence accounting is inconsistent")
        return self


class PersistentHopCandidateRecurrencePageV1(ScannerModel):
    schema_version: Literal[1] = 1
    items: Annotated[tuple[PersistentHopCandidateRecurrenceV1, ...], Field(max_length=256)]


class PersistentHopTrackingPresentationReader(Protocol):
    def detail(self, session_id: str) -> PersistentHopTrackingDetailV1 | None: ...

    def artifact(self, session_id: str) -> bytes | None: ...

    def recurrences(self) -> PersistentHopCandidateRecurrencePageV1: ...


__all__ = [
    "PersistentHopTleCandidateV1",
    "PersistentHopCandidateRecurrencePageV1",
    "PersistentHopCandidateRecurrenceV1",
    "PersistentHopTrackingArtifactV1",
    "PersistentHopTrackingManifestV1",
    "PersistentHopTrackingDetailV1",
    "PersistentHopTrackingPresentationReader",
    "PersistentHopTrackingStatusV1",
    "PersistentHopTrajectoryTrackletV1",
    "PersistentHopUnscoredGroupV1",
    "TrackingState",
]
