from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.contracts.calibration import (
    ReceiverFrequencyCalibrationSetV1,
    ReceiverFrequencyCalibrationV1,
)
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.radio import RadioIdentityV1, RadioSettingsV1, ReceiverGainV1
from leo.contracts.recording import (
    CompressionSettingsV1,
    ContinuitySummaryV1,
    HostIdentityV1,
    ProducerV1,
    RecordingChunkV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.profiles import compile_capture_plan, load_profile_revision
from leo.qualification.frequency_calibration import (
    BANDWIDTH_HZ,
    EXTRACTOR_CONFIG_DIGEST,
    EXTRACTOR_IMPLEMENTATION,
    GAIN_DB,
    IF_CENTER_HZ,
    SAMPLE_COUNT,
    SAMPLE_RATE_HZ,
    TEMPLATE_DIGEST,
    WINDOW_COUNT,
    CalibrationCaptureEnvelopeV1,
    CalibrationExtractorReceiptV1,
    CalibrationWindowObservationV1,
    FrequencyCalibrationDwellV1,
    FrequencyCalibrationEvidenceV1,
    FrequencyCalibrationGenerationV1,
    FrequencyCalibrationPlanV1,
    generate_frequency_calibration,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
SOURCE_REVISION = "0123456789abcdef0123456789abcdef01234567"
SOURCE_TREE_DIGEST = "sha256:" + "c" * 64
EXECUTABLE_DIGEST = "sha256:" + "d" * 64
RADIO_ID = "radio_pluto_19f2"
RADIO_SERIAL = "10400056f695001322002d0010ad1719f2"
HARDWARE_EPOCH = "hw_gauss_r21_science_postreboot_20260816_v1"
TOPOLOGY_DIGEST = (
    "sha256:eb69aef0b2211b3073d125da66f29ec2154e06a4a52916c2d0a036e8f17efef7"
)


def _plan() -> FrequencyCalibrationPlanV1:
    return FrequencyCalibrationPlanV1.create(
        plan_id="wp11-radio-a-rx1",
        declared_utc_ns=100,
        radio_id=RADIO_ID,
        radio_serial=RADIO_SERIAL,
        physical_receiver_id="rx_lnb_d",
        hardware_epoch_id=HARDWARE_EPOCH,
        topology_evidence_digest=TOPOLOGY_DIGEST,
        scheduled_session_ids=("cal-a-1", "cal-a-2", "cal-a-3"),
        extractor_git_revision=SOURCE_REVISION,
        extractor_source_tree_digest=SOURCE_TREE_DIGEST,
        extractor_executable_digest=EXECUTABLE_DIGEST,
        evidence_uri="qualification://frequency-calibration/wp11-radio-a-rx1/evidence.json",
    )


def _manifest(index: int) -> RecordingManifestV1:
    revision = load_profile_revision(
        Path(__file__).parents[2]
        / "profiles"
        / "starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml"
    )
    plan = compile_capture_plan(revision, [RADIO_ID], source_type=SourceType.LIVE)
    settings = RadioSettingsV1(
        center_frequency_hz=IF_CENTER_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=BANDWIDTH_HZ,
        receiver_ids=(1,),
        gain_mode=GainMode.MANUAL,
        gains=(ReceiverGainV1(receiver_id=1, gain_db=GAIN_DB),),
    )
    first = 1_000_000_000_000 + index * 70_000_000_000
    last = first + (SAMPLE_COUNT - 1) * 1_000_000_000 // SAMPLE_RATE_HZ
    stream_id = f"cal-stream-{index}"
    stream = RecordingStreamV1(
        stream_id=stream_id,
        radio=RadioIdentityV1(
            radio_id=RADIO_ID,
            serial=RADIO_SERIAL,
            uri="ip:192.0.2.10",
            transport=RadioTransport.IIO_IP,
        ),
        requested_settings=settings,
        applied_settings=settings,
        state=StreamState.COMPLETE,
        requested_sample_count=SAMPLE_COUNT,
        captured_sample_count=SAMPLE_COUNT,
        timing=StreamTimingV1(
            first_sample=TimingEstimateV1(
                estimate_utc_ns=first,
                earliest_utc_ns=first - 10,
                latest_utc_ns=first + 10,
                method=TimingMethod.HOST_BRACKET,
            ),
            last_sample=TimingEstimateV1(
                estimate_utc_ns=last,
                earliest_utc_ns=last - 10,
                latest_utc_ns=last + 10,
                method=TimingMethod.HOST_BRACKET,
            ),
        ),
        chunks=(
            RecordingChunkV1(
                chunk_index=0,
                relative_path=f"radio-a/iq-{index}.ci16.zst",
                sample_start=0,
                sample_count=SAMPLE_COUNT,
                uncompressed_bytes=SAMPLE_COUNT * 4,
                compressed_bytes=100,
                uncompressed_sha256=DIGEST_A,
                compressed_sha256=DIGEST_B,
            ),
        ),
        continuity=ContinuitySummaryV1(refill_count=1, segment_count=1),
    )
    return RecordingManifestV1(
        session_id=f"cal-a-{index + 1}",
        state=CaptureState.COMMITTED,
        source_type=SourceType.LIVE,
        created_utc_ns=first - 1_000,
        finalized_utc_ns=last + 1_000,
        capture_plan=plan,
        tags=("CALIBRATION", "LIVE"),
        streams=(stream,),
        synchronization=SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.BEST_EFFORT,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=(stream_id,),
        ),
        compression=CompressionSettingsV1(policy_id="zstd-128m-v1"),
        host=HostIdentityV1(hostname="calibration-host"),
        producer=ProducerV1(name="leo", version="0.1.0", source_revision=SOURCE_REVISION),
    )


def _observations(
    index: int,
    offsets: tuple[float, ...],
) -> tuple[CalibrationWindowObservationV1, ...]:
    return tuple(
        CalibrationWindowObservationV1(
            observation_id=f"cal-{index}-window-{window:03d}",
            window_index=window,
            sample_start=window * 250_000,
            decision="candidate" if window < len(offsets) else "no_candidate",
            candidate_score=9.0 if window < len(offsets) else 1.0,
            candidate_offset_hz=offsets[window] if window < len(offsets) else None,
        )
        for window in range(WINDOW_COUNT)
    )


def _dwell(index: int, offsets: tuple[float, ...]) -> FrequencyCalibrationDwellV1:
    manifest = _manifest(index)
    manifest_digest = sha256_digest(canonical_json_bytes(manifest.model_dump(mode="json")))
    created = datetime.fromtimestamp(manifest.created_utc_ns // 1_000_000_000, tz=UTC)
    uri = (
        f"bulk://recordings/{created.year:04d}/{created.month:02d}/{created.day:02d}/"
        f"{manifest.session_id}"
    )
    capture = CalibrationCaptureEnvelopeV1.create(
        recording_uri=uri,
        manifest_digest=manifest_digest,
        manifest=manifest,
        stream_id=manifest.streams[0].stream_id,
        physical_receiver_id="rx_lnb_d",
        hardware_epoch_id=HARDWARE_EPOCH,
        topology_evidence_digest=TOPOLOGY_DIGEST,
    )
    extraction = CalibrationExtractorReceiptV1.create(
        envelope_digest=capture.envelope_digest,
        recording_uri=uri,
        manifest_digest=manifest_digest,
        session_id=manifest.session_id,
        stream_id=manifest.streams[0].stream_id,
        radio_id=RADIO_ID,
        radio_serial=RADIO_SERIAL,
        physical_receiver_id="rx_lnb_d",
        hardware_epoch_id=HARDWARE_EPOCH,
        extractor_implementation=EXTRACTOR_IMPLEMENTATION,
        extractor_config_digest=EXTRACTOR_CONFIG_DIGEST,
        template_digest=TEMPLATE_DIGEST,
        git_revision=SOURCE_REVISION,
        source_tree_digest=SOURCE_TREE_DIGEST,
        executable_digest=EXECUTABLE_DIGEST,
        observations=_observations(index, offsets),
    )
    return FrequencyCalibrationDwellV1(
        scheduled_index=index,
        capture=capture,
        extraction=extraction,
    )


def _good_dwells(center: float = 0.0) -> tuple[FrequencyCalibrationDwellV1, ...]:
    return tuple(
        _dwell(index, (center - 100 + index * 10, center + index * 10, center + 100 + index * 10))
        for index in range(3)
    )


def _generate(dwells: tuple[FrequencyCalibrationDwellV1, ...]) -> FrequencyCalibrationGenerationV1:
    return generate_frequency_calibration(
        plan=_plan(),
        dwells=dwells,
        calibration_id="cal-radio-a-rx1-epoch-a",
        calibration_set_id="cal-set-epoch-a",
        created_utc_ns=2_000_000_000_000,
    )


def test_sealed_campaign_replays_exact_output_and_equal_session_estimator() -> None:
    result = _generate(_good_dwells())

    assert result.evidence.status == "sufficient"
    assert result.evidence.trust_status == "unverified_foundation"
    assert not result.evidence.acceptance_eligible
    assert result.trust_status == "unverified_foundation"
    assert not result.acceptance_eligible
    assert result.evidence.usable_candidate_count == 9
    assert result.evidence.session_centers_hz == (0.0, 10.0, 20.0)
    assert result.evidence.empirical_center_hz == 10.0
    assert result.evidence.inlier_session_ids == ("cal-a-1", "cal-a-2", "cal-a-3")
    assert result.calibration is not None
    assert result.calibration.center_hz == 10.0
    assert result.calibration.evidence[0].uri == _plan().evidence_uri
    assert result.calibration.evidence[0].digest == result.evidence.evidence_digest
    assert result.calibration.valid_from_utc_ns == result.evidence.valid_from_utc_ns
    assert result.calibration_set is not None


def test_historical_d_chain_boundary_is_fail_closed_at_centered_tune() -> None:
    center = 4_201.5
    passing = _generate(
        (
            _dwell(0, (center - 7_798.4,) * 3),
            _dwell(1, (center,) * 3),
            _dwell(2, (center + 7_798.4,) * 3),
        )
    )
    zero_margin = _generate(
        (
            _dwell(0, (center - 7_798.5,) * 3),
            _dwell(1, (center,) * 3),
            _dwell(2, (center + 7_798.5,) * 3),
        )
    )
    negative_margin = _generate(
        (
            _dwell(0, (center - 7_799.5,) * 3),
            _dwell(1, (center,) * 3),
            _dwell(2, (center + 7_799.5,) * 3),
        )
    )

    assert passing.evidence.status == "sufficient"
    assert passing.evidence.sampled_band_margin_hz == pytest.approx(0.1)
    assert zero_margin.evidence.status == "insufficient"
    assert zero_margin.evidence.sampled_band_margin_hz == 0.0
    assert negative_margin.evidence.status == "insufficient"
    assert negative_margin.evidence.sampled_band_margin_hz == -1.0


def test_extreme_within_session_candidates_are_insufficient() -> None:
    adversarial = _generate(
        tuple(_dwell(index, (-1_200_000.0, 0.0, 1_200_000.0)) for index in range(3))
    )

    assert adversarial.evidence.status == "insufficient"
    assert "within_session_multimodal_candidate_evidence" in adversarial.evidence.reasons
    assert "within_session_robust_dispersion_exceeds_limit" in adversarial.evidence.reasons
    assert "within_session_radius_exceeds_limit" in adversarial.evidence.reasons
    assert adversarial.calibration is None


def test_timing_uses_feasible_delta_interval_not_summed_widths() -> None:
    original = _manifest(0)
    document = original.model_dump(mode="python")
    timing = document["streams"][0]["timing"]
    first = timing["first_sample"]
    last = timing["last_sample"]
    first_estimate = first["estimate_utc_ns"]
    last_estimate = last["estimate_utc_ns"]
    first.update(earliest_utc_ns=first_estimate - 100, latest_utc_ns=first_estimate + 100)
    last.update(
        estimate_utc_ns=last_estimate + 200,
        earliest_utc_ns=last_estimate + 150,
        latest_utc_ns=last_estimate + 250,
    )
    manifest = RecordingManifestV1.model_validate(document)
    digest = sha256_digest(canonical_json_bytes(manifest.model_dump(mode="json")))
    created = datetime.fromtimestamp(manifest.created_utc_ns // 1_000_000_000, tz=UTC)
    uri = (
        f"bulk://recordings/{created.year:04d}/{created.month:02d}/{created.day:02d}/"
        f"{manifest.session_id}"
    )
    with pytest.raises(ValidationError, match="exact N/Fs"):
        CalibrationCaptureEnvelopeV1.create(
            recording_uri=uri,
            manifest_digest=digest,
            manifest=manifest,
            stream_id=manifest.streams[0].stream_id,
            physical_receiver_id="rx_lnb_d",
            hardware_epoch_id=HARDWARE_EPOCH,
            topology_evidence_digest=TOPOLOGY_DIGEST,
        )


def test_weak_or_multimodal_evidence_emits_no_fallback() -> None:
    weak = _generate(tuple(_dwell(index, (float(index),)) for index in range(3)))
    multi = _generate(
        (
            _dwell(0, (-50_000.0, -50_000.0, -50_000.0)),
            _dwell(1, (50_000.0, 50_000.0, 50_000.0)),
            _dwell(2, (50_100.0, 50_100.0, 50_100.0)),
        )
    )
    assert weak.evidence.status == "insufficient"
    assert weak.calibration is None
    assert "minimum_usable_candidates_not_met" in weak.evidence.reasons
    assert multi.evidence.status == "insufficient"
    assert "multimodal_session_evidence" in multi.evidence.reasons


def test_redigested_derived_mutation_is_rejected_by_pure_replay() -> None:
    evidence = _generate(_good_dwells()).evidence
    document = evidence.model_dump(mode="json")
    document["empirical_center_hz"] = 999.0
    document["evidence_digest"] = canonical_digest(
        {key: value for key, value in document.items() if key != "evidence_digest"}
    )
    with pytest.raises(ValidationError, match="does not replay"):
        FrequencyCalibrationEvidenceV1.model_validate(document)


def test_redigested_manifest_or_extractor_mutation_is_rejected() -> None:
    dwell = _good_dwells()[0]
    capture = dwell.capture.model_dump(mode="json")
    capture["manifest"]["host"]["hostname"] = "mutated"
    capture["envelope_digest"] = canonical_digest(
        {key: value for key, value in capture.items() if key != "envelope_digest"}
    )
    with pytest.raises(ValidationError, match="manifest digest"):
        CalibrationCaptureEnvelopeV1.model_validate(capture)

    receipt = dwell.extraction.model_dump(mode="json")
    receipt["observations"][0]["candidate_score"] = 0.0
    receipt["receipt_digest"] = canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    with pytest.raises(ValidationError, match="decision does not replay"):
        CalibrationExtractorReceiptV1.model_validate(receipt)


def test_unrelated_valid_calibration_and_set_are_rejected() -> None:
    result = _generate(_good_dwells())
    assert result.calibration is not None
    values = result.calibration.model_dump(
        mode="python",
        exclude={"schema_version", "calibration_digest"},
    )
    values["evidence"] = result.calibration.evidence
    unrelated = ReceiverFrequencyCalibrationV1.create(**{**values, "calibration_id": "unrelated"})
    unrelated_set = ReceiverFrequencyCalibrationSetV1.create(
        calibration_set_id=result.evidence.output_calibration_set_id,
        calibrations=(unrelated,),
    )
    with pytest.raises(ValidationError, match="does not replay"):
        FrequencyCalibrationGenerationV1(
            evidence=result.evidence,
            calibration=unrelated,
            calibration_set=unrelated_set,
        )


def test_arbitrary_relaxed_plan_and_noncanonical_uri_are_rejected() -> None:
    plan = _plan().model_dump(mode="python")
    plan["minimum_satellite_doppler_guard_hz"] = 250_000.0
    plan["plan_digest"] = canonical_digest(
        {key: value for key, value in plan.items() if key != "plan_digest"}
    )
    with pytest.raises(ValidationError):
        FrequencyCalibrationPlanV1.model_validate(plan)

    capture = _good_dwells()[0].capture.model_dump(mode="json")
    capture["recording_uri"] = "bulk://recordings/2026/8/19/cal-a-1"
    capture["envelope_digest"] = canonical_digest(
        {key: value for key, value in capture.items() if key != "envelope_digest"}
    )
    with pytest.raises(ValidationError, match="date is not canonical"):
        CalibrationCaptureEnvelopeV1.model_validate(capture)
