"""Replayable, fail-closed generation of WP11 empirical acquisition centers."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from urllib.parse import quote

from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.calibration import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
)
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
MAD_OUTLIER_MULTIPLIER = 4.5
MINIMUM_OUTLIER_THRESHOLD_HZ = 10_000.0
MAXIMUM_ROBUST_SIGMA_HZ = 100_000.0
MULTIMODAL_GAP_HZ = 75_000.0
METHOD = "equal_session_median_mad_empirical_pilot_acquisition_center_v2"
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
    extractor_source_revision: SafeIdentifier
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
    mad_outlier_multiplier: float = MAD_OUTLIER_MULTIPLIER
    minimum_outlier_threshold_hz: float = MINIMUM_OUTLIER_THRESHOLD_HZ
    maximum_robust_sigma_hz: float = MAXIMUM_ROBUST_SIGMA_HZ
    multimodal_gap_hz: float = MULTIMODAL_GAP_HZ
    candidate_measurement_uncertainty_hz: float = MEASUREMENT_ALLOWANCE_HZ
    maximum_calibration_uncertainty_hz: float = MAXIMUM_UNCERTAINTY_HZ
    pilot_occupied_half_width_hz: float = PILOT_OCCUPIED_HALF_WIDTH_HZ
    residual_search_half_width_hz: float = RESIDUAL_SEARCH_HALF_WIDTH_HZ
    minimum_satellite_doppler_guard_hz: float = SATELLITE_DOPPLER_GUARD_HZ
    edge_filter_guard_hz: float = EDGE_FILTER_GUARD_HZ
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
            "mad_outlier_multiplier": MAD_OUTLIER_MULTIPLIER,
            "minimum_outlier_threshold_hz": MINIMUM_OUTLIER_THRESHOLD_HZ,
            "maximum_robust_sigma_hz": MAXIMUM_ROBUST_SIGMA_HZ,
            "multimodal_gap_hz": MULTIMODAL_GAP_HZ,
            "candidate_measurement_uncertainty_hz": MEASUREMENT_ALLOWANCE_HZ,
            "maximum_calibration_uncertainty_hz": MAXIMUM_UNCERTAINTY_HZ,
            "pilot_occupied_half_width_hz": PILOT_OCCUPIED_HALF_WIDTH_HZ,
            "residual_search_half_width_hz": RESIDUAL_SEARCH_HALF_WIDTH_HZ,
            "minimum_satellite_doppler_guard_hz": SATELLITE_DOPPLER_GUARD_HZ,
            "edge_filter_guard_hz": EDGE_FILTER_GUARD_HZ,
        }
        actual = self.model_dump(mode="python", include=set(frozen))
        if actual != frozen:
            raise ValueError("WP11 calibration geometry and thresholds are frozen")
        if len(self.scheduled_session_ids) < MINIMUM_USABLE_SESSIONS:
            raise ValueError("at least three calibration sessions must be predeclared")
        if self.receiver_ids != (1,):
            raise ValueError("frequency calibration requires exactly RX1")
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
        expected_delta = (SAMPLE_COUNT - 1) * 1_000_000_000 // SAMPLE_RATE_HZ
        timing_uncertainty = (first.latest_utc_ns - first.earliest_utc_ns) + (
            last.latest_utc_ns - last.earliest_utc_ns
        )
        observed_delta = last.estimate_utc_ns - first.estimate_utc_ns
        if abs(observed_delta - expected_delta) > timing_uncertainty:
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
    source_revision: SafeIdentifier
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
    status: Literal["sufficient", "insufficient"]
    reasons: tuple[str, ...]
    usable_candidate_count: Annotated[int, Field(ge=0)]
    usable_session_count: Annotated[int, Field(ge=0)]
    inlier_candidate_count: Annotated[int, Field(ge=0)]
    inlier_session_count: Annotated[int, Field(ge=0)]
    rejected_outlier_count: Annotated[int, Field(ge=0)]
    session_centers_hz: tuple[float, ...]
    inlier_session_ids: tuple[SafeIdentifier, ...]
    empirical_center_hz: float | None
    robust_sigma_hz: float | None
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


class FrequencyCalibrationGenerationV1(ContractModel):
    schema_version: Literal[1] = 1
    evidence: FrequencyCalibrationEvidenceV1
    calibration: ReceiverFrequencyCalibrationV1 | None
    calibration_set: ReceiverFrequencyCalibrationSetV1 | None

    @model_validator(mode="after")
    def _replay_exact_outputs(self) -> Self:
        if self.evidence.status == "insufficient":
            if self.calibration is not None or self.calibration_set is not None:
                raise ValueError("insufficient evidence cannot emit calibration output")
            return self
        expected = _build_calibration(self.evidence)
        if self.calibration != expected:
            raise ValueError("calibration output does not replay from evidence")
        expected_set = ReceiverFrequencyCalibrationSetV1.create(
            calibration_set_id=self.evidence.output_calibration_set_id,
            calibrations=(expected,),
        )
        if self.calibration_set != expected_set:
            raise ValueError("calibration-set output does not replay from evidence")
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
            calibration=None,
            calibration_set=None,
        )
    calibration = _build_calibration(evidence)
    return FrequencyCalibrationGenerationV1(
        evidence=evidence,
        calibration=calibration,
        calibration_set=ReceiverFrequencyCalibrationSetV1.create(
            calibration_set_id=calibration_set_id,
            calibrations=(calibration,),
        ),
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
            or extraction.source_revision != plan.extractor_source_revision
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
    usable = [
        (d.capture.manifest.session_id, values, float(statistics.median(values)))
        for d, values in zip(dwells, candidates_by_session, strict=True)
        if len(values) >= MINIMUM_CANDIDATES_PER_SESSION
    ]
    total_candidates = sum(len(values) for values in candidates_by_session)
    reasons: list[str] = []
    if total_candidates < MINIMUM_USABLE_CANDIDATES:
        reasons.append("minimum_usable_candidates_not_met")
    if len(usable) < MINIMUM_USABLE_SESSIONS:
        reasons.append("minimum_distinct_usable_sessions_not_met")

    session_centers = tuple(item[2] for item in usable)
    inliers: list[tuple[str, tuple[float, ...], float]] = []
    center = sigma = lower = upper = sampled_margin = residual_margin = None
    if session_centers:
        initial = float(statistics.median(session_centers))
        mad = float(statistics.median(abs(value - initial) for value in session_centers))
        sigma = 1.4826 * mad
        threshold = max(MINIMUM_OUTLIER_THRESHOLD_HZ, MAD_OUTLIER_MULTIPLIER * sigma)
        inliers = [item for item in usable if abs(item[2] - initial) <= threshold]
        if len(inliers) < MINIMUM_USABLE_SESSIONS:
            reasons.append("minimum_distinct_inlier_sessions_not_met")
        if sigma > MAXIMUM_ROBUST_SIGMA_HZ:
            reasons.append("robust_dispersion_exceeds_limit")
        ordered = sorted(session_centers)
        if any(
            right - left > MULTIMODAL_GAP_HZ
            for left, right in zip(ordered, ordered[1:], strict=False)
        ):
            reasons.append("multimodal_session_evidence")
        if inliers:
            inlier_centers = [item[2] for item in inliers]
            center = float(statistics.median(inlier_centers))
            uncertainty = max(abs(value - center) for value in inlier_centers) + (
                MEASUREMENT_ALLOWANCE_HZ
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
            if sampled_margin < 0:
                reasons.append(
                    "sampled_band_does_not_cover_pilot_uncertainty_and_doppler_guard"
                )
            if residual_margin < 0:
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
        "rejected_outlier_count": len(usable) - len(inliers),
        "session_centers_hz": session_centers,
        "inlier_session_ids": tuple(item[0] for item in inliers),
        "empirical_center_hz": center,
        "robust_sigma_hz": sigma,
        "uncertainty_lower_hz": lower,
        "uncertainty_upper_hz": upper,
        "sampled_band_margin_hz": sampled_margin,
        "residual_search_margin_hz": residual_margin,
        "valid_from_utc_ns": valid_from,
    }


def _build_calibration(evidence: FrequencyCalibrationEvidenceV1) -> ReceiverFrequencyCalibrationV1:
    assert evidence.empirical_center_hz is not None
    assert evidence.uncertainty_lower_hz is not None
    assert evidence.uncertainty_upper_hz is not None
    assert evidence.valid_from_utc_ns is not None
    plan = evidence.plan
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=evidence.output_calibration_id,
        radio_id=plan.radio_id,
        radio_serial=plan.radio_serial,
        receiver_id=1,
        physical_receiver_id=plan.physical_receiver_id,
        hardware_epoch_id=plan.hardware_epoch_id,
        center_hz=evidence.empirical_center_hz,
        uncertainty_lower_hz=evidence.uncertainty_lower_hz,
        uncertainty_upper_hz=evidence.uncertainty_upper_hz,
        valid_from_utc_ns=evidence.valid_from_utc_ns,
        valid_until_utc_ns=evidence.output_valid_until_utc_ns,
        method=METHOD,
        created_utc_ns=evidence.output_created_utc_ns,
        evidence=(
            CalibrationEvidenceV1(
                kind="frequency_calibration_campaign_v1",
                uri=plan.evidence_uri,
                digest=evidence.evidence_digest,
                source_revision=plan.extractor_source_revision,
            ),
        ),
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
