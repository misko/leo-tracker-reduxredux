"""Replayable, fail-closed generation of WP11 empirical acquisition centers."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import (
    Sha256Digest,
    canonical_digest,
    canonical_json_bytes,
    sha256_digest,
)
from leo.contracts.recording import RecordingManifestV1
from leo.contracts.states import CaptureState, GainMode, SourceType, StreamState
from leo.storage import PathConfinementError, parse_recording_bundle_uri

SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
GitRevision = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]

PROFILE_NAME = "starlink-ch4-lower-2p5m-60s-rx1-centered-v1"
PROFILE_DIGEST = "sha256:0f6aa753e16feaba1f76df21f0b620f32ab0b72456cb6034f2b1ea6a60c11e1a"
IF_CENTER_HZ = 1_709_521_250
RF_CENTER_HZ = 11_459_521_250
LNB_LO_HZ = 9_750_000_000
SAMPLE_RATE_HZ = 2_500_000
BANDWIDTH_HZ = 2_500_000
SAMPLE_COUNT = 150_000_000
GAIN_DB = 40.0
WINDOW_COUNT = 600
WINDOW_SAMPLE_COUNT = 25_000
WINDOW_STRIDE_SAMPLES = 250_000
PILOT_OCCUPIED_HALF_WIDTH_HZ = 937_500.0
SATELLITE_DOPPLER_GUARD_HZ = 300_000.0
# No additional filter-edge allowance has been scientifically established.  It
# is explicit and frozen at zero; adding one tightens (and may invalidate) the
# 2.5 MS/s profile, never permits reducing the Doppler guard.
EDGE_FILTER_GUARD_HZ = 0.0
RESIDUAL_SEARCH_HALF_WIDTH_HZ = 400_000.0
CANDIDATE_SCORE_THRESHOLD = 8.0
MINIMUM_CANDIDATES_PER_SESSION = 3
MINIMUM_USABLE_CANDIDATES = 9
MINIMUM_USABLE_SESSIONS = 3
MEASUREMENT_ALLOWANCE_HZ = 500.0
MAXIMUM_UNCERTAINTY_HZ = 200_000.0
SESSION_CENTER_MAD_OUTLIER_MULTIPLIER = 4.5
SESSION_CENTER_MINIMUM_OUTLIER_THRESHOLD_HZ = 10_000.0
SESSION_CENTER_MAXIMUM_ROBUST_SIGMA_HZ = 100_000.0
SESSION_CENTER_MULTIMODAL_GAP_HZ = 75_000.0
WITHIN_SESSION_MAXIMUM_ROBUST_SIGMA_HZ = 100_000.0
WITHIN_SESSION_MULTIMODAL_GAP_HZ = 75_000.0
WITHIN_SESSION_MAXIMUM_RADIUS_HZ = 200_000.0
TIMING_QUANTIZATION_NS = 0
METHOD = "unverified_foundation_equal_session_median_mad_acquisition_center_v2"
EXTRACTOR_IMPLEMENTATION = "leo.wp11.blind_pilot_calibration_windows.v1"
TEMPLATE_DIGEST = canonical_digest(
    {
        "kind": "starlink_ch4_lower_sync_template_v1",
        "tone_centers_hz": [-820_312.5, 820_312.5],
        "occupied_half_width_hz": PILOT_OCCUPIED_HALF_WIDTH_HZ,
    }
)
EXTRACTOR_CONFIG_DIGEST = canonical_digest(
    {
        "implementation": EXTRACTOR_IMPLEMENTATION,
        "window_count": WINDOW_COUNT,
        "window_sample_count": WINDOW_SAMPLE_COUNT,
        "window_stride_samples": WINDOW_STRIDE_SAMPLES,
        "score_threshold": CANDIDATE_SCORE_THRESHOLD,
        "template_digest": TEMPLATE_DIGEST,
    }
)
_RADIO_TOPOLOGY = {
    "radio_pluto_5d4d": (
        "1040005e0b100007100010000bf33a5d4d",
        "rx_lnb_b",
        "hw_gauss_r20_science_postreboot_20260816_v1",
        "sha256:eff9673575738b3bd72246d02252e41b5d1d548ae775e9eb453e1ee3a8290bfa",
    ),
    "radio_pluto_19f2": (
        "10400056f695001322002d0010ad1719f2",
        "rx_lnb_d",
        "hw_gauss_r21_science_postreboot_20260816_v1",
        "sha256:eb69aef0b2211b3073d125da66f29ec2154e06a4a52916c2d0a036e8f17efef7",
    ),
}


class FrequencyCalibrationPlanV1(ContractModel):
    """Predeclared identity and exact, non-relaxable WP11 method."""

    schema_version: Literal[1] = 1
    plan_id: SafeIdentifier
    plan_digest: Sha256Digest
    declared_utc_ns: Annotated[int, Field(ge=0)]
    campaign_role: Literal["pre_acceptance_frequency_calibration"] = (
        "pre_acceptance_frequency_calibration"
    )
    raw_iq_reuse_policy: Literal["forbid_acceptance_evaluation"] = (
        "forbid_acceptance_evaluation"
    )
    radio_id: SafeIdentifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    topology_evidence_digest: Sha256Digest
    scheduled_session_ids: tuple[SafeIdentifier, ...]
    extractor_git_revision: GitRevision
    extractor_source_tree_digest: Sha256Digest
    extractor_executable_digest: Sha256Digest
    evidence_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    profile_name: str = PROFILE_NAME
    profile_revision_digest: Sha256Digest = PROFILE_DIGEST
    center_frequency_hz: int = IF_CENTER_HZ
    rf_center_frequency_hz: int = RF_CENTER_HZ
    lnb_lo_hz: int = LNB_LO_HZ
    sample_rate_hz: int = SAMPLE_RATE_HZ
    bandwidth_hz: int = BANDWIDTH_HZ
    receiver_ids: tuple[Literal[1], ...] = (1,)
    gain_db: float = GAIN_DB
    dwell_seconds: Literal[60] = 60
    sample_count: int = SAMPLE_COUNT
    starlink_channel: Literal["ch4"] = "ch4"
    starlink_edge: Literal["lower"] = "lower"
    window_count: int = WINDOW_COUNT
    window_sample_count: int = WINDOW_SAMPLE_COUNT
    window_stride_samples: int = WINDOW_STRIDE_SAMPLES
    template_digest: Sha256Digest = TEMPLATE_DIGEST
    extractor_implementation: str = EXTRACTOR_IMPLEMENTATION
    extractor_config_digest: Sha256Digest = EXTRACTOR_CONFIG_DIGEST
    candidate_score_threshold: float = CANDIDATE_SCORE_THRESHOLD
    minimum_candidates_per_session: int = MINIMUM_CANDIDATES_PER_SESSION
    minimum_usable_candidates: int = MINIMUM_USABLE_CANDIDATES
    minimum_distinct_usable_sessions: int = MINIMUM_USABLE_SESSIONS
    session_center_mad_outlier_multiplier: float = SESSION_CENTER_MAD_OUTLIER_MULTIPLIER
    session_center_minimum_outlier_threshold_hz: float = (
        SESSION_CENTER_MINIMUM_OUTLIER_THRESHOLD_HZ
    )
    session_center_maximum_robust_sigma_hz: float = SESSION_CENTER_MAXIMUM_ROBUST_SIGMA_HZ
    session_center_multimodal_gap_hz: float = SESSION_CENTER_MULTIMODAL_GAP_HZ
    within_session_maximum_robust_sigma_hz: float = WITHIN_SESSION_MAXIMUM_ROBUST_SIGMA_HZ
    within_session_multimodal_gap_hz: float = WITHIN_SESSION_MULTIMODAL_GAP_HZ
    within_session_maximum_radius_hz: float = WITHIN_SESSION_MAXIMUM_RADIUS_HZ
    candidate_measurement_uncertainty_hz: float = MEASUREMENT_ALLOWANCE_HZ
    maximum_calibration_uncertainty_hz: float = MAXIMUM_UNCERTAINTY_HZ
    pilot_occupied_half_width_hz: float = PILOT_OCCUPIED_HALF_WIDTH_HZ
    residual_search_half_width_hz: float = RESIDUAL_SEARCH_HALF_WIDTH_HZ
    minimum_satellite_doppler_guard_hz: float = SATELLITE_DOPPLER_GUARD_HZ
    edge_filter_guard_hz: float = EDGE_FILTER_GUARD_HZ
    timing_quantization_ns: int = TIMING_QUANTIZATION_NS
    validity_delay_ns: Literal[1] = 1

    @model_validator(mode="after")
    def _frozen_and_content_addressed(self) -> Self:
        frozen = {
            "profile_name": PROFILE_NAME,
            "profile_revision_digest": PROFILE_DIGEST,
            "center_frequency_hz": IF_CENTER_HZ,
            "rf_center_frequency_hz": RF_CENTER_HZ,
            "lnb_lo_hz": LNB_LO_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "bandwidth_hz": BANDWIDTH_HZ,
            "gain_db": GAIN_DB,
            "sample_count": SAMPLE_COUNT,
            "window_count": WINDOW_COUNT,
            "window_sample_count": WINDOW_SAMPLE_COUNT,
            "window_stride_samples": WINDOW_STRIDE_SAMPLES,
            "template_digest": TEMPLATE_DIGEST,
            "extractor_implementation": EXTRACTOR_IMPLEMENTATION,
            "extractor_config_digest": EXTRACTOR_CONFIG_DIGEST,
            "candidate_score_threshold": CANDIDATE_SCORE_THRESHOLD,
            "minimum_candidates_per_session": MINIMUM_CANDIDATES_PER_SESSION,
            "minimum_usable_candidates": MINIMUM_USABLE_CANDIDATES,
            "minimum_distinct_usable_sessions": MINIMUM_USABLE_SESSIONS,
            "session_center_mad_outlier_multiplier": SESSION_CENTER_MAD_OUTLIER_MULTIPLIER,
            "session_center_minimum_outlier_threshold_hz": (
                SESSION_CENTER_MINIMUM_OUTLIER_THRESHOLD_HZ
            ),
            "session_center_maximum_robust_sigma_hz": (
                SESSION_CENTER_MAXIMUM_ROBUST_SIGMA_HZ
            ),
            "session_center_multimodal_gap_hz": SESSION_CENTER_MULTIMODAL_GAP_HZ,
            "within_session_maximum_robust_sigma_hz": (
                WITHIN_SESSION_MAXIMUM_ROBUST_SIGMA_HZ
            ),
            "within_session_multimodal_gap_hz": WITHIN_SESSION_MULTIMODAL_GAP_HZ,
            "within_session_maximum_radius_hz": WITHIN_SESSION_MAXIMUM_RADIUS_HZ,
            "candidate_measurement_uncertainty_hz": MEASUREMENT_ALLOWANCE_HZ,
            "maximum_calibration_uncertainty_hz": MAXIMUM_UNCERTAINTY_HZ,
            "pilot_occupied_half_width_hz": PILOT_OCCUPIED_HALF_WIDTH_HZ,
            "residual_search_half_width_hz": RESIDUAL_SEARCH_HALF_WIDTH_HZ,
            "minimum_satellite_doppler_guard_hz": SATELLITE_DOPPLER_GUARD_HZ,
            "edge_filter_guard_hz": EDGE_FILTER_GUARD_HZ,
            "timing_quantization_ns": TIMING_QUANTIZATION_NS,
        }
        actual = self.model_dump(mode="python", include=set(frozen))
        if actual != frozen:
            raise ValueError("WP11 calibration geometry and thresholds are frozen")
        if len(self.scheduled_session_ids) < MINIMUM_USABLE_SESSIONS:
            raise ValueError("at least three calibration sessions must be predeclared")
        if self.receiver_ids != (1,):
            raise ValueError("frequency calibration requires exactly RX1")
        expected_topology = _RADIO_TOPOLOGY.get(self.radio_id)
        if expected_topology != (
            self.radio_serial,
            self.physical_receiver_id,
            self.hardware_epoch_id,
            self.topology_evidence_digest,
        ):
            raise ValueError("radio/path/topology identity is not the frozen WP11 station topology")
        if len(set(self.scheduled_session_ids)) != len(self.scheduled_session_ids):
            raise ValueError("scheduled calibration session ids must be unique")
        expected_uri = f"qualification://frequency-calibration/{self.plan_id}/evidence.json"
        if self.evidence_uri != expected_uri:
            raise ValueError(f"evidence URI must be canonical: {expected_uri}")
        if self.plan_digest != _digest_without(self, "plan_digest"):
            raise ValueError("frequency-calibration plan digest does not match content")
        return self

    @classmethod
    def create(cls, **values: Any) -> Self:
        document: dict[str, Any] = {"schema_version": 1, **values}
        candidate = cls.model_construct(plan_digest="sha256:" + "0" * 64, **document)
        normalized = candidate.model_dump(mode="json", exclude={"plan_digest"})
        return cls(plan_digest=canonical_digest(normalized), **normalized)


class CalibrationCaptureEnvelopeV1(ContractModel):
    """Sealed manifest plus external physical-path/topology identity."""

    schema_version: Literal[1] = 1
    envelope_digest: Sha256Digest
    recording_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    manifest_digest: Sha256Digest
    manifest: RecordingManifestV1
    stream_id: SafeIdentifier
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    topology_evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def _validate_capture(self) -> Self:
        try:
            uri_session_id = parse_recording_bundle_uri(self.recording_uri)
        except PathConfinementError as error:
            raise ValueError(str(error)) from error
        if uri_session_id != self.manifest.session_id:
            raise ValueError("recording URI session does not match manifest")
        created = datetime.fromtimestamp(
            self.manifest.created_utc_ns // 1_000_000_000,
            tz=UTC,
        )
        expected_uri = (
            f"bulk://recordings/{created.year:04d}/{created.month:02d}/{created.day:02d}/"
            f"{quote(self.manifest.session_id, safe='._-:')}"
        )
        if self.recording_uri != expected_uri:
            raise ValueError("recording URI date/path does not match canonical manifest location")
        expected_manifest = sha256_digest(
            canonical_json_bytes(self.manifest.model_dump(mode="json"))
        )
        if self.manifest_digest != expected_manifest:
            raise ValueError("manifest digest does not match canonical manifest content")
        if self.manifest.state is not CaptureState.COMMITTED:
            raise ValueError("calibration capture must be committed")
        if self.manifest.source_type is not SourceType.LIVE:
            raise ValueError("calibration capture must be live")
        if "CALIBRATION" not in self.manifest.tags or "ACCEPTANCE" in self.manifest.tags:
            raise ValueError("capture must be calibration-only, never acceptance")
        if len(self.manifest.streams) != 1 or self.manifest.streams[0].stream_id != self.stream_id:
            raise ValueError("calibration manifest must contain exactly the bound stream")
        stream = self.manifest.streams[0]
        profile = self.manifest.capture_plan.profile_revision
        if profile.revision_digest != PROFILE_DIGEST or profile.profile.name != PROFILE_NAME:
            raise ValueError("capture does not use the exact frozen centered profile")
        if stream.state is not StreamState.COMPLETE or stream.applied_settings is None:
            raise ValueError("calibration stream must be complete with applied settings")
        settings = stream.applied_settings
        if (
            settings.center_frequency_hz != IF_CENTER_HZ
            or settings.sample_rate_hz != SAMPLE_RATE_HZ
            or settings.bandwidth_hz != BANDWIDTH_HZ
            or settings.receiver_ids != (1,)
            or settings.gain_mode is not GainMode.MANUAL
            or len(settings.gains) != 1
            or settings.gains[0].receiver_id != 1
            or settings.gains[0].gain_db != GAIN_DB
            or stream.captured_sample_count != SAMPLE_COUNT
            or stream.requested_sample_count != SAMPLE_COUNT
        ):
            raise ValueError("applied capture geometry differs from frozen WP11 profile")
        continuity = stream.continuity
        if continuity.gap_count or continuity.missing_sample_count or continuity.overflow_count:
            raise ValueError("calibration stream must be contiguous without observed loss")
        if stream.timing is None:
            raise ValueError("calibration stream requires timing evidence")
        first, last = stream.timing.first_sample, stream.timing.last_sample
        numerator = (SAMPLE_COUNT - 1) * 1_000_000_000
        expected_floor = numerator // SAMPLE_RATE_HZ
        expected_ceil = math.ceil(numerator / SAMPLE_RATE_HZ)
        possible_lower = last.earliest_utc_ns - first.latest_utc_ns
        possible_upper = last.latest_utc_ns - first.earliest_utc_ns
        if (
            possible_lower > expected_ceil + TIMING_QUANTIZATION_NS
            or possible_upper < expected_floor - TIMING_QUANTIZATION_NS
        ):
            raise ValueError("manifest timing cannot support exact N/Fs geometry")
        if self.envelope_digest != _digest_without(self, "envelope_digest"):
            raise ValueError("capture envelope digest does not match content")
        return self

    @classmethod
    def create(cls, **values: Any) -> Self:
        return _create_digested(cls, "envelope_digest", values)

    def interval_bounds(self) -> tuple[int, int]:
        timing = self.manifest.streams[0].timing
        assert timing is not None
        sample_ns = math.ceil(1_000_000_000 / SAMPLE_RATE_HZ)
        return timing.first_sample.earliest_utc_ns, timing.last_sample.latest_utc_ns + sample_ns


class CalibrationWindowObservationV1(ContractModel):
    schema_version: Literal[1] = 1
    observation_id: SafeIdentifier
    window_index: Annotated[int, Field(ge=0, lt=WINDOW_COUNT)]
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: int = WINDOW_SAMPLE_COUNT
    decision: Literal["candidate", "no_candidate"]
    candidate_score: Annotated[float, Field(ge=0)]
    candidate_offset_hz: float | None = None

    @field_validator("candidate_score", "candidate_offset_hz")
    @classmethod
    def _finite(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("extractor observations must be finite")
        return value

    @model_validator(mode="after")
    def _decision_replays(self) -> Self:
        if self.sample_count != WINDOW_SAMPLE_COUNT:
            raise ValueError("calibration window sample count is frozen")
        if self.sample_start != self.window_index * WINDOW_STRIDE_SAMPLES:
            raise ValueError("calibration windows must use frozen 10%-exposure geometry")
        candidate = self.candidate_score >= CANDIDATE_SCORE_THRESHOLD
        if candidate != (self.decision == "candidate"):
            raise ValueError("candidate decision does not replay from frozen threshold")
        if candidate != (self.candidate_offset_hz is not None):
            raise ValueError("only candidates carry an offset")
        if self.candidate_offset_hz is not None and abs(self.candidate_offset_hz) > min(
            SAMPLE_RATE_HZ, BANDWIDTH_HZ
        ) / 2:
            raise ValueError("candidate offset lies outside usable sampled bandwidth")
        return self


class CalibrationExtractorReceiptV1(ContractModel):
    schema_version: Literal[1] = 1
    receipt_digest: Sha256Digest
    envelope_digest: Sha256Digest
    recording_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    manifest_digest: Sha256Digest
    session_id: SafeIdentifier
    stream_id: SafeIdentifier
    radio_id: SafeIdentifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    profile_revision_digest: Sha256Digest = PROFILE_DIGEST
    extractor_implementation: str = EXTRACTOR_IMPLEMENTATION
    extractor_config_digest: Sha256Digest = EXTRACTOR_CONFIG_DIGEST
    template_digest: Sha256Digest = TEMPLATE_DIGEST
    git_revision: GitRevision
    source_tree_digest: Sha256Digest
    executable_digest: Sha256Digest
    observations: tuple[CalibrationWindowObservationV1, ...]

    @model_validator(mode="after")
    def _sealed_and_complete(self) -> Self:
        if (
            self.profile_revision_digest != PROFILE_DIGEST
            or self.extractor_implementation != EXTRACTOR_IMPLEMENTATION
            or self.extractor_config_digest != EXTRACTOR_CONFIG_DIGEST
            or self.template_digest != TEMPLATE_DIGEST
        ):
            raise ValueError("extractor implementation/config/template are frozen")
        indexes = tuple(item.window_index for item in self.observations)
        if indexes != tuple(range(WINDOW_COUNT)):
            raise ValueError("extractor receipt must retain exactly 600 ordered windows")
        ids = tuple(item.observation_id for item in self.observations)
        if len(set(ids)) != len(ids):
            raise ValueError("extractor observation ids must be unique")
        if self.receipt_digest != _digest_without(self, "receipt_digest"):
            raise ValueError("extractor receipt digest does not match content")
        return self

    @classmethod
    def create(cls, **values: Any) -> Self:
        return _create_digested(cls, "receipt_digest", values)


class FrequencyCalibrationDwellV1(ContractModel):
    schema_version: Literal[1] = 1
    scheduled_index: Annotated[int, Field(ge=0)]
    capture: CalibrationCaptureEnvelopeV1
    extraction: CalibrationExtractorReceiptV1

    @model_validator(mode="after")
    def _bindings_match(self) -> Self:
        stream = self.capture.manifest.streams[0]
        pairs = (
            (self.extraction.envelope_digest, self.capture.envelope_digest),
            (self.extraction.recording_uri, self.capture.recording_uri),
            (self.extraction.manifest_digest, self.capture.manifest_digest),
            (self.extraction.session_id, self.capture.manifest.session_id),
            (self.extraction.stream_id, self.capture.stream_id),
            (self.extraction.radio_id, stream.radio.radio_id),
            (self.extraction.radio_serial, stream.radio.serial),
            (self.extraction.physical_receiver_id, self.capture.physical_receiver_id),
            (self.extraction.hardware_epoch_id, self.capture.hardware_epoch_id),
        )
        if any(left != right for left, right in pairs):
            raise ValueError("extractor receipt is not bound to capture envelope")
        return self


class FrequencyCalibrationSessionStatisticsV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SafeIdentifier
    candidate_count: Annotated[int, Field(ge=0)]
    center_hz: float | None
    robust_sigma_hz: float | None
    radius_hz: float | None
    multimodal: bool
    usable: bool


class FrequencyCalibrationEvidenceV1(ContractModel):
    """Persisted inputs and results; validation performs a pure full replay."""

    schema_version: Literal[1] = 1
    evidence_digest: Sha256Digest
    plan: FrequencyCalibrationPlanV1
    dwells: tuple[FrequencyCalibrationDwellV1, ...]
    output_calibration_id: SafeIdentifier
    output_calibration_set_id: SafeIdentifier
    output_created_utc_ns: Annotated[int, Field(ge=0)]
    output_valid_until_utc_ns: Annotated[int | None, Field(ge=0)] = None
    trust_status: Literal["unverified_foundation"] = "unverified_foundation"
    acceptance_eligible: Literal[False] = False
    required_operational_stage: Literal[
        "trusted_store_extractor_and_predeclaration_verification"
    ] = "trusted_store_extractor_and_predeclaration_verification"
    status: Literal["sufficient", "insufficient"]
    reasons: tuple[str, ...]
    usable_candidate_count: Annotated[int, Field(ge=0)]
    usable_session_count: Annotated[int, Field(ge=0)]
    inlier_candidate_count: Annotated[int, Field(ge=0)]
    inlier_session_count: Annotated[int, Field(ge=0)]
    rejected_session_center_outlier_count: Annotated[int, Field(ge=0)]
    session_statistics: tuple[FrequencyCalibrationSessionStatisticsV1, ...]
    session_centers_hz: tuple[float, ...]
    inlier_session_ids: tuple[SafeIdentifier, ...]
    empirical_center_hz: float | None
    session_center_robust_sigma_hz: float | None
    uncertainty_lower_hz: float | None
    uncertainty_upper_hz: float | None
    sampled_band_margin_hz: float | None
    residual_search_margin_hz: float | None
    valid_from_utc_ns: int | None
    method: str = METHOD
    interpretation: Literal[
        "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"
    ] = "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"

    @model_validator(mode="after")
    def _replay_every_derived_field(self) -> Self:
        if self.method != METHOD:
            raise ValueError("calibration method is frozen")
        expected = _derive(self.plan, self.dwells)
        actual = self.model_dump(
            mode="python",
            include=set(expected),
        )
        if actual != expected:
            raise ValueError("persisted calibration derivation does not replay")
        if self.output_created_utc_ns < max(d.capture.interval_bounds()[1] for d in self.dwells):
            raise ValueError("calibration output creation predates capture evidence")
        if self.evidence_digest != _digest_without(self, "evidence_digest"):
            raise ValueError("frequency-calibration evidence digest does not match content")
        return self


class FrequencyCalibrationDraftEstimateV1(ContractModel):
    """Non-promotable mathematical estimate; deliberately not a science calibration."""

    schema_version: Literal[1] = 1
    draft_digest: Sha256Digest
    trust_status: Literal["unverified_foundation"] = "unverified_foundation"
    acceptance_eligible: Literal[False] = False
    proposed_calibration_id: SafeIdentifier
    proposed_calibration_set_id: SafeIdentifier
    radio_id: SafeIdentifier
    radio_serial: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    receiver_id: Literal[1] = 1
    physical_receiver_id: SafeIdentifier
    hardware_epoch_id: SafeIdentifier
    center_hz: float
    uncertainty_lower_hz: float
    uncertainty_upper_hz: float
    proposed_valid_from_utc_ns: Annotated[int, Field(ge=0)]
    proposed_valid_until_utc_ns: Annotated[int | None, Field(ge=0)] = None
    method: Literal[
        "unverified_foundation_equal_session_median_mad_acquisition_center_v2"
    ] = "unverified_foundation_equal_session_median_mad_acquisition_center_v2"
    evidence_uri: Annotated[str, StringConstraints(min_length=1, max_length=2048)]
    evidence_digest: Sha256Digest
    required_promoter: Literal[
        "trusted_store_extractor_and_predeclaration_verification"
    ] = "trusted_store_extractor_and_predeclaration_verification"

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        if not self.uncertainty_lower_hz <= self.center_hz <= self.uncertainty_upper_hz:
            raise ValueError("draft uncertainty bounds do not contain center")
        if self.draft_digest != _digest_without(self, "draft_digest"):
            raise ValueError("draft estimate digest does not match content")
        return self


class FrequencyCalibrationGenerationV1(ContractModel):
    schema_version: Literal[1] = 1
    evidence: FrequencyCalibrationEvidenceV1
    draft_estimate: FrequencyCalibrationDraftEstimateV1 | None
    calibration: None = None
    calibration_set: None = None
    trust_status: Literal["unverified_foundation"] = "unverified_foundation"
    acceptance_eligible: Literal[False] = False

    @model_validator(mode="after")
    def _replay_exact_outputs(self) -> Self:
        if self.calibration is not None or self.calibration_set is not None:
            raise ValueError("foundation can never emit public calibration contracts")
        if self.evidence.status == "insufficient":
            if self.draft_estimate is not None:
                raise ValueError("insufficient evidence cannot emit a draft estimate")
            return self
        expected = _build_draft_estimate(self.evidence)
        if self.draft_estimate != expected:
            raise ValueError("draft estimate does not replay from evidence")
        return self


def generate_frequency_calibration(
    *,
    plan: FrequencyCalibrationPlanV1,
    dwells: tuple[FrequencyCalibrationDwellV1, ...],
    calibration_id: str,
    calibration_set_id: str,
    created_utc_ns: int,
    valid_until_utc_ns: int | None = None,
) -> FrequencyCalibrationGenerationV1:
    derived = _derive(plan, dwells)
    values: dict[str, Any] = {
        "schema_version": 1,
        "plan": plan,
        "dwells": dwells,
        "output_calibration_id": calibration_id,
        "output_calibration_set_id": calibration_set_id,
        "output_created_utc_ns": created_utc_ns,
        "output_valid_until_utc_ns": valid_until_utc_ns,
        "trust_status": "unverified_foundation",
        "acceptance_eligible": False,
        "required_operational_stage": (
            "trusted_store_extractor_and_predeclaration_verification"
        ),
        **derived,
        "method": METHOD,
        "interpretation": (
            "empirical_search_center_including_satellite_doppler_not_intrinsic_lnb_error"
        ),
    }
    evidence = FrequencyCalibrationEvidenceV1(
        evidence_digest=canonical_digest(_jsonable(values)),
        **values,
    )
    if evidence.status == "insufficient":
        return FrequencyCalibrationGenerationV1(
            evidence=evidence,
            draft_estimate=None,
            calibration=None,
            calibration_set=None,
        )
    return FrequencyCalibrationGenerationV1(
        evidence=evidence,
        draft_estimate=_build_draft_estimate(evidence),
        calibration=None,
        calibration_set=None,
    )


def _derive(
    plan: FrequencyCalibrationPlanV1,
    dwells: tuple[FrequencyCalibrationDwellV1, ...],
) -> dict[str, Any]:
    if tuple(d.capture.manifest.session_id for d in dwells) != plan.scheduled_session_ids:
        raise ValueError("dwells must match every predeclared session in order")
    if tuple(d.scheduled_index for d in dwells) != tuple(range(len(dwells))):
        raise ValueError("scheduled indexes must be contiguous")
    uris = [d.capture.recording_uri for d in dwells]
    streams = [d.capture.stream_id for d in dwells]
    manifests = [d.capture.manifest_digest for d in dwells]
    observations = [o.observation_id for d in dwells for o in d.extraction.observations]
    if any(len(set(values)) != len(values) for values in (uris, streams, manifests, observations)):
        raise ValueError("campaign URIs, streams, manifests, and observations must be unique")

    previous_end = -1
    for dwell in dwells:
        capture, extraction = dwell.capture, dwell.extraction
        stream = capture.manifest.streams[0]
        if (
            capture.manifest.session_id not in plan.scheduled_session_ids
            or stream.radio.radio_id != plan.radio_id
            or stream.radio.serial != plan.radio_serial
            or capture.physical_receiver_id != plan.physical_receiver_id
            or capture.hardware_epoch_id != plan.hardware_epoch_id
            or capture.topology_evidence_digest != plan.topology_evidence_digest
            or extraction.git_revision != plan.extractor_git_revision
            or extraction.source_tree_digest != plan.extractor_source_tree_digest
            or extraction.executable_digest != plan.extractor_executable_digest
        ):
            raise ValueError("calibration evidence does not match frozen plan identity")
        start, end = capture.interval_bounds()
        if start <= plan.declared_utc_ns:
            raise ValueError("plan must predate all calibration captures")
        if start <= previous_end:
            raise ValueError("calibration timing uncertainty intervals must not overlap")
        previous_end = end

    candidates_by_session: list[tuple[float, ...]] = []
    for dwell in dwells:
        candidates: list[float] = []
        for observation in dwell.extraction.observations:
            if observation.decision == "candidate":
                assert observation.candidate_offset_hz is not None
                candidates.append(observation.candidate_offset_hz)
        candidates_by_session.append(tuple(candidates))
    statistics_rows: list[FrequencyCalibrationSessionStatisticsV1] = []
    usable: list[tuple[str, tuple[float, ...], float, float]] = []
    for dwell, values in zip(dwells, candidates_by_session, strict=True):
        session_id = dwell.capture.manifest.session_id
        session_center = session_sigma = session_radius = None
        multimodal = False
        enough = len(values) >= MINIMUM_CANDIDATES_PER_SESSION
        if values:
            session_center = float(statistics.median(values))
            session_mad = float(
                statistics.median(abs(value - session_center) for value in values)
            )
            session_sigma = 1.4826 * session_mad
            session_radius = max(abs(value - session_center) for value in values)
            ordered_values = sorted(values)
            multimodal = any(
                right - left > WITHIN_SESSION_MULTIMODAL_GAP_HZ
                for left, right in zip(ordered_values, ordered_values[1:], strict=False)
            )
        session_usable = bool(
            enough
            and session_sigma is not None
            and session_sigma <= WITHIN_SESSION_MAXIMUM_ROBUST_SIGMA_HZ
            and session_radius is not None
            and session_radius <= WITHIN_SESSION_MAXIMUM_RADIUS_HZ
            and not multimodal
        )
        statistics_rows.append(
            FrequencyCalibrationSessionStatisticsV1(
                session_id=session_id,
                candidate_count=len(values),
                center_hz=session_center,
                robust_sigma_hz=session_sigma,
                radius_hz=session_radius,
                multimodal=multimodal,
                usable=session_usable,
            )
        )
        if session_usable:
            assert session_center is not None and session_radius is not None
            usable.append((session_id, values, session_center, session_radius))
    total_candidates = sum(len(values) for values in candidates_by_session)
    reasons: list[str] = []
    if total_candidates < MINIMUM_USABLE_CANDIDATES:
        reasons.append("minimum_usable_candidates_not_met")
    if len(usable) < MINIMUM_USABLE_SESSIONS:
        reasons.append("minimum_distinct_usable_sessions_not_met")
    if any(row.multimodal for row in statistics_rows):
        reasons.append("within_session_multimodal_candidate_evidence")
    if any(
        row.robust_sigma_hz is not None
        and row.robust_sigma_hz > WITHIN_SESSION_MAXIMUM_ROBUST_SIGMA_HZ
        for row in statistics_rows
    ):
        reasons.append("within_session_robust_dispersion_exceeds_limit")
    if any(
        row.radius_hz is not None and row.radius_hz > WITHIN_SESSION_MAXIMUM_RADIUS_HZ
        for row in statistics_rows
    ):
        reasons.append("within_session_radius_exceeds_limit")

    session_centers = tuple(item[2] for item in usable)
    inliers: list[tuple[str, tuple[float, ...], float, float]] = []
    center = sigma = lower = upper = sampled_margin = residual_margin = None
    if session_centers:
        initial = float(statistics.median(session_centers))
        mad = float(statistics.median(abs(value - initial) for value in session_centers))
        sigma = 1.4826 * mad
        threshold = max(
            SESSION_CENTER_MINIMUM_OUTLIER_THRESHOLD_HZ,
            SESSION_CENTER_MAD_OUTLIER_MULTIPLIER * sigma,
        )
        inliers = [item for item in usable if abs(item[2] - initial) <= threshold]
        if len(inliers) < MINIMUM_USABLE_SESSIONS:
            reasons.append("minimum_distinct_inlier_sessions_not_met")
        if sigma > SESSION_CENTER_MAXIMUM_ROBUST_SIGMA_HZ:
            reasons.append("session_center_robust_dispersion_exceeds_limit")
        ordered = sorted(session_centers)
        if any(
            right - left > SESSION_CENTER_MULTIMODAL_GAP_HZ
            for left, right in zip(ordered, ordered[1:], strict=False)
        ):
            reasons.append("multimodal_session_evidence")
        if inliers:
            inlier_centers = [item[2] for item in inliers]
            center = float(statistics.median(inlier_centers))
            between_session_radius = max(abs(value - center) for value in inlier_centers)
            within_session_radius = max(item[3] for item in inliers)
            uncertainty = (
                between_session_radius + within_session_radius + MEASUREMENT_ALLOWANCE_HZ
            )
            lower, upper = center - uncertainty, center + uncertainty
            if uncertainty > MAXIMUM_UNCERTAINTY_HZ:
                reasons.append("calibration_uncertainty_exceeds_limit")
            usable_half_band = min(SAMPLE_RATE_HZ, BANDWIDTH_HZ) / 2
            sampled_margin = (
                usable_half_band
                - PILOT_OCCUPIED_HALF_WIDTH_HZ
                - EDGE_FILTER_GUARD_HZ
                - abs(center)
                - uncertainty
                - SATELLITE_DOPPLER_GUARD_HZ
            )
            residual_margin = (
                RESIDUAL_SEARCH_HALF_WIDTH_HZ
                - uncertainty
                - SATELLITE_DOPPLER_GUARD_HZ
            )
            if sampled_margin <= 0:
                reasons.append(
                    "sampled_band_does_not_cover_pilot_uncertainty_and_doppler_guard"
                )
            if residual_margin <= 0:
                reasons.append("residual_search_does_not_cover_uncertainty_and_doppler_guard")

    status = "insufficient" if reasons else "sufficient"
    valid_from = max(d.capture.interval_bounds()[1] for d in dwells) + 1 if dwells else None
    return {
        "status": status,
        "reasons": tuple(dict.fromkeys(reasons)),
        "usable_candidate_count": total_candidates,
        "usable_session_count": len(usable),
        "inlier_candidate_count": sum(len(item[1]) for item in inliers),
        "inlier_session_count": len(inliers),
        "rejected_session_center_outlier_count": len(usable) - len(inliers),
        "session_statistics": tuple(row.model_dump(mode="python") for row in statistics_rows),
        "session_centers_hz": session_centers,
        "inlier_session_ids": tuple(item[0] for item in inliers),
        "empirical_center_hz": center,
        "session_center_robust_sigma_hz": sigma,
        "uncertainty_lower_hz": lower,
        "uncertainty_upper_hz": upper,
        "sampled_band_margin_hz": sampled_margin,
        "residual_search_margin_hz": residual_margin,
        "valid_from_utc_ns": valid_from,
    }


def _build_draft_estimate(
    evidence: FrequencyCalibrationEvidenceV1,
) -> FrequencyCalibrationDraftEstimateV1:
    assert evidence.empirical_center_hz is not None
    assert evidence.uncertainty_lower_hz is not None
    assert evidence.uncertainty_upper_hz is not None
    assert evidence.valid_from_utc_ns is not None
    plan = evidence.plan
    values: dict[str, Any] = {
        "schema_version": 1,
        "trust_status": "unverified_foundation",
        "acceptance_eligible": False,
        "proposed_calibration_id": evidence.output_calibration_id,
        "proposed_calibration_set_id": evidence.output_calibration_set_id,
        "radio_id": plan.radio_id,
        "radio_serial": plan.radio_serial,
        "receiver_id": 1,
        "physical_receiver_id": plan.physical_receiver_id,
        "hardware_epoch_id": plan.hardware_epoch_id,
        "center_hz": evidence.empirical_center_hz,
        "uncertainty_lower_hz": evidence.uncertainty_lower_hz,
        "uncertainty_upper_hz": evidence.uncertainty_upper_hz,
        "proposed_valid_from_utc_ns": evidence.valid_from_utc_ns,
        "proposed_valid_until_utc_ns": evidence.output_valid_until_utc_ns,
        "method": METHOD,
        "evidence_uri": plan.evidence_uri,
        "evidence_digest": evidence.evidence_digest,
        "required_promoter": "trusted_store_extractor_and_predeclaration_verification",
    }
    return FrequencyCalibrationDraftEstimateV1(
        draft_digest=canonical_digest(values),
        **values,
    )


def _create_digested(cls: type[Any], digest_field: str, values: dict[str, Any]) -> Any:
    document: dict[str, Any] = {"schema_version": 1, **values}
    candidate = cls.model_construct(**{digest_field: "sha256:" + "0" * 64}, **document)
    normalized = candidate.model_dump(mode="json", exclude={digest_field})
    return cls(**{digest_field: canonical_digest(normalized)}, **normalized)


def _digest_without(value: ContractModel, field: str) -> str:
    return canonical_digest(value.model_dump(mode="json", exclude={field}))


def _jsonable(value: object) -> Any:
    if isinstance(value, ContractModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value
