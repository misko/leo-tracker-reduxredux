"""Shared scan tracking contracts, independent of capture layout and sample rate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.scanner.persistent_hop_tracking import (
    PersistentHopTleCandidateV1,
    PersistentHopTrajectoryTrackletV1,
    PersistentHopUnscoredGroupV1,
)

SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
ArtifactName = Literal["trajectory", "trajectory-tle"]


@dataclass(frozen=True)
class TrackingCandidate:
    candidate_rank: int
    integer_epoch_sample: int
    fractional_epoch_offset_samples: float
    fractional_tracking_cfo_hz: float
    fractional_exact_score: float
    fractional_control_score: float
    fractional_margin: float
    passed_fractional_margin_gate: bool


@dataclass(frozen=True)
class TrackingProbe:
    visit_index: int
    receiver_id: int
    probe_index: int
    probe_start_ms: int
    channel: int
    edge: str
    actual_rf_hz: float
    valid_start_counter: int
    payload_start_sample: int
    candidates: tuple[TrackingCandidate, ...]


@dataclass(frozen=True)
class TrackingInput:
    session_id: str
    capture_mode: Literal["fixed", "adaptive"]
    sample_rate_hz: int
    radio_id: str
    stream_generation: str
    input_manifest_sha256: str
    analysis_manifest_sha256: str
    raw_recording_authority_digest: str
    timing: PersistentHopUtcTimingAuthorityV1 | None
    qualified: bool
    probes: tuple[TrackingProbe, ...]
    probe_ms: int = 20


class TrackingArtifactV1(ContractModel):
    name: ArtifactName
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class CatalogueExclusionV1(ContractModel):
    catalog_number: int
    name: str
    reason: Literal["catalogue-labelled-debris"] = "catalogue-labelled-debris"


class ScannerTrackingProductV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-shared-tracking-v1"] = "scanner-shared-tracking-v1"
    session_id: SessionId
    capture_mode: Literal["fixed", "adaptive"]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    input_manifest_sha256: Sha256Digest
    analysis_manifest_sha256: Sha256Digest
    configuration_digest: Sha256Digest
    tle_match_config_digest: Sha256Digest | None = None
    created_at: datetime
    trajectory_state: Literal["complete", "no-trajectory", "unsupported"]
    tle_state: Literal["pending", "complete", "partial", "unavailable", "no-eligible-groups"]
    reasons: tuple[str, ...] = ()
    projected_candidate_count: Annotated[int, Field(ge=0)] = 0
    physical_group_count: Annotated[int, Field(ge=0)] = 0
    eligible_group_count: Annotated[int, Field(ge=0)] = 0
    attempted_group_count: Annotated[int, Field(ge=0)] = 0
    deferred_group_count: Annotated[int, Field(ge=0)] = 0
    group_limit: Annotated[int, Field(ge=1, le=32)] = 4
    tracklets: tuple[PersistentHopTrajectoryTrackletV1, ...] = ()
    tle_candidates: tuple[PersistentHopTleCandidateV1, ...] = ()
    unscored_groups: tuple[PersistentHopUnscoredGroupV1, ...] = ()
    observer_site: ObserverSiteV1
    original_tle_snapshot: TleSnapshotRefV1 | None = None
    eligible_tle_snapshot: TleSnapshotRefV1 | None = None
    catalogue_policy: Literal["exclude-labelled-starlink-debris-before-response-v1"] = (
        "exclude-labelled-starlink-debris-before-response-v1"
    )
    catalogue_exclusions: tuple[CatalogueExclusionV1, ...] = ()
    artifacts: tuple[TrackingArtifactV1, ...] = ()
    candidate_only: Literal[True] = True
    identity_claimed: Literal[False] = False

    @model_validator(mode="after")
    def _accounting(self) -> Self:
        if (
            not 0
            <= self.attempted_group_count
            <= self.eligible_group_count
            <= self.physical_group_count
        ):
            raise ValueError("tracking group accounting differs")
        if self.attempted_group_count > self.group_limit:
            raise ValueError("tracking exceeds group budget")
        if self.deferred_group_count != self.eligible_group_count - self.attempted_group_count:
            raise ValueError("tracking deferred group accounting differs")
        if self.attempted_group_count != len(self.tle_candidates) + len(self.unscored_groups):
            raise ValueError("tracking attempted dispositions differ")
        if self.tle_candidates and self.eligible_tle_snapshot is None:
            raise ValueError("TLE comparisons lack catalogue authority")
        names = [a.name for a in self.artifacts]
        if len(set(names)) != len(names):
            raise ValueError("tracking artifact names are duplicated")
        if self.trajectory_state == "complete" and "trajectory" not in names:
            raise ValueError("complete trajectories lack their independent PNG")
        if self.tle_candidates and self.tle_match_config_digest is None:
            raise ValueError("TLE comparisons lack matching policy authority")
        if (self.original_tle_snapshot is None) != (self.eligible_tle_snapshot is None):
            raise ValueError("eligible catalogue lacks original snapshot provenance")
        if self.original_tle_snapshot is not None and self.eligible_tle_snapshot is not None:
            original, eligible = self.original_tle_snapshot, self.eligible_tle_snapshot
            if (
                original.provider != eligible.provider
                or original.collected_utc_ns != eligible.collected_utc_ns
                or original.object_count - eligible.object_count != len(self.catalogue_exclusions)
            ):
                raise ValueError("catalogue exclusion inventory does not close")
        return self


class ScannerTrackingStatusV1(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV1 | None = None


class ScannerTrackingReader(Protocol):
    def status(self, session_id: str) -> ScannerTrackingStatusV1: ...
    def artifact(self, session_id: str, name: ArtifactName) -> bytes | None: ...


class ScannerTrackingInputs(Protocol):
    def load(self, session_id: str) -> TrackingInput: ...
