"""Offline acceptance of independent and synchronized single-RX capture modes."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

import numpy as np
from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileRevisionV2
from leo.contracts.recording import RecordingManifestV3, RecordingStreamV1
from leo.contracts.states import (
    CaptureState,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
)
from leo.pipeline.contracts import IqReader
from leo.storage import PathConfinementError, RecordingStore, parse_recording_bundle_uri

CaptureModeRole = Literal["independent_radio_a", "independent_radio_b", "synchronized_pair"]
_HARDWARE_PROFILE_NAME = "starlink-ch4-lower-2p5m-60s-rx1-centered-v1"
_HARDWARE_PROFILE_REVISION_DIGEST = (
    "sha256:0f6aa753e16feaba1f76df21f0b620f32ab0b72456cb6034f2b1ea6a60c11e1a"
)
_HARDWARE_IF_HZ = 1_709_521_250
_HARDWARE_RF_HZ = 11_459_521_250
_HARDWARE_SAMPLE_RATE_HZ = 2_500_000
_HARDWARE_BANDWIDTH_HZ = 2_500_000
_HARDWARE_SAMPLE_COUNT = 150_000_000
_HARDWARE_RECEIVER_ID = 1
_HARDWARE_GAIN_DB = 40.0
_HARDWARE_MINIMUM_OVERLAP = 0.99
_HARDWARE_CLIPPING_ABS_THRESHOLD = 2_047
_HARDWARE_CLIPPING_SEMANTICS = "ad9361_signed_12bit_native_ci16_abs_ge_2047"
_HARDWARE_CLIPPING_PROVENANCE = (
    "pluto-plus-utils@d5cd29301c5b36b3d65f8433af1508f2650eadea:"
    "docs/ANALYSIS_PROVENANCE.md,src/pluto_plus/analysis.py"
)
_HARDWARE_RADIO_IDS = ("radio_pluto_5d4d", "radio_pluto_19f2")
_HARDWARE_RADIO_SERIALS = (
    "1040005e0b100007100010000bf33a5d4d",
    "10400056f695001322002d0010ad1719f2",
)
_HARDWARE_RADIO_URIS = ("ip:192.168.1.20", "ip:192.168.1.21")
_HARDWARE_RECEIVER_CHAINS = ("rx_lnb_b", "rx_lnb_d")
_HARDWARE_EPOCH_IDS = (
    "hw_gauss_r20_science_postreboot_20260816_v1",
    "hw_gauss_r21_science_postreboot_20260816_v1",
)
_HARDWARE_STATION_TOPOLOGY_DIGESTS = (
    "sha256:eff9673575738b3bd72246d02252e41b5d1d548ae775e9eb453e1ee3a8290bfa",
    "sha256:eb69aef0b2211b3073d125da66f29ec2154e06a4a52916c2d0a036e8f17efef7",
)
_OVERLAP_ROUNDING_TOLERANCE_NS = 1
SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class CaptureModeExpectationV1(ContractModel):
    """Exact geometry shared by the three hardware-acceptance sessions."""

    schema_version: Literal[1] = 1
    profile_name: str
    profile_revision_digest: Sha256Digest
    radio_ids: tuple[SafeIdentifier, SafeIdentifier]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    center_frequency_hz: Annotated[int, Field(gt=0)]
    rf_center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    gain_db: Annotated[float, Field(ge=40.0, le=40.0)]
    sample_count: Annotated[int, Field(gt=0)]
    starlink_channel: Literal["ch4"]
    starlink_edge: Literal["lower"]
    requested_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )
    minimum_pair_overlap_fraction: Annotated[float, Field(ge=0.0, le=1.0)] = 0.99
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)] = 32_767
    clipping_semantics: Literal[
        "generic_ci16",
        "ad9361_signed_12bit_native_ci16_abs_ge_2047",
    ] = "generic_ci16"
    clipping_provenance: str | None = None
    maximum_clipped_sample_fraction: Annotated[float, Field(ge=0.0, le=0.0)] = 0.0
    maximum_gap_count: Literal[0] = 0
    maximum_missing_sample_count: Literal[0] = 0
    maximum_overflow_count: Literal[0] = 0
    maximum_constant_iq_stream_count: Literal[0] = 0
    source_type: SourceType = SourceType.LIVE
    hardware_epoch_ids: tuple[SafeIdentifier, SafeIdentifier] | None = None
    station_topology_evidence_digests: tuple[Sha256Digest, Sha256Digest] | None = None

    @field_validator("radio_ids")
    @classmethod
    def _radio_ids_are_distinct(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2:
            raise ValueError("capture-mode acceptance requires two distinct radios")
        return value

    @classmethod
    def from_profile_revision(
        cls,
        revision: CaptureProfileRevisionV1 | CaptureProfileRevisionV2,
        radio_ids: tuple[str, str],
        *,
        source_type: SourceType = SourceType.LIVE,
        minimum_pair_overlap_fraction: float = 0.99,
    ) -> Self:
        profile = revision.profile
        if profile.duration_seconds is None or profile.sample_count is not None:
            raise ValueError("capture-mode acceptance profile requires a duration")
        if profile.rf_center_frequency_hz is None:
            raise ValueError("capture-mode acceptance profile requires an RF center")
        if (
            profile.starlink_channel != "ch4"
            or profile.starlink_edge is None
            or profile.starlink_edge.value != "lower"
        ):
            raise ValueError("capture-mode acceptance profile must target CH4 lower")
        if len(profile.receivers) != 1:
            raise ValueError("capture-mode acceptance profile must select exactly one RX")
        if profile.gain_mode is not GainMode.MANUAL or len(profile.gains) != 1:
            raise ValueError("capture-mode acceptance profile requires one manual RX gain")
        gain = profile.gains[0]
        if gain.receiver_id != profile.receivers[0]:
            raise ValueError("capture-mode acceptance gain does not match its RX")
        if gain.gain_db != 40.0:
            raise ValueError("capture-mode acceptance profile requires frozen 40 dB gain")
        sample_count = int(profile.duration_seconds * profile.sample_rate_hz)
        return cls(
            profile_name=profile.name,
            profile_revision_digest=revision.revision_digest,
            radio_ids=radio_ids,
            receiver_id=profile.receivers[0],
            center_frequency_hz=profile.center_frequency_hz,
            rf_center_frequency_hz=profile.rf_center_frequency_hz,
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            gain_db=gain.gain_db,
            sample_count=sample_count,
            starlink_channel="ch4",
            starlink_edge="lower",
            minimum_pair_overlap_fraction=minimum_pair_overlap_fraction,
            source_type=source_type,
        )

    @classmethod
    def from_hardware_profile_revision(
        cls,
        revision: CaptureProfileRevisionV1 | CaptureProfileRevisionV2,
        radio_ids: tuple[str, str],
    ) -> Self:
        if revision.profile.duration_seconds != 60 or revision.profile.sample_count is not None:
            raise ValueError("hardware capture-mode campaign requires an exact 60 second dwell")
        expectation = cls.from_profile_revision(
            revision,
            radio_ids,
            source_type=SourceType.LIVE,
            minimum_pair_overlap_fraction=_HARDWARE_MINIMUM_OVERLAP,
        )
        expectation = expectation.model_copy(
            update={
                "clipping_abs_threshold": _HARDWARE_CLIPPING_ABS_THRESHOLD,
                "clipping_semantics": _HARDWARE_CLIPPING_SEMANTICS,
                "clipping_provenance": _HARDWARE_CLIPPING_PROVENANCE,
                "hardware_epoch_ids": _HARDWARE_EPOCH_IDS,
                "station_topology_evidence_digests": _HARDWARE_STATION_TOPOLOGY_DIGESTS,
            }
        )
        _require_hardware_expectation(expectation)
        return expectation


class CaptureModeStreamTimingEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    stream_id: SafeIdentifier
    radio_id: SafeIdentifier
    sample_count: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    first_estimate_utc_ns: Annotated[int, Field(ge=0)]
    first_earliest_utc_ns: Annotated[int, Field(ge=0)]
    first_latest_utc_ns: Annotated[int, Field(ge=0)]
    first_uncertainty_ns: Annotated[int, Field(ge=0)]
    last_estimate_utc_ns: Annotated[int, Field(ge=0)]
    last_earliest_utc_ns: Annotated[int, Field(ge=0)]
    last_latest_utc_ns: Annotated[int, Field(ge=0)]
    last_uncertainty_ns: Annotated[int, Field(ge=0)]
    sample_interval_end_estimate_utc_ns: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _timing_is_explicit_and_consistent(self) -> Self:
        if not self.first_earliest_utc_ns <= self.first_estimate_utc_ns <= self.first_latest_utc_ns:
            raise ValueError("first-sample timing estimate lies outside its uncertainty interval")
        if not self.last_earliest_utc_ns <= self.last_estimate_utc_ns <= self.last_latest_utc_ns:
            raise ValueError("last-sample timing estimate lies outside its uncertainty interval")
        if self.first_uncertainty_ns != self.first_latest_utc_ns - self.first_earliest_utc_ns:
            raise ValueError("first-sample uncertainty width is inconsistent")
        if self.last_uncertainty_ns != self.last_latest_utc_ns - self.last_earliest_utc_ns:
            raise ValueError("last-sample uncertainty width is inconsistent")
        if self.last_estimate_utc_ns < self.first_estimate_utc_ns:
            raise ValueError("stream timing interval regresses")
        if self.sample_interval_end_estimate_utc_ns <= self.last_estimate_utc_ns:
            raise ValueError("sample interval end must follow the last-sample estimate")
        expected_last = (
            self.first_estimate_utc_ns
            + (self.sample_count - 1) * 1_000_000_000 // self.sample_rate_hz
        )
        expected_interval_end = (
            self.first_estimate_utc_ns + self.sample_count * 1_000_000_000 // self.sample_rate_hz
        )
        if self.last_estimate_utc_ns != expected_last:
            raise ValueError("last-sample estimate disagrees with exact sample-clock geometry")
        if self.sample_interval_end_estimate_utc_ns != expected_interval_end:
            raise ValueError("sample interval end disagrees with exact half-open duration N/Fs")
        return self


class CaptureModeSessionCheckV1(ContractModel):
    schema_version: Literal[1] = 1
    role: CaptureModeRole
    session_id: SafeIdentifier
    expected_radio_ids: tuple[SafeIdentifier, ...]
    bundle_uri: str | None = None
    manifest_session_id: SafeIdentifier | None = None
    manifest_sha256: Sha256Digest | None = None
    digest_valid: bool = False
    observed_radio_ids: tuple[str, ...] = ()
    observed_radio_serials: tuple[str, ...] = ()
    observed_radio_uris: tuple[str, ...] = ()
    declared_receiver_chain_ids: tuple[str, ...] = ()
    declared_hardware_epoch_ids: tuple[str, ...] = ()
    declared_station_topology_evidence_digests: tuple[Sha256Digest, ...] = ()
    observed_receiver_ids: tuple[tuple[int, ...], ...] = ()
    observed_sample_counts: tuple[int, ...] = ()
    observed_gain_db: tuple[float, ...] = ()
    observed_gap_counts: tuple[int, ...] = ()
    observed_missing_sample_counts: tuple[int, ...] = ()
    observed_overflow_counts: tuple[int, ...] = ()
    observed_clipped_sample_counts: tuple[int, ...] = ()
    observed_clipped_sample_fractions: tuple[Annotated[float, Field(ge=0.0, le=1.0)], ...] = ()
    observed_constant_iq: tuple[bool, ...] = ()
    stream_timing: tuple[CaptureModeStreamTimingEvidenceV1, ...] = ()
    synchronization_grade: SynchronizationGrade | None = None
    manifest_overlap_fraction: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    overlap_fraction: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    estimated_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    guaranteed_overlap_ns: Annotated[int | None, Field(ge=0)] = None
    guaranteed_overlap_fraction: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    estimated_start_skew_ns: Annotated[int | None, Field(ge=0)] = None
    start_skew_uncertainty_ns: Annotated[int | None, Field(ge=0)] = None
    overlap_rounding_tolerance_ns: Literal[1] | None = None
    passed: bool = False
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _passed_has_no_errors(self) -> Self:
        if self.passed != (self.digest_valid and not self.errors):
            raise ValueError("capture-mode check pass state disagrees with evidence")
        if not self.passed:
            return self
        if self.bundle_uri is None or self.manifest_sha256 is None:
            raise ValueError("passing capture-mode check requires bundle identity and digest")
        try:
            uri_session_id = parse_recording_bundle_uri(self.bundle_uri)
        except (TypeError, ValueError, PathConfinementError) as error:
            raise ValueError("passing capture-mode bundle URI is not canonical") from error
        if uri_session_id != self.session_id:
            raise ValueError("passing capture-mode bundle URI is not bound to its session")
        if self.manifest_session_id != self.session_id:
            raise ValueError("passing capture-mode manifest is not bound to its session")
        count = len(self.expected_radio_ids)
        required_cardinalities = (
            len(self.observed_radio_ids),
            len(self.observed_radio_serials),
            len(self.observed_radio_uris),
            len(self.declared_receiver_chain_ids),
            len(self.declared_hardware_epoch_ids),
            len(self.declared_station_topology_evidence_digests),
            len(self.observed_receiver_ids),
            len(self.observed_sample_counts),
            len(self.observed_gain_db),
            len(self.observed_gap_counts),
            len(self.observed_missing_sample_counts),
            len(self.observed_overflow_counts),
            len(self.observed_clipped_sample_counts),
            len(self.observed_clipped_sample_fractions),
            len(self.observed_constant_iq),
            len(self.stream_timing),
        )
        if count not in (1, 2) or any(observed != count for observed in required_cardinalities):
            raise ValueError("passing capture-mode check has incomplete stream evidence")
        if self.observed_radio_ids != self.expected_radio_ids:
            raise ValueError("passing capture-mode check observed unexpected radio IDs")
        if any(not value for value in self.observed_radio_serials + self.observed_radio_uris):
            raise ValueError("passing capture-mode check requires radio identity evidence")
        if any(not value for value in self.declared_receiver_chain_ids):
            raise ValueError("passing capture-mode check requires declared receiver topology")
        if any(not value for value in self.declared_hardware_epoch_ids):
            raise ValueError("passing capture-mode check requires declared hardware epochs")
        if any(receiver_ids != (1,) for receiver_ids in self.observed_receiver_ids):
            raise ValueError("passing capture-mode check requires physical RX1")
        if any(value <= 0 for value in self.observed_sample_counts):
            raise ValueError("passing capture-mode check requires observed samples")
        if any(value != 40.0 for value in self.observed_gain_db):
            raise ValueError("passing capture-mode check requires frozen gain evidence")
        if any(
            self.observed_gap_counts
            + self.observed_missing_sample_counts
            + self.observed_overflow_counts
        ):
            raise ValueError("passing capture-mode check cannot contain continuity loss")
        if any(self.observed_clipped_sample_counts) or any(self.observed_clipped_sample_fractions):
            raise ValueError("passing capture-mode check cannot contain clipped IQ")
        if any(self.observed_constant_iq):
            raise ValueError("passing capture-mode check cannot contain constant IQ")
        pair_fields = (
            self.manifest_overlap_fraction,
            self.overlap_fraction,
            self.estimated_overlap_ns,
            self.guaranteed_overlap_ns,
            self.guaranteed_overlap_fraction,
            self.estimated_start_skew_ns,
            self.start_skew_uncertainty_ns,
            self.overlap_rounding_tolerance_ns,
        )
        if self.role == "synchronized_pair":
            if self.synchronization_grade not in {
                SynchronizationGrade.BEST_EFFORT_OBSERVED,
                SynchronizationGrade.DEGRADED,
            }:
                raise ValueError("passing synchronized check has no synchronization grade")
            if any(value is None for value in pair_fields):
                raise ValueError("passing synchronized check requires recomputed timing evidence")
            recomputed = _recompute_pair_timing((self.stream_timing[0], self.stream_timing[1]))
            observed_recomputed = (
                self.estimated_overlap_ns,
                self.overlap_fraction,
                self.guaranteed_overlap_ns,
                self.guaranteed_overlap_fraction,
                self.estimated_start_skew_ns,
                self.start_skew_uncertainty_ns,
            )
            if observed_recomputed != recomputed:
                raise ValueError("passing synchronized check overlap is not timing-derived")
            denominator_ns = min(
                timing.sample_count * 1_000_000_000 // timing.sample_rate_hz
                for timing in self.stream_timing
            )
            tolerance = _OVERLAP_ROUNDING_TOLERANCE_NS / denominator_ns
            if (
                self.overlap_rounding_tolerance_ns != _OVERLAP_ROUNDING_TOLERANCE_NS
                or self.manifest_overlap_fraction is None
                or self.overlap_fraction is None
                or abs(self.manifest_overlap_fraction - self.overlap_fraction) > tolerance
            ):
                raise ValueError(
                    "manifest overlap differs from sample-clock overlap beyond one-nanosecond "
                    "fractional rounding tolerance"
                )
        else:
            if self.synchronization_grade is not SynchronizationGrade.NOT_REQUESTED:
                raise ValueError("passing independent check has an invalid synchronization grade")
            if any(value is not None for value in pair_fields):
                raise ValueError("passing independent check cannot claim overlap evidence")
        return self


class CaptureModeAcceptanceReceiptV1(ContractModel):
    kind: Literal["single_rx_capture_mode_acceptance"] = "single_rx_capture_mode_acceptance"
    schema_version: Literal[1] = 1
    acceptance_id: SafeIdentifier
    observed_utc_ns: Annotated[int, Field(ge=0)]
    expectation: CaptureModeExpectationV1
    checks: tuple[CaptureModeSessionCheckV1, CaptureModeSessionCheckV1, CaptureModeSessionCheckV1]
    accepted: bool
    acceptance_scope: Literal["capture_only"] = "capture_only"
    processing_evidence_evaluated: Literal[False] = False
    scientific_acceptance_claimed: Literal[False] = False
    required_follow_up: Literal["linked_standard_processing_and_detection_receipt"] = (
        "linked_standard_processing_and_detection_receipt"
    )

    @model_validator(mode="after")
    def _receipt_is_complete(self) -> Self:
        expected_roles: tuple[CaptureModeRole, ...] = (
            "independent_radio_a",
            "independent_radio_b",
            "synchronized_pair",
        )
        if tuple(check.role for check in self.checks) != expected_roles:
            raise ValueError("capture-mode receipt requires the three canonical roles")
        expected_radio_ids = (
            (self.expectation.radio_ids[0],),
            (self.expectation.radio_ids[1],),
            self.expectation.radio_ids,
        )
        for check, expected in zip(self.checks, expected_radio_ids, strict=True):
            if check.expected_radio_ids != expected:
                raise ValueError("capture-mode check radio role disagrees with expectation")
            if check.passed and any(
                sample_count != self.expectation.sample_count
                for sample_count in check.observed_sample_counts
            ):
                raise ValueError(
                    "passing capture-mode check sample counts disagree with expectation"
                )
            if check.passed and any(
                timing.radio_id != radio_id
                for timing, radio_id in zip(
                    check.stream_timing, check.expected_radio_ids, strict=True
                )
            ):
                raise ValueError("passing capture-mode timing identities disagree with expectation")
            if check.passed and any(
                timing.sample_count != self.expectation.sample_count
                or timing.sample_rate_hz != self.expectation.sample_rate_hz
                for timing in check.stream_timing
            ):
                raise ValueError("passing capture-mode timing geometry disagrees with expectation")
            indexes = tuple(self.expectation.radio_ids.index(radio_id) for radio_id in expected)
            if check.passed and self.expectation.hardware_epoch_ids is not None:
                expected_epochs = tuple(
                    self.expectation.hardware_epoch_ids[index] for index in indexes
                )
                if check.declared_hardware_epoch_ids != expected_epochs:
                    raise ValueError("passing capture-mode hardware epoch differs from expectation")
            if check.passed and self.expectation.station_topology_evidence_digests is not None:
                expected_digests = tuple(
                    self.expectation.station_topology_evidence_digests[index] for index in indexes
                )
                if check.declared_station_topology_evidence_digests != expected_digests:
                    raise ValueError(
                        "passing capture-mode topology evidence differs from expectation"
                    )
        pair = self.checks[2]
        if (
            pair.passed
            and pair.overlap_fraction is not None
            and pair.overlap_fraction < self.expectation.minimum_pair_overlap_fraction
        ):
            raise ValueError("passing synchronized check is below the overlap threshold")
        session_ids = tuple(check.session_id for check in self.checks)
        if len(set(session_ids)) != 3:
            raise ValueError("capture-mode receipt requires three distinct sessions")
        if self.accepted != all(check.passed for check in self.checks):
            raise ValueError("capture-mode receipt acceptance disagrees with checks")
        return self


class CaptureModeCampaignAcceptanceReceiptV2(ContractModel):
    """Ten trials in each canonical capture stratum (30 distinct sessions)."""

    kind: Literal["single_rx_capture_mode_campaign_acceptance"] = (
        "single_rx_capture_mode_campaign_acceptance"
    )
    schema_version: Literal[2] = 2
    acceptance_id: SafeIdentifier
    observed_utc_ns: Annotated[int, Field(ge=0)]
    expectation: CaptureModeExpectationV1
    trial_receipts: tuple[CaptureModeAcceptanceReceiptV1, ...]
    accepted: bool
    acceptance_scope: Literal["capture_only"] = "capture_only"
    processing_evidence_evaluated: Literal[False] = False
    scientific_acceptance_claimed: Literal[False] = False
    required_follow_up: Literal["linked_standard_processing_and_detection_receipt"] = (
        "linked_standard_processing_and_detection_receipt"
    )

    @model_validator(mode="after")
    def _campaign_is_complete(self) -> Self:
        _require_hardware_expectation(self.expectation)
        if len(self.trial_receipts) != 10:
            raise ValueError("capture-mode campaign requires exactly 10 trials per stratum")
        if any(receipt.expectation != self.expectation for receipt in self.trial_receipts):
            raise ValueError("capture-mode campaign trial expectations differ")
        expected_serials = (
            (_HARDWARE_RADIO_SERIALS[0],),
            (_HARDWARE_RADIO_SERIALS[1],),
            _HARDWARE_RADIO_SERIALS,
        )
        expected_uris = (
            (_HARDWARE_RADIO_URIS[0],),
            (_HARDWARE_RADIO_URIS[1],),
            _HARDWARE_RADIO_URIS,
        )
        expected_chains = (
            (_HARDWARE_RECEIVER_CHAINS[0],),
            (_HARDWARE_RECEIVER_CHAINS[1],),
            _HARDWARE_RECEIVER_CHAINS,
        )
        expected_epochs = (
            (_HARDWARE_EPOCH_IDS[0],),
            (_HARDWARE_EPOCH_IDS[1],),
            _HARDWARE_EPOCH_IDS,
        )
        expected_topology_digests = (
            (_HARDWARE_STATION_TOPOLOGY_DIGESTS[0],),
            (_HARDWARE_STATION_TOPOLOGY_DIGESTS[1],),
            _HARDWARE_STATION_TOPOLOGY_DIGESTS,
        )
        for receipt in self.trial_receipts:
            for index, check in enumerate(receipt.checks):
                if check.passed and (
                    check.observed_radio_serials != expected_serials[index]
                    or check.observed_radio_uris != expected_uris[index]
                    or check.declared_receiver_chain_ids != expected_chains[index]
                    or check.declared_hardware_epoch_ids != expected_epochs[index]
                    or check.declared_station_topology_evidence_digests
                    != expected_topology_digests[index]
                ):
                    raise ValueError("passing campaign check has unqualified hardware identity")
        session_ids = tuple(
            check.session_id for receipt in self.trial_receipts for check in receipt.checks
        )
        if len(session_ids) != 30 or len(set(session_ids)) != 30:
            raise ValueError("capture-mode campaign requires 30 distinct sessions")
        if self.accepted:
            manifest_digests = tuple(
                check.manifest_sha256 for receipt in self.trial_receipts for check in receipt.checks
            )
            bundle_uris = tuple(
                check.bundle_uri for receipt in self.trial_receipts for check in receipt.checks
            )
            if None in manifest_digests or len(set(manifest_digests)) != 30:
                raise ValueError("accepted campaign requires 30 unique manifest digests")
            if None in bundle_uris or len(set(bundle_uris)) != 30:
                raise ValueError("accepted campaign requires 30 unique bundle URIs")
        trial_ids = tuple(receipt.acceptance_id for receipt in self.trial_receipts)
        if len(set(trial_ids)) != 10:
            raise ValueError("capture-mode campaign trial IDs must be distinct")
        if self.accepted != all(receipt.accepted for receipt in self.trial_receipts):
            raise ValueError("capture-mode campaign acceptance disagrees with its trials")
        return self


class CaptureModeAcceptanceHarness:
    """Verify three already-committed bundles without radios or a database."""

    def __init__(self, store: RecordingStore) -> None:
        _reject_qnap_path(store.root)
        _reject_symlinked_path(store.root)
        self._store = store

    @classmethod
    def open_read_only(cls, root: Path) -> Self:
        """Open an existing local store after no-follow QNAP confinement checks."""

        _reject_qnap_path(root)
        _reject_symlinked_path(root)
        return cls(RecordingStore.open_read_only(root))

    def run(
        self,
        expectation: CaptureModeExpectationV1,
        *,
        acceptance_id: str,
        independent_radio_a_session_id: str,
        independent_radio_b_session_id: str,
        synchronized_pair_session_id: str,
        receipt_path: Path | None = None,
        observed_utc_ns: int | None = None,
    ) -> CaptureModeAcceptanceReceiptV1:
        sessions: tuple[tuple[CaptureModeRole, str, tuple[str, ...]], ...] = (
            ("independent_radio_a", independent_radio_a_session_id, (expectation.radio_ids[0],)),
            ("independent_radio_b", independent_radio_b_session_id, (expectation.radio_ids[1],)),
            ("synchronized_pair", synchronized_pair_session_id, expectation.radio_ids),
        )
        if len({session_id for _, session_id, _ in sessions}) != 3:
            raise ValueError("capture-mode acceptance requires three distinct session IDs")
        checks = tuple(
            self._check(expectation, role, session_id, expected_radios)
            for role, session_id, expected_radios in sessions
        )
        receipt = CaptureModeAcceptanceReceiptV1(
            acceptance_id=acceptance_id,
            observed_utc_ns=time.time_ns() if observed_utc_ns is None else observed_utc_ns,
            expectation=expectation,
            checks=checks,  # type: ignore[arg-type]
            accepted=all(check.passed for check in checks),
        )
        if receipt_path is not None:
            _write_immutable_receipt(receipt_path, receipt)
        return receipt

    def run_campaign(
        self,
        expectation: CaptureModeExpectationV1,
        *,
        acceptance_id: str,
        independent_radio_a_session_ids: tuple[str, ...],
        independent_radio_b_session_ids: tuple[str, ...],
        synchronized_pair_session_ids: tuple[str, ...],
        receipt_path: Path | None = None,
        observed_utc_ns: int | None = None,
    ) -> CaptureModeCampaignAcceptanceReceiptV2:
        _require_hardware_expectation(expectation)
        strata = (
            independent_radio_a_session_ids,
            independent_radio_b_session_ids,
            synchronized_pair_session_ids,
        )
        if any(len(session_ids) != 10 for session_ids in strata):
            raise ValueError("capture-mode campaign requires exactly 10 sessions per stratum")
        all_session_ids = tuple(session_id for stratum in strata for session_id in stratum)
        if len(set(all_session_ids)) != 30:
            raise ValueError("capture-mode campaign requires 30 distinct sessions")
        trials = tuple(
            self.run(
                expectation,
                acceptance_id=f"capture-mode-trial-{index:02d}",
                independent_radio_a_session_id=independent_radio_a_session_ids[index],
                independent_radio_b_session_id=independent_radio_b_session_ids[index],
                synchronized_pair_session_id=synchronized_pair_session_ids[index],
            )
            for index in range(10)
        )
        receipt = CaptureModeCampaignAcceptanceReceiptV2(
            acceptance_id=acceptance_id,
            observed_utc_ns=time.time_ns() if observed_utc_ns is None else observed_utc_ns,
            expectation=expectation,
            trial_receipts=trials,
            accepted=all(trial.accepted for trial in trials),
        )
        if receipt_path is not None:
            _write_immutable_receipt(receipt_path, receipt)
        return receipt

    def _check(
        self,
        expectation: CaptureModeExpectationV1,
        role: CaptureModeRole,
        session_id: str,
        expected_radios: tuple[str, ...],
    ) -> CaptureModeSessionCheckV1:
        errors: list[str] = []
        try:
            bundle = self._store.inspect(session_id)
        except Exception as error:
            return CaptureModeSessionCheckV1(
                role=role,
                session_id=session_id,
                expected_radio_ids=expected_radios,
                errors=(f"bundle inspection failed: {type(error).__name__}: {error}",),
            )
        try:
            self._store.verify(bundle)
            digest_valid = True
        except Exception as error:
            digest_valid = False
            errors.append(f"bundle verification failed: {type(error).__name__}: {error}")

        manifest = bundle.manifest
        if isinstance(manifest, RecordingManifestV3):
            errors.append(
                "capture-mode acceptance V1 does not support device-axis RecordingManifestV3"
            )
            return CaptureModeSessionCheckV1(
                role=role,
                session_id=session_id,
                expected_radio_ids=expected_radios,
                bundle_uri=bundle.uri,
                manifest_session_id=manifest.session_id,
                manifest_sha256=bundle.manifest_sha256,
                digest_valid=digest_valid,
                errors=tuple(dict.fromkeys(errors)),
            )
        plan = manifest.capture_plan
        profile = plan.profile_revision.profile
        streams = manifest.streams
        sync = manifest.synchronization
        expected_effective = (
            SynchronizationMode.NONE
            if role != "synchronized_pair"
            else SynchronizationMode.BEST_EFFORT
        )

        _expect(errors, bundle.session_id == session_id, "inspected bundle session differs")
        _expect(errors, manifest.session_id == session_id, "manifest session differs")
        try:
            _expect(
                errors,
                self._store.resolve_uri(bundle.uri) == bundle.path,
                "bundle URI resolves to a different recording",
            )
        except Exception as error:
            errors.append(f"bundle URI resolution failed: {type(error).__name__}: {error}")

        _expect(errors, manifest.state is CaptureState.COMMITTED, "session is not committed")
        _expect(errors, manifest.source_type is expectation.source_type, "source type differs")
        if expectation.source_type is SourceType.LIVE:
            _expect(
                errors,
                "ACCEPTANCE" in manifest.tags,
                "live acceptance capture lacks the ACCEPTANCE tag",
            )
            _expect(
                errors,
                "CALIBRATION" not in manifest.tags,
                "acceptance capture is incorrectly tagged CALIBRATION",
            )
        _expect(
            errors,
            plan.profile_revision.revision_digest == expectation.profile_revision_digest,
            "profile revision differs",
        )
        _expect(errors, profile.name == expectation.profile_name, "profile name differs")
        _expect(
            errors,
            profile.center_frequency_hz == expectation.center_frequency_hz,
            "IF center differs",
        )
        _expect(
            errors,
            profile.rf_center_frequency_hz == expectation.rf_center_frequency_hz,
            "RF center differs",
        )
        _expect(
            errors,
            profile.starlink_channel == expectation.starlink_channel,
            "Starlink channel differs",
        )
        _expect(
            errors,
            getattr(profile.starlink_edge, "value", None) == expectation.starlink_edge,
            "Starlink edge differs",
        )
        _expect(errors, profile.sample_rate_hz == expectation.sample_rate_hz, "sample rate differs")
        _expect(errors, profile.bandwidth_hz == expectation.bandwidth_hz, "bandwidth differs")
        _expect(errors, profile.gain_mode is GainMode.MANUAL, "profile gain mode differs")
        _expect(
            errors,
            len(profile.gains) == 1 and profile.gains[0].gain_db == expectation.gain_db,
            "profile gain differs",
        )
        _expect(
            errors,
            profile.receivers == (expectation.receiver_id,),
            "profile is not the expected single RX",
        )
        _expect(
            errors,
            plan.resolved_sample_count == expectation.sample_count,
            "plan sample count differs",
        )
        _expect(errors, plan.radio_ids == expected_radios, "capture-plan radios differ")
        _expect(errors, len(streams) == len(expected_radios), "stream count differs")
        _expect(
            errors,
            tuple(stream.radio.radio_id for stream in streams) == expected_radios,
            "stream radios differ",
        )
        _expect(
            errors,
            plan.requested_synchronization_mode is SynchronizationMode.BEST_EFFORT,
            "requested synchronization mode differs",
        )
        _expect(
            errors,
            plan.effective_synchronization_mode is expected_effective,
            "effective synchronization mode differs",
        )
        _expect(
            errors,
            sync.effective_mode is expected_effective,
            "observed synchronization mode differs",
        )

        observed_gains: list[float] = []
        clipped_counts: list[int] = []
        clipped_fractions: list[float] = []
        constant_iq: list[bool] = []
        timing_evidence: list[CaptureModeStreamTimingEvidenceV1] = []
        for index, stream in enumerate(streams):
            settings = stream.applied_settings or stream.requested_settings
            _expect(errors, stream.state is StreamState.COMPLETE, f"stream {index} is not complete")
            hardware_identity = _expected_hardware_identity(stream.radio.radio_id)
            if expectation.source_type is SourceType.LIVE:
                _expect(
                    errors,
                    hardware_identity is not None
                    and stream.radio.serial == hardware_identity[0]
                    and stream.radio.uri == hardware_identity[1]
                    and stream.radio.transport is RadioTransport.IIO_IP,
                    f"stream {index} hardware identity differs",
                )
            _expect(
                errors,
                settings.receiver_ids == (expectation.receiver_id,),
                f"stream {index} receiver geometry differs",
            )
            _expect(
                errors,
                settings.center_frequency_hz == expectation.center_frequency_hz,
                f"stream {index} IF center differs",
            )
            _expect(
                errors,
                settings.sample_rate_hz == expectation.sample_rate_hz,
                f"stream {index} sample rate differs",
            )
            _expect(
                errors,
                settings.bandwidth_hz == expectation.bandwidth_hz,
                f"stream {index} bandwidth differs",
            )
            gain = settings.gains[0] if len(settings.gains) == 1 else None
            observed_gains.append(0.0 if gain is None else gain.gain_db)
            _expect(
                errors, settings.gain_mode is GainMode.MANUAL, f"stream {index} gain mode differs"
            )
            _expect(
                errors,
                gain is not None
                and gain.receiver_id == expectation.receiver_id
                and gain.gain_db == expectation.gain_db,
                f"stream {index} gain differs",
            )
            _expect(
                errors,
                stream.requested_sample_count == expectation.sample_count,
                f"stream {index} requested samples differ",
            )
            _expect(
                errors,
                stream.captured_sample_count == expectation.sample_count,
                f"stream {index} captured samples differ",
            )
            _expect(errors, bool(stream.chunks), f"stream {index} has no IQ chunks")
            _expect(errors, stream.timing is not None, f"stream {index} has no timing evidence")
            if stream.timing is not None:
                timing = _stream_timing_evidence(stream)
                timing_evidence.append(timing)
                expected_span_ns = (
                    (stream.captured_sample_count - 1) * 1_000_000_000 // settings.sample_rate_hz
                )
                observed_span_ns = timing.last_estimate_utc_ns - timing.first_estimate_utc_ns
                _expect(
                    errors,
                    abs(observed_span_ns - expected_span_ns) <= 1,
                    f"stream {index} timing span disagrees with sample geometry",
                )
            continuity = stream.continuity
            _expect(
                errors,
                continuity.gap_count <= expectation.maximum_gap_count,
                f"stream {index} gap count exceeds threshold",
            )
            _expect(
                errors,
                continuity.missing_sample_count <= expectation.maximum_missing_sample_count,
                f"stream {index} missing sample count exceeds threshold",
            )
            _expect(
                errors,
                continuity.overflow_count <= expectation.maximum_overflow_count,
                f"stream {index} overflow count exceeds threshold",
            )
            try:
                clipped_count, clipped_fraction, is_constant = _scan_stream_quality(
                    self._store.reader(bundle, stream.stream_id),
                    clipping_abs_threshold=expectation.clipping_abs_threshold,
                )
            except Exception as error:
                clipped_count, clipped_fraction, is_constant = 0, 0.0, False
                errors.append(
                    f"stream {index} quality scan failed: {type(error).__name__}: {error}"
                )
            clipped_counts.append(clipped_count)
            clipped_fractions.append(clipped_fraction)
            constant_iq.append(is_constant)
            _expect(
                errors,
                clipped_fraction <= expectation.maximum_clipped_sample_fraction,
                f"stream {index} clipped sample fraction exceeds threshold",
            )
            _expect(
                errors,
                int(is_constant) <= expectation.maximum_constant_iq_stream_count,
                f"stream {index} IQ is constant",
            )

        estimated_overlap_ns: int | None = None
        recomputed_overlap_fraction: float | None = None
        guaranteed_overlap_ns: int | None = None
        guaranteed_overlap_fraction: float | None = None
        estimated_start_skew_ns: int | None = None
        start_skew_uncertainty_ns: int | None = None
        if role == "synchronized_pair":
            _expect(
                errors,
                sync.grade
                in {SynchronizationGrade.BEST_EFFORT_OBSERVED, SynchronizationGrade.DEGRADED},
                "paired synchronization grade is invalid",
            )
            _expect(errors, sync.overlap_fraction is not None, "paired overlap is absent")
            if len(timing_evidence) == 2:
                (
                    estimated_overlap_ns,
                    recomputed_overlap_fraction,
                    guaranteed_overlap_ns,
                    guaranteed_overlap_fraction,
                    estimated_start_skew_ns,
                    start_skew_uncertainty_ns,
                ) = _recompute_pair_timing((timing_evidence[0], timing_evidence[1]))
                _expect(
                    errors,
                    recomputed_overlap_fraction >= expectation.minimum_pair_overlap_fraction,
                    "recomputed paired overlap is below threshold",
                )
                denominator_ns = min(
                    timing.sample_count * 1_000_000_000 // timing.sample_rate_hz
                    for timing in timing_evidence
                )
                if sync.overlap_fraction is not None:
                    _expect(
                        errors,
                        abs(sync.overlap_fraction - recomputed_overlap_fraction)
                        <= _OVERLAP_ROUNDING_TOLERANCE_NS / denominator_ns,
                        "manifest overlap differs from sample-clock overlap beyond "
                        "one-nanosecond fractional rounding tolerance",
                    )
            else:
                errors.append("paired timing evidence is incomplete")
        else:
            _expect(
                errors,
                sync.grade is SynchronizationGrade.NOT_REQUESTED,
                "independent session claims synchronization",
            )
            _expect(errors, sync.overlap_fraction is None, "independent session claims overlap")

        canonical_errors = tuple(dict.fromkeys(errors))
        return CaptureModeSessionCheckV1(
            role=role,
            session_id=session_id,
            expected_radio_ids=expected_radios,
            bundle_uri=bundle.uri,
            manifest_session_id=manifest.session_id,
            manifest_sha256=bundle.manifest_sha256,
            digest_valid=digest_valid,
            observed_radio_ids=tuple(stream.radio.radio_id for stream in streams),
            observed_radio_serials=tuple(stream.radio.serial for stream in streams),
            observed_radio_uris=tuple(stream.radio.uri for stream in streams),
            declared_receiver_chain_ids=tuple(
                _receiver_chain_id(stream.radio.radio_id) for stream in streams
            ),
            declared_hardware_epoch_ids=tuple(
                _hardware_epoch_id(stream.radio.radio_id) for stream in streams
            ),
            declared_station_topology_evidence_digests=tuple(
                _station_topology_digest(stream.radio.radio_id) for stream in streams
            ),
            observed_receiver_ids=tuple(
                (stream.applied_settings or stream.requested_settings).receiver_ids
                for stream in streams
            ),
            observed_sample_counts=tuple(stream.captured_sample_count for stream in streams),
            observed_gain_db=tuple(observed_gains),
            observed_gap_counts=tuple(stream.continuity.gap_count for stream in streams),
            observed_missing_sample_counts=tuple(
                stream.continuity.missing_sample_count for stream in streams
            ),
            observed_overflow_counts=tuple(stream.continuity.overflow_count for stream in streams),
            observed_clipped_sample_counts=tuple(clipped_counts),
            observed_clipped_sample_fractions=tuple(clipped_fractions),
            observed_constant_iq=tuple(constant_iq),
            stream_timing=tuple(timing_evidence),
            synchronization_grade=sync.grade,
            manifest_overlap_fraction=sync.overlap_fraction,
            overlap_fraction=recomputed_overlap_fraction,
            estimated_overlap_ns=estimated_overlap_ns,
            guaranteed_overlap_ns=guaranteed_overlap_ns,
            guaranteed_overlap_fraction=guaranteed_overlap_fraction,
            estimated_start_skew_ns=estimated_start_skew_ns,
            start_skew_uncertainty_ns=start_skew_uncertainty_ns,
            overlap_rounding_tolerance_ns=(1 if role == "synchronized_pair" else None),
            passed=digest_valid and not canonical_errors,
            errors=canonical_errors,
        )


def _expect(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _stream_timing_evidence(stream: RecordingStreamV1) -> CaptureModeStreamTimingEvidenceV1:
    timing = stream.timing
    if timing is None:
        raise ValueError("stream has no timing evidence")
    settings = stream.applied_settings or stream.requested_settings
    sample_period_ns = (1_000_000_000 + settings.sample_rate_hz - 1) // settings.sample_rate_hz
    first = timing.first_sample
    last = timing.last_sample
    return CaptureModeStreamTimingEvidenceV1(
        stream_id=stream.stream_id,
        radio_id=stream.radio.radio_id,
        sample_count=stream.captured_sample_count,
        sample_rate_hz=settings.sample_rate_hz,
        first_estimate_utc_ns=first.estimate_utc_ns,
        first_earliest_utc_ns=first.earliest_utc_ns,
        first_latest_utc_ns=first.latest_utc_ns,
        first_uncertainty_ns=first.latest_utc_ns - first.earliest_utc_ns,
        last_estimate_utc_ns=last.estimate_utc_ns,
        last_earliest_utc_ns=last.earliest_utc_ns,
        last_latest_utc_ns=last.latest_utc_ns,
        last_uncertainty_ns=last.latest_utc_ns - last.earliest_utc_ns,
        sample_interval_end_estimate_utc_ns=last.estimate_utc_ns + sample_period_ns,
    )


def _recompute_pair_timing(
    timing: tuple[CaptureModeStreamTimingEvidenceV1, CaptureModeStreamTimingEvidenceV1],
) -> tuple[int, float, int, float, int, int]:
    first, second = timing
    overlap_start = max(first.first_estimate_utc_ns, second.first_estimate_utc_ns)
    overlap_end = min(
        first.sample_interval_end_estimate_utc_ns,
        second.sample_interval_end_estimate_utc_ns,
    )
    estimated_overlap_ns = max(0, overlap_end - overlap_start)
    denominator = min(
        first.sample_interval_end_estimate_utc_ns - first.first_estimate_utc_ns,
        second.sample_interval_end_estimate_utc_ns - second.first_estimate_utc_ns,
    )
    if denominator <= 0:
        raise ValueError("paired timing interval has no positive duration")
    estimated_fraction = min(1.0, estimated_overlap_ns / denominator)
    guaranteed_start = max(first.first_latest_utc_ns, second.first_latest_utc_ns)
    guaranteed_end = min(
        first.last_earliest_utc_ns
        + first.sample_interval_end_estimate_utc_ns
        - first.last_estimate_utc_ns,
        second.last_earliest_utc_ns
        + second.sample_interval_end_estimate_utc_ns
        - second.last_estimate_utc_ns,
    )
    guaranteed_overlap_ns = max(0, guaranteed_end - guaranteed_start)
    guaranteed_fraction = min(1.0, guaranteed_overlap_ns / denominator)
    estimated_skew_ns = abs(first.first_estimate_utc_ns - second.first_estimate_utc_ns)
    skew_uncertainty_ns = first.first_uncertainty_ns + second.first_uncertainty_ns
    return (
        estimated_overlap_ns,
        estimated_fraction,
        guaranteed_overlap_ns,
        guaranteed_fraction,
        estimated_skew_ns,
        skew_uncertainty_ns,
    )


def _receiver_chain_id(radio_id: str) -> str:
    mapping = dict(zip(_HARDWARE_RADIO_IDS, _HARDWARE_RECEIVER_CHAINS, strict=True))
    return mapping.get(radio_id, "rx1")


def _hardware_epoch_id(radio_id: str) -> str:
    mapping = dict(zip(_HARDWARE_RADIO_IDS, _HARDWARE_EPOCH_IDS, strict=True))
    return mapping.get(radio_id, "unqualified-test-hardware-epoch")


def _station_topology_digest(radio_id: str) -> str:
    mapping = dict(zip(_HARDWARE_RADIO_IDS, _HARDWARE_STATION_TOPOLOGY_DIGESTS, strict=True))
    return mapping.get(
        radio_id,
        "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    )


def _expected_hardware_identity(radio_id: str) -> tuple[str, str] | None:
    mapping = {
        configured_id: (serial, uri)
        for configured_id, serial, uri in zip(
            _HARDWARE_RADIO_IDS,
            _HARDWARE_RADIO_SERIALS,
            _HARDWARE_RADIO_URIS,
            strict=True,
        )
    }
    return mapping.get(radio_id)


def _require_hardware_expectation(expectation: CaptureModeExpectationV1) -> None:
    required = (
        expectation.profile_name == _HARDWARE_PROFILE_NAME
        and expectation.profile_revision_digest == _HARDWARE_PROFILE_REVISION_DIGEST
        and expectation.receiver_id == _HARDWARE_RECEIVER_ID
        and expectation.center_frequency_hz == _HARDWARE_IF_HZ
        and expectation.rf_center_frequency_hz == _HARDWARE_RF_HZ
        and expectation.sample_rate_hz == _HARDWARE_SAMPLE_RATE_HZ
        and expectation.bandwidth_hz == _HARDWARE_BANDWIDTH_HZ
        and expectation.gain_db == _HARDWARE_GAIN_DB
        and expectation.sample_count == _HARDWARE_SAMPLE_COUNT
        and expectation.source_type is SourceType.LIVE
        and expectation.minimum_pair_overlap_fraction == _HARDWARE_MINIMUM_OVERLAP
        and expectation.clipping_abs_threshold == _HARDWARE_CLIPPING_ABS_THRESHOLD
        and expectation.clipping_semantics == _HARDWARE_CLIPPING_SEMANTICS
        and expectation.clipping_provenance == _HARDWARE_CLIPPING_PROVENANCE
        and expectation.radio_ids == _HARDWARE_RADIO_IDS
        and expectation.hardware_epoch_ids == _HARDWARE_EPOCH_IDS
        and expectation.station_topology_evidence_digests == _HARDWARE_STATION_TOPOLOGY_DIGESTS
    )
    if not required:
        raise ValueError(
            "hardware capture-mode campaign requires the immutable 60s CH4 LOWER RX1 "
            "2.5MS/s 40dB LIVE profile, fixed Pluto identities, native 2047-count rail, "
            "and frozen 0.99 overlap threshold"
        )


def _scan_stream_quality(
    reader: IqReader,
    *,
    clipping_abs_threshold: int,
) -> tuple[int, float, bool]:
    """Compute bounded-memory ADC clipping and constant-IQ evidence from stored CI16."""

    clipped = 0
    observed = 0
    minimum: np.ndarray | None = None
    maximum: np.ndarray | None = None
    for block in reader.iter_blocks(block_samples=262_144):
        values = block.samples[:, 0, :].astype(np.int32, copy=False)
        magnitudes = np.abs(values)
        clipped += int(np.count_nonzero(np.any(magnitudes >= clipping_abs_threshold, axis=1)))
        observed += len(values)
        block_minimum = values.min(axis=0)
        block_maximum = values.max(axis=0)
        minimum = block_minimum if minimum is None else np.minimum(minimum, block_minimum)
        maximum = block_maximum if maximum is None else np.maximum(maximum, block_maximum)
    if observed != reader.sample_count:
        raise ValueError("quality scan does not cover the stored sample count")
    if minimum is None or maximum is None:
        raise ValueError("quality scan observed no IQ samples")
    return clipped, clipped / observed, bool(np.array_equal(minimum, maximum))


def _write_immutable_receipt(
    path: Path,
    receipt: CaptureModeAcceptanceReceiptV1 | CaptureModeCampaignAcceptanceReceiptV2,
) -> None:
    _reject_qnap_path(path)
    _reject_symlinked_path(path.parent)
    if not path.name or path.name in {".", ".."}:
        raise ValueError("capture-mode receipt path must name one file")
    parent = Path(os.path.abspath(path.parent))
    _reject_qnap_path(parent)
    try:
        parent_mode = os.lstat(parent).st_mode
    except FileNotFoundError as error:
        raise ValueError("capture-mode receipt parent does not exist") from error
    if not stat.S_ISDIR(parent_mode):
        raise ValueError("capture-mode receipt parent is not a directory")
    destination = parent / path.name
    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"immutable capture-mode receipt already exists: {destination}")
    payload = receipt.model_dump_json(indent=2).encode("utf-8") + b"\n"
    if len(payload) > 128 * 1024:
        raise ValueError("capture-mode receipt exceeds its bounded size")
    temporary = parent / f".{path.name}.{os.getpid()}-{uuid4().hex}.partial"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o440,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _reject_qnap_path(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    qnap = Path("/mnt/qnap01")
    if absolute == qnap or qnap in absolute.parents:
        raise ValueError("capture-mode acceptance cannot use a QNAP path")


def _reject_symlinked_path(path: Path) -> None:
    """Reject every existing symlink component without following its target."""

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return
        if stat.S_ISLNK(mode):
            target = Path(os.readlink(current))
            lexical_target = target if target.is_absolute() else current.parent / target
            _reject_qnap_path(lexical_target)
            raise ValueError(f"capture-mode acceptance path is symlinked: {current}")
