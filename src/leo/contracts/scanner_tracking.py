"""Shared scan tracking contracts, independent of capture layout and sample rate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_position import SparseScanPositionDiagnosticV1
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.scanner.persistent_hop_tracking import (
    PersistentHopTleCandidateV1,
    PersistentHopTrajectoryTrackletV1,
    PersistentHopUnscoredGroupV1,
)

SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
ArtifactName = Literal[
    "trajectory",
    "trajectory-tle",
    "tle-review-01",
    "tle-review-02",
    "tle-review-03",
    "tle-review-04",
    "tle-review-05",
    "tle-review-06",
    "tle-review-07",
    "tle-review-08",
    "tle-review-09",
    "tle-review-10",
    "tle-review-11",
    "tle-review-12",
    "tle-review-13",
    "tle-review-14",
    "tle-review-15",
    "tle-review-16",
    "tle-review-17",
    "tle-review-18",
    "tle-review-19",
    "tle-review-20",
    "tle-review-21",
    "tle-review-22",
    "tle-review-23",
    "tle-review-24",
    "tle-review-25",
    "tle-review-26",
    "tle-review-27",
    "tle-review-28",
    "tle-review-29",
    "tle-review-30",
    "tle-review-31",
    "tle-review-32",
]
ArtifactNameV12 = ArtifactName | Literal["position-diagnostic"]


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
    capture_start_utc_ns: int | None = None
    capture_end_utc_ns: int | None = None


class TrackingArtifactV1(ContractModel):
    name: ArtifactName
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class TrackingArtifactV12(ContractModel):
    name: ArtifactNameV12
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=64 * 1024 * 1024)]


class CatalogueExclusionV1(ContractModel):
    catalog_number: int
    name: str
    reason: Literal["catalogue-labelled-debris"] = "catalogue-labelled-debris"


class CataloguePropagationExclusionV1(ContractModel):
    catalog_number: Annotated[int, Field(gt=0)]
    name: str
    selected_element_digest: Sha256Digest
    error_codes: tuple[Annotated[int, Field(gt=0)], ...]
    screened_utc_ns: tuple[Annotated[int, Field(gt=0)], ...]
    reason: Literal["sgp4-propagation-error"] = "sgp4-propagation-error"

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if not self.name.strip() or not self.error_codes or not self.screened_utc_ns:
            raise ValueError("propagation exclusion evidence is incomplete")
        if tuple(sorted(set(self.error_codes))) != self.error_codes:
            raise ValueError("propagation exclusion codes are not canonical")
        if tuple(sorted(set(self.screened_utc_ns))) != self.screened_utc_ns:
            raise ValueError("propagation exclusion times are not canonical")
        return self


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
                or original.object_count - eligible.object_count
                != len(self.catalogue_exclusions) + len(getattr(self, "propagation_exclusions", ()))
            ):
                raise ValueError("catalogue exclusion inventory does not close")
        return self


class ScannerTrackingProductV2(ScannerTrackingProductV1):
    schema_version: Literal[2] = 2  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v2"] = "scanner-shared-tracking-v2"  # type: ignore[assignment]
    trajectory_time_basis: Literal["qualified-utc", "device-counter-relative"]

    @model_validator(mode="after")
    def _time_basis(self) -> Self:
        if self.trajectory_time_basis == "device-counter-relative" and (
            self.tle_state not in ("pending", "unavailable")
            or self.tle_candidates
            or self.original_tle_snapshot is not None
        ):
            raise ValueError("device-relative trajectories cannot claim catalogue authority")
        return self


class ScannerTrackingProductV3(ScannerTrackingProductV2):
    schema_version: Literal[3] = 3  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v3"] = "scanner-shared-tracking-v3"  # type: ignore[assignment]


class ScannerTrackingProductV4(ScannerTrackingProductV3):
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v4"] = "scanner-shared-tracking-v4"  # type: ignore[assignment]


class ScannerTrackingProductV5(ScannerTrackingProductV4):
    """Four-second trajectory-continuity policy, separate from V4 evidence."""

    schema_version: Literal[5] = 5  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v5"] = "scanner-shared-tracking-v5"  # type: ignore[assignment]


class ScannerTrackingProductV6(ScannerTrackingProductV5):
    """All reconstructed tracklets are rendered in the independent PNG evidence."""

    schema_version: Literal[6] = 6  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v6"] = "scanner-shared-tracking-v6"  # type: ignore[assignment]


class ScannerTrackingProductV7(ScannerTrackingProductV6):
    """Four-second Hough tracks with 14-observation/seven-second TLE eligibility."""

    schema_version: Literal[7] = 7  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v7"] = "scanner-shared-tracking-v7"  # type: ignore[assignment]


class ScannerTrackingProductV8(ScannerTrackingProductV7):
    """Response-blind SGP4 failures are excluded with persisted evidence."""

    schema_version: Literal[8] = 8  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v8"] = "scanner-shared-tracking-v8"  # type: ignore[assignment]
    catalogue_policy: Literal["exclude-labelled-debris-and-sgp4-failures-before-response-v1"] = (
        "exclude-labelled-debris-and-sgp4-failures-before-response-v1"  # type: ignore[assignment]
    )
    propagation_exclusions: tuple[CataloguePropagationExclusionV1, ...] = ()


class ScannerTrackingProductV9(ScannerTrackingProductV8):
    schema_version: Literal[9] = 9  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v9"] = "scanner-shared-tracking-v9"  # type: ignore[assignment]
    tle_residual_partition_policy: Literal["deterministic-randomized-observation-v1"] = (
        "deterministic-randomized-observation-v1"
    )


class ScannerTleReviewCandidateV1(ContractModel):
    rank: Annotated[int, Field(ge=1, le=5)]
    catalog_number: Annotated[int, Field(gt=0)]
    selected_tau_s: float
    fitted_offset_hz: float
    fit_rms_hz: Annotated[float, Field(ge=0)]
    randomized_evaluation_rms_hz: Annotated[float, Field(ge=0)]


class ScannerTleTrackReviewV1(ContractModel):
    tracklet_id: Sha256Digest
    channel: Annotated[int, Field(ge=1, le=4)]
    edge: Literal["lower", "upper"]
    start_s: float
    end_s: float
    observation_count: Annotated[int, Field(ge=14)]
    fit_observation_count: Annotated[int, Field(ge=2)]
    randomized_evaluation_observation_count: Annotated[int, Field(ge=1)]
    artifact_name: ArtifactName
    candidates: tuple[ScannerTleReviewCandidateV1, ...]

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        if (
            self.end_s <= self.start_s
            or self.fit_observation_count + self.randomized_evaluation_observation_count
            != self.observation_count
            or not 1 <= len(self.candidates) <= 5
            or self.artifact_name in ("trajectory", "trajectory-tle")
        ):
            raise ValueError("TLE track review evidence is incoherent")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("TLE track review ranks are not canonical")
        return self


class ScannerTrackingProductV10(ScannerTrackingProductV9):
    """Randomized evaluation with material control margins and per-track reviews."""

    schema_version: Literal[10] = 10  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v10"] = "scanner-shared-tracking-v10"  # type: ignore[assignment]
    control_comparison_policy: Literal["minimum-0.01-nll-per-evaluation-observation-v1"] = (
        "minimum-0.01-nll-per-evaluation-observation-v1"
    )
    track_reviews: tuple[ScannerTleTrackReviewV1, ...] = ()

    @model_validator(mode="after")
    def _track_review_artifacts(self) -> Self:
        artifact_names = {item.name for item in self.artifacts}
        review_names = tuple(item.artifact_name for item in self.track_reviews)
        if len(set(review_names)) != len(review_names) or any(
            name not in artifact_names for name in review_names
        ):
            raise ValueError("TLE track review artifacts are incomplete")
        return self


class ScannerTrackingProductV11(ScannerTrackingProductV10):
    """Nominal catalogue gates; polynomial and wrong-time comparisons are diagnostics."""

    schema_version: Literal[11] = 11  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v11"] = "scanner-shared-tracking-v11"  # type: ignore[assignment]
    control_comparison_policy: Literal["polynomial-and-wrong-time-diagnostic-only-v1"] = (  # type: ignore[assignment]
        "polynomial-and-wrong-time-diagnostic-only-v1"
    )


class ScannerTrackingProductV12(ScannerTrackingProductV11):
    """Shared tracking plus a bounded site-assisted positioning diagnostic."""

    schema_version: Literal[12] = 12  # type: ignore[assignment]
    analysis_id: Literal["scanner-shared-tracking-v12"] = "scanner-shared-tracking-v12"  # type: ignore[assignment]
    artifacts: tuple[TrackingArtifactV12, ...] = ()  # type: ignore[assignment]
    position_diagnostic: SparseScanPositionDiagnosticV1 | None = None

    @model_validator(mode="after")
    def _position_artifact(self) -> Self:
        names = {artifact.name for artifact in self.artifacts}
        if self.position_diagnostic is not None and "position-diagnostic" not in names:
            raise ValueError("position diagnostic lacks its independent PNG")
        return self


class ScannerTrackingStatusV1(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV1 | None = None


class ScannerTrackingStatusV2(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV2 | None = None


class ScannerTrackingStatusV3(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV3 | None = None


class ScannerTrackingStatusV4(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV4 | None = None


class ScannerTrackingStatusV5(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV5 | None = None


class ScannerTrackingStatusV6(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV6 | None = None


class ScannerTrackingStatusV7(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV7 | None = None


class ScannerTrackingStatusV8(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV8 | None = None


class ScannerTrackingStatusV9(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV9 | None = None


class ScannerTrackingStatusV10(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV10 | None = None


class ScannerTrackingStatusV11(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV11 | None = None


class ScannerTrackingStatusV12(ContractModel):
    session_id: SessionId
    state: Literal["pending", "running", "complete", "failed"] = "pending"
    phase: str = "waiting-for-analysis"
    failure_summary: str | None = None
    product: ScannerTrackingProductV12 | None = None

    @model_validator(mode="after")
    def _terminal_product(self) -> Self:
        if self.state == "complete" and (
            self.product is None or self.product.position_diagnostic is None
        ):
            raise ValueError("complete V12 tracking status requires a position diagnostic product")
        return self


class ScannerTrackingReader(Protocol):
    def status(
        self, session_id: str
    ) -> (
        ScannerTrackingStatusV1
        | ScannerTrackingStatusV2
        | ScannerTrackingStatusV3
        | ScannerTrackingStatusV4
        | ScannerTrackingStatusV5
        | ScannerTrackingStatusV6
        | ScannerTrackingStatusV7
        | ScannerTrackingStatusV8
        | ScannerTrackingStatusV9
        | ScannerTrackingStatusV10
        | ScannerTrackingStatusV11
        | ScannerTrackingStatusV12
    ): ...
    def artifact(self, session_id: str, name: ArtifactNameV12) -> bytes | None: ...


class ScannerTrackingInputs(Protocol):
    def load(self, session_id: str) -> TrackingInput: ...
