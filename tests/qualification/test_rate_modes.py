from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.contracts.digests import canonical_digest
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.recording import (
    DEVICE_AXIS_STORAGE_POLICY_V1,
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV2,
    RecordingManifestV3,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityPolicy,
    GainMode,
    PeerFailurePolicy,
    SourceType,
)
from leo.domain.profiles import compile_capture_plan
from leo.qualification.rate_modes import (
    ContiguousRateDeviceAxisCharacterizationStreamV1,
    ContiguousRateDeviceAxisCharacterizationV1,
    ContiguousRateNativeIpCanaryEvidenceV1,
    ContiguousRatePrerequisitesV1,
    ContiguousRatePrerequisitesV2,
    ContiguousRatePrerequisitesV3,
    ContiguousRatePrerequisitesV4,
    ContiguousRateQualificationPolicyV1,
    ContiguousRateQualificationReceiptV1,
    ContiguousRateQualificationReceiptV2,
    ContiguousRateQualificationReceiptV3,
    ContiguousRateQualificationReceiptV4,
    ContiguousRateQualificationTargetV1,
    ContiguousRateQualificationTargetV2,
    ContiguousRateQualificationTargetV3,
    ContiguousRateQualificationTargetV4,
    ContiguousRateRadioMetricsV1,
    ContiguousRateRadioSafetyEvidenceV1,
    ContiguousRateTrialEvidenceV1,
    ContiguousRateTrialEvidenceV2,
    ContiguousRateUsbControlArmEvidenceV1,
    ContiguousRateUsbControlArmEvidenceV2,
    ContiguousRateUsbRadioCaptureIntervalV2,
    ContiguousRateUsbRadioIdentityV2,
    ContiguousRateUsbRadioRestorationEvidenceV2,
    ContiguousRateWriterBenchmarkEvidenceV1,
    contiguous_rate_qualification_target_digest,
    evaluate_contiguous_rate,
    evaluate_device_axis_contiguous_rate,
)
from leo.radio import FakeRadioSource
from leo.storage import RecordingStore

_HOST = HostIdentityV1(
    hostname="rate-qualification-host",
    machine_id="rate-qualification-machine",
    operating_system="test-linux",
)
_PRODUCER = ProducerV1(
    name="leo-acquisition",
    version="test",
    source_revision="1" * 40,
)


def _evidence_digest(label: str) -> str:
    return canonical_digest({"evidence": label})


def _capture(
    tmp_path: Path,
    *,
    sample_rate_hz: int,
    gap_radio_a: bool = False,
) -> tuple[RecordingManifestV2, str]:
    profile = CaptureProfileV2(
        name=f"rate-{sample_rate_hz}-qualification-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=12,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        continuity_policy=ContinuityPolicy.REQUIRE_CONTIGUOUS,
        storage_policy="rate-qualification-zstd-v1",
        tags=("CAPTURE_ONLY", "LIVE"),
        kernel_buffers=8,
        refill_queue_capacity=32,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ("radio-a", "radio-b"),
        source_type=SourceType.LIVE,
    )
    store = RecordingStore(tmp_path / "bulk")
    coordinator = AcquisitionCoordinator(
        store,
        host=_HOST,
        producer=_PRODUCER,
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            "radio-a": FakeRadioSource(
                "radio-a",
                gaps_before_blocks={1: 4} if gap_radio_a else None,
            ),
            "radio-b": FakeRadioSource("radio-b"),
        },
        session_id=f"rate-{sample_rate_hz}-{'gap' if gap_radio_a else 'clean'}",
    )
    assert result.bundle is not None
    assert isinstance(result.manifest, RecordingManifestV2)
    store.verify(result.bundle)
    return result.manifest, result.bundle.manifest_sha256


def _capture_v3(
    tmp_path: Path,
    *,
    gap_radio_a: bool = False,
) -> tuple[RecordingManifestV3, str]:
    profile = CaptureProfileV2(
        name="rate-3000000-device-axis-qualification-test",
        center_frequency_hz=1_700_000_000,
        sample_rate_hz=3_000_000,
        bandwidth_hz=2_500_000,
        receivers=(0, 1),
        gain_mode=GainMode.MANUAL,
        gains=(
            ReceiverGainV1(receiver_id=0, gain_db=30),
            ReceiverGainV1(receiver_id=1, gain_db=30),
        ),
        sample_count=12,
        refill_samples=4,
        settle_seconds=Decimal(0),
        prime_refills=0,
        continuity_policy=ContinuityPolicy.ALLOW_SEGMENTS,
        peer_failure_policy=PeerFailurePolicy.FAIL_SESSION,
        storage_policy=DEVICE_AXIS_STORAGE_POLICY_V1,
        tags=(
            "CAPTURE_ONLY",
            "DEVICE_AXIS_ZERO_FILL",
            "LIVE",
            "RANDOM_TUNING",
            "STANDARD_NATIVE",
        ),
        kernel_buffers=8,
        refill_queue_capacity=32,
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV2.from_profile(profile),
        ("radio-a", "radio-b"),
        source_type=SourceType.LIVE,
    )
    store = RecordingStore(tmp_path / "bulk-v3")
    coordinator = AcquisitionCoordinator(
        store,
        compression=CompressionSettingsV1(
            policy_id=DEVICE_AXIS_STORAGE_POLICY_V1,
            target_uncompressed_bytes=64,
        ),
        host=_HOST,
        producer=_PRODUCER,
        config=AcquisitionConfig(safety_reserve_bytes=0),
        free_bytes=lambda _path: 10**12,
    )
    result = coordinator.capture_once(
        plan,
        {
            "radio-a": FakeRadioSource(
                "radio-a",
                gaps_before_blocks={1: 4} if gap_radio_a else None,
            ),
            "radio-b": FakeRadioSource("radio-b"),
        },
        session_id=f"rate-3000000-device-axis-{'gap' if gap_radio_a else 'clean'}",
    )
    assert result.bundle is not None
    assert isinstance(result.manifest, RecordingManifestV3)
    report = store.verify(result.bundle)
    assert report.validity_inventory_count == 2
    return result.manifest, result.bundle.manifest_sha256


def _target(
    manifest: RecordingManifestV2,
    *,
    required_trial_count: int = 1,
    required_tags: tuple[str, ...] = ("CAPTURE_ONLY",),
    prerequisites: ContiguousRatePrerequisitesV2 | None = None,
) -> ContiguousRateQualificationTargetV2:
    profile = manifest.capture_plan.profile_revision.profile
    return ContiguousRateQualificationTargetV2(
        qualification_id=f"rate-{profile.sample_rate_hz}",
        profile_revision_digest=manifest.capture_plan.profile_revision.revision_digest,
        capture_plan_digest=manifest.capture_plan.plan_digest,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        requested_sample_count=manifest.capture_plan.resolved_sample_count,
        expected_radios=(manifest.streams[0].radio, manifest.streams[1].radio),
        expected_host=_HOST,
        expected_producer=_PRODUCER,
        pluto_plus_utils_revision="2" * 40,
        libiio_version="0.25 / 6305ea1",
        libiio_library_sha256="sha256:" + "3" * 64,
        python_iio_sha256="sha256:" + "4" * 64,
        native_network_interface="enp132s0",
        native_source_address="192.168.1.142",
        prerequisites=prerequisites or _prerequisites(manifest),
        policy=ContiguousRateQualificationPolicyV1(
            required_trial_count=required_trial_count,
            required_tags=required_tags,
        ),
    )


def _radio_metrics(radio_id: str, sample_count: int) -> ContiguousRateRadioMetricsV1:
    return ContiguousRateRadioMetricsV1(
        radio_id=radio_id,
        requested_sample_count=sample_count,
        observed_sample_count=sample_count,
        device_span_sample_count=sample_count,
        observed_gap_count=0,
        observed_missing_sample_count=0,
        observed_overflow_count=0,
        enqueue_failure_count=0,
    )


def _usb_control_radios() -> tuple[
    ContiguousRateUsbRadioIdentityV2,
    ContiguousRateUsbRadioIdentityV2,
]:
    return (
        ContiguousRateUsbRadioIdentityV2(
            radio_id="usb-control-a",
            serial="usb-control-serial-a",
            uri="usb:1.2.3",
            firmware_version="usb-control-firmware-a",
        ),
        ContiguousRateUsbRadioIdentityV2(
            radio_id="usb-control-b",
            serial="usb-control-serial-b",
            uri="usb:4.5.6",
            firmware_version="usb-control-firmware-b",
        ),
    )


def _usb_control_restoration(
    radio_id: str,
) -> ContiguousRateUsbRadioRestorationEvidenceV2:
    return ContiguousRateUsbRadioRestorationEvidenceV2(
        radio_id=radio_id,
        pre_settings_evidence_sha256=_evidence_digest(f"{radio_id}-pre-settings"),
        post_settings_evidence_sha256=_evidence_digest(f"{radio_id}-post-settings"),
        rx_settings_restored=True,
        passed=True,
    )


def _usb_capture_interval(
    radio_id: str,
    *,
    started_monotonic_ns: int,
) -> ContiguousRateUsbRadioCaptureIntervalV2:
    return ContiguousRateUsbRadioCaptureIntervalV2(
        radio_id=radio_id,
        started_monotonic_ns=started_monotonic_ns,
        ended_monotonic_ns=started_monotonic_ns + 60_000_000_000,
    )


def _prerequisites(
    manifest: RecordingManifestV2 | RecordingManifestV3,
) -> ContiguousRatePrerequisitesV2:
    profile = manifest.capture_plan.profile_revision.profile
    radio_ids = (manifest.streams[0].radio.radio_id, manifest.streams[1].radio.radio_id)
    usb_radios = _usb_control_radios()
    canary_metrics = (
        _radio_metrics(radio_ids[0], profile.sample_rate_hz),
        _radio_metrics(radio_ids[1], profile.sample_rate_hz),
    )
    usb_metrics = (
        _radio_metrics(usb_radios[0].radio_id, profile.sample_rate_hz * 60),
        _radio_metrics(usb_radios[1].radio_id, profile.sample_rate_hz * 60),
    )

    def safety(radio_id: str) -> ContiguousRateRadioSafetyEvidenceV1:
        return ContiguousRateRadioSafetyEvidenceV1(
            radio_id=radio_id,
            pre_safety_evidence_sha256=_evidence_digest(f"{radio_id}-pre-safety"),
            post_safety_evidence_sha256=_evidence_digest(f"{radio_id}-post-safety"),
            pre_tx_safe=True,
            post_tx_safe=True,
            rx_settings_restored=True,
            passed=True,
        )

    def canary(
        metrics: ContiguousRateRadioMetricsV1,
    ) -> ContiguousRateNativeIpCanaryEvidenceV1:
        return ContiguousRateNativeIpCanaryEvidenceV1(
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            evidence_sha256=_evidence_digest(f"{metrics.radio_id}-native-ip-canary"),
            metrics=metrics,
            passed=True,
        )

    return ContiguousRatePrerequisitesV2(
        radio_safety=(safety(radio_ids[0]), safety(radio_ids[1])),
        native_ip_canaries=(canary(canary_metrics[0]), canary(canary_metrics[1])),
        usb_control_arm=ContiguousRateUsbControlArmEvidenceV2(
            duration_ns=60_000_000_000,
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            evidence_sha256=_evidence_digest("simultaneous-usb-control"),
            radios=usb_radios,
            capture_intervals=(
                _usb_capture_interval(usb_radios[0].radio_id, started_monotonic_ns=1_000_000),
                _usb_capture_interval(usb_radios[1].radio_id, started_monotonic_ns=2_000_000),
            ),
            radio_restoration=(
                _usb_control_restoration(usb_radios[0].radio_id),
                _usb_control_restoration(usb_radios[1].radio_id),
            ),
            radio_metrics=usb_metrics,
            passed=True,
        ),
        writer_benchmark=ContiguousRateWriterBenchmarkEvidenceV1(
            evidence_sha256=_evidence_digest("incompressible-writer-benchmark"),
            uncompressed_bytes_written=144_000_000,
            elapsed_ns=2_000_000_000,
            sustained_bytes_per_second=72_000_000,
            passed=True,
        ),
    )


def _prerequisites_v3(
    manifest: RecordingManifestV2 | RecordingManifestV3,
) -> ContiguousRatePrerequisitesV3:
    v2 = _prerequisites(manifest)
    return ContiguousRatePrerequisitesV3(
        radio_safety=v2.radio_safety,
        native_ip_canaries=v2.native_ip_canaries,
        writer_benchmark=v2.writer_benchmark,
    )


def _target_v3(
    manifest: RecordingManifestV2,
    *,
    prerequisites: ContiguousRatePrerequisitesV3 | None = None,
    required_trial_count: int = 1,
) -> ContiguousRateQualificationTargetV3:
    v2 = _target(manifest, required_trial_count=required_trial_count)
    return ContiguousRateQualificationTargetV3(
        **v2.model_dump(exclude={"schema_version", "prerequisites"}),
        prerequisites=prerequisites or _prerequisites_v3(manifest),
    )


def _target_v4(
    manifest: RecordingManifestV3,
    *,
    required_trial_count: int = 1,
) -> ContiguousRateQualificationTargetV4:
    profile = manifest.capture_plan.profile_revision.profile
    v3_prerequisites = _prerequisites_v3(manifest)
    characterization = _five_m_characterization(manifest)
    return ContiguousRateQualificationTargetV4(
        qualification_id="rate-3000000-device-axis-v4",
        profile_revision_digest=manifest.capture_plan.profile_revision.revision_digest,
        capture_plan_digest=manifest.capture_plan.plan_digest,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        requested_sample_count=manifest.capture_plan.resolved_sample_count,
        expected_radios=(manifest.streams[0].radio, manifest.streams[1].radio),
        expected_host=_HOST,
        expected_producer=_PRODUCER,
        pluto_plus_utils_revision="2" * 40,
        libiio_version="0.25 / 6305ea1",
        libiio_library_sha256="sha256:" + "3" * 64,
        python_iio_sha256="sha256:" + "4" * 64,
        native_network_interface="enp132s0",
        native_source_address="192.168.1.142",
        prerequisites=ContiguousRatePrerequisitesV4(
            radio_safety=v3_prerequisites.radio_safety,
            native_ip_canaries=v3_prerequisites.native_ip_canaries,
            writer_benchmark=v3_prerequisites.writer_benchmark,
            five_m_characterization=characterization,
        ),
        policy=ContiguousRateQualificationPolicyV1(
            required_trial_count=required_trial_count,
            required_tags=(
                "CAPTURE_ONLY",
                "DEVICE_AXIS_ZERO_FILL",
                "LIVE",
                "RANDOM_TUNING",
                "STANDARD_NATIVE",
            ),
        ),
    )


def _five_m_characterization(
    manifest: RecordingManifestV3,
) -> ContiguousRateDeviceAxisCharacterizationV1:
    stream_checks = tuple(
        ContiguousRateDeviceAxisCharacterizationStreamV1(
            radio_id=stream.radio.radio_id,
            observed_sample_count=300_000_000,
            zero_fill_sample_count=0,
            continuity_segment_count=1,
            gap_count=0,
            missing_sample_count=0,
            overflow_count=0,
            enqueue_failure_count=0,
            terminal_rejected_gap_count=0,
            terminal_rejected_missing_sample_count=0,
            terminal_rejected_overflow_count=0,
            gap_map_segment_count=1,
            gap_map_boundary_count=0,
            validity_segment_count=1,
            observed_iq_sha256=_evidence_digest(f"{stream.radio.radio_id}-5m-iq"),
            logical_iq_sha256=_evidence_digest(f"{stream.radio.radio_id}-5m-iq"),
            timeline_sha256=_evidence_digest(f"{stream.radio.radio_id}-5m-timeline"),
            gap_map_sha256=_evidence_digest(f"{stream.radio.radio_id}-5m-gap-map"),
            validity_inventory_sha256=_evidence_digest(f"{stream.radio.radio_id}-5m-validity"),
        )
        for stream in manifest.streams
    )
    return ContiguousRateDeviceAxisCharacterizationV1(
        evidence_sha256=_evidence_digest("5m-characterization"),
        manifest_sha256=_evidence_digest("5m-manifest"),
        session_id="five-m-characterization",
        profile_revision_digest=_evidence_digest("5m-profile"),
        capture_plan_digest=_evidence_digest("5m-plan"),
        radios=(manifest.streams[0].radio, manifest.streams[1].radio),
        host=manifest.host,
        producer=manifest.producer,
        manifest_state=CaptureState.COMMITTED,
        streams=(stream_checks[0], stream_checks[1]),
        bundle_verified=True,
        physical_zero_verified=True,
        validity_verified=True,
        gap_map_verified=True,
        passed=True,
        errors=(),
    )


def _prerequisites_v1(manifest: RecordingManifestV2) -> ContiguousRatePrerequisitesV1:
    profile = manifest.capture_plan.profile_revision.profile
    v2 = _prerequisites(manifest)
    radio_ids = tuple(item.radio_id for item in v2.radio_safety)
    return ContiguousRatePrerequisitesV1(
        radio_safety=v2.radio_safety,
        native_ip_canaries=v2.native_ip_canaries,
        usb_control_arm=ContiguousRateUsbControlArmEvidenceV1(
            duration_ns=60_000_000_000,
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            evidence_sha256=_evidence_digest("simultaneous-usb-control-v1"),
            radio_metrics=(
                _radio_metrics(radio_ids[0], profile.sample_rate_hz * 60),
                _radio_metrics(radio_ids[1], profile.sample_rate_hz * 60),
            ),
            passed=True,
        ),
        writer_benchmark=v2.writer_benchmark,
    )


def _target_v1(
    manifest: RecordingManifestV2,
    prerequisites: ContiguousRatePrerequisitesV1,
) -> ContiguousRateQualificationTargetV1:
    profile = manifest.capture_plan.profile_revision.profile
    return ContiguousRateQualificationTargetV1(
        qualification_id=f"rate-{profile.sample_rate_hz}-v1",
        profile_revision_digest=manifest.capture_plan.profile_revision.revision_digest,
        capture_plan_digest=manifest.capture_plan.plan_digest,
        sample_rate_hz=profile.sample_rate_hz,
        bandwidth_hz=profile.bandwidth_hz,
        requested_sample_count=manifest.capture_plan.resolved_sample_count,
        expected_radios=(manifest.streams[0].radio, manifest.streams[1].radio),
        expected_host=_HOST,
        expected_producer=_PRODUCER,
        pluto_plus_utils_revision="2" * 40,
        libiio_version="0.25 / 6305ea1",
        libiio_library_sha256="sha256:" + "3" * 64,
        python_iio_sha256="sha256:" + "4" * 64,
        native_network_interface="enp132s0",
        native_source_address="192.168.1.142",
        prerequisites=prerequisites,
        policy=ContiguousRateQualificationPolicyV1(required_trial_count=1),
    )


def _trial(
    manifest: RecordingManifestV2,
    manifest_sha256: str,
    *,
    digest_valid: bool = True,
) -> ContiguousRateTrialEvidenceV1:
    return ContiguousRateTrialEvidenceV1(
        trial_id=f"trial-{manifest.session_id}",
        manifest_sha256=manifest_sha256,
        digest_valid=digest_valid,
        manifest=manifest,
    )


def _trial_v2(
    manifest: RecordingManifestV3,
    manifest_sha256: str,
    *,
    digest_valid: bool = True,
) -> ContiguousRateTrialEvidenceV2:
    return ContiguousRateTrialEvidenceV2(
        trial_id=f"trial-{manifest.session_id}",
        manifest_sha256=manifest_sha256,
        digest_valid=digest_valid,
        manifest=manifest,
    )


@pytest.mark.parametrize("sample_rate_hz", (3_000_000, 5_000_000))
def test_strict_rate_gate_accepts_only_exact_lossless_v2_evidence(
    tmp_path: Path,
    sample_rate_hz: int,
) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=sample_rate_hz)

    receipt = evaluate_contiguous_rate(
        _target(manifest),
        (_trial(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    assert receipt.complete
    assert receipt.passed
    assert isinstance(receipt, ContiguousRateQualificationReceiptV2)
    assert receipt.schema_version == 2
    assert receipt.target.schema_version == 2
    assert receipt.target.prerequisites.schema_version == 2
    assert receipt.target.prerequisites.usb_control_arm.schema_version == 2
    assert receipt.target_digest == contiguous_rate_qualification_target_digest(receipt.target)
    assert all(
        canary.metrics.requested_sample_count == sample_rate_hz
        for canary in receipt.target.prerequisites.native_ip_canaries
    )
    assert all(
        metrics.requested_sample_count == sample_rate_hz * 60
        for metrics in receipt.target.prerequisites.usb_control_arm.radio_metrics
    )
    expected_radio_ids = tuple(radio.radio_id for radio in receipt.target.expected_radios)
    safety_radio_ids = tuple(item.radio_id for item in receipt.target.prerequisites.radio_safety)
    canary_radio_ids = tuple(
        item.metrics.radio_id for item in receipt.target.prerequisites.native_ip_canaries
    )
    usb_radio_ids = tuple(
        item.radio_id for item in receipt.target.prerequisites.usb_control_arm.radios
    )
    interval_radio_ids = tuple(
        item.radio_id for item in receipt.target.prerequisites.usb_control_arm.capture_intervals
    )
    restoration_radio_ids = tuple(
        item.radio_id for item in receipt.target.prerequisites.usb_control_arm.radio_restoration
    )
    assert safety_radio_ids == canary_radio_ids == expected_radio_ids
    assert usb_radio_ids == interval_radio_ids == restoration_radio_ids
    assert usb_radio_ids != expected_radio_ids
    assert receipt.checks[0].passed
    assert receipt.checks[0].errors == ()


def test_v3_qualifies_only_exact_production_native_prerequisites(
    tmp_path: Path,
) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites_v3(manifest)

    receipt = evaluate_contiguous_rate(
        _target_v3(manifest, prerequisites=prerequisites),
        (_trial(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    assert isinstance(receipt, ContiguousRateQualificationReceiptV3)
    assert receipt.complete and receipt.passed
    assert receipt.schema_version == receipt.target.schema_version == 3
    assert set(receipt.target.prerequisites.model_dump(mode="json")) == {
        "schema_version",
        "radio_safety",
        "native_ip_canaries",
        "writer_benchmark",
    }
    assert receipt.target_digest == contiguous_rate_qualification_target_digest(receipt.target)

    with_usb = prerequisites.model_dump(mode="json")
    with_usb["usb_control_arm"] = _prerequisites(manifest).usb_control_arm.model_dump(mode="json")
    with pytest.raises(ValidationError, match="usb_control_arm"):
        ContiguousRatePrerequisitesV3.model_validate(with_usb)

    reordered = prerequisites.model_dump(mode="json")
    reordered["native_ip_canaries"].reverse()
    with pytest.raises(ValidationError, match="inventories or ordering differ"):
        ContiguousRatePrerequisitesV3.model_validate(reordered)

    failed_writer = prerequisites.writer_benchmark.model_copy(update={"passed": False})
    failed = prerequisites.model_copy(update={"writer_benchmark": failed_writer})
    with pytest.raises(ValidationError, match="passing 72 MB/s writer benchmark"):
        _target_v3(manifest, prerequisites=failed)

    tampered = receipt.model_dump(mode="json")
    tampered["target"]["prerequisites"]["native_ip_canaries"][0]["evidence_sha256"] = (
        _evidence_digest("tampered-v3-canary")
    )
    with pytest.raises(ValidationError, match="target digest does not match"):
        ContiguousRateQualificationReceiptV3.model_validate(tampered)


def test_v4_qualifies_exact_verified_device_axis_v3_evidence(tmp_path: Path) -> None:
    manifest, digest = _capture_v3(tmp_path)
    target = _target_v4(manifest)

    receipt = evaluate_device_axis_contiguous_rate(
        target,
        (_trial_v2(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    assert isinstance(receipt, ContiguousRateQualificationReceiptV4)
    assert receipt.complete and receipt.passed
    assert receipt.schema_version == receipt.target.schema_version == 4
    assert receipt.target_digest == contiguous_rate_qualification_target_digest(receipt.target)
    assert receipt.checks[0].schema_version == 2
    assert receipt.checks[0].manifest_schema_version == 3
    assert tuple(item.radio_id for item in receipt.checks[0].stream_checks) == (
        "radio-a",
        "radio-b",
    )
    assert all(
        item.logical_sample_count == item.observed_sample_count == 12
        and item.zero_fill_sample_count == 0
        and item.continuity_segment_count == 1
        and item.observed_iq_sha256 == item.logical_iq_sha256
        for item in receipt.checks[0].stream_checks
    )
    assert set(receipt.model_dump(mode="json")) == {
        "kind",
        "schema_version",
        "target",
        "target_digest",
        "created_utc_ns",
        "complete",
        "passed",
        "checks",
    }
    assert (
        ContiguousRateQualificationReceiptV4.model_validate_json(receipt.model_dump_json())
        == receipt
    )
    with pytest.raises(TypeError, match="evaluate_device_axis_contiguous_rate"):
        evaluate_contiguous_rate(target, (), created_utc_ns=1)


def test_v4_rejects_gap_fill_and_unverified_device_axis_evidence(tmp_path: Path) -> None:
    manifest, digest = _capture_v3(tmp_path, gap_radio_a=True)
    target = _target_v4(manifest)

    gap_receipt = evaluate_device_axis_contiguous_rate(
        target,
        (_trial_v2(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )
    assert gap_receipt.complete and not gap_receipt.passed
    assert {error for error in gap_receipt.checks[0].errors if error.startswith("radio-a:")} >= {
        "radio-a: stream state is partial, not complete",
        "radio-a: device-axis zero-fill sample count is nonzero",
        "radio-a: logical IQ digest differs from observed IQ digest",
        "radio-a: continuity segment count is not exactly one",
        "radio-a: counter gap count is nonzero",
        "radio-a: counter-proven missing sample count is nonzero",
    }

    unverified_receipt = evaluate_device_axis_contiguous_rate(
        target,
        (_trial_v2(manifest, digest, digest_valid=False),),
        created_utc_ns=1_800_000_000_000_000_000,
    )
    assert "bundle digest verification failed" in unverified_receipt.checks[0].errors


def test_v4_trial_contract_refuses_legacy_v2_manifest(tmp_path: Path) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000)
    with pytest.raises(ValidationError, match="schema_version"):
        ContiguousRateTrialEvidenceV2.model_validate(
            {
                "schema_version": 2,
                "trial_id": "legacy-v2",
                "manifest_sha256": digest,
                "digest_valid": True,
                "manifest": manifest.model_dump(mode="json"),
            }
        )


def test_v4_five_m_characterization_requires_full_verified_device_axis(
    tmp_path: Path,
) -> None:
    manifest, _ = _capture_v3(tmp_path)
    document = _five_m_characterization(manifest).model_dump(mode="json")
    document["manifest_state"] = "degraded"
    for stream in document["streams"]:
        stream["observed_sample_count"] = 284_795_648
        stream["zero_fill_sample_count"] = 15_204_352
        stream["continuity_segment_count"] = 59
        stream["gap_count"] = 58
        stream["missing_sample_count"] = 15_204_352
        stream["gap_map_segment_count"] = 59
        stream["gap_map_boundary_count"] = 58
        stream["validity_segment_count"] = 59
    characterization = ContiguousRateDeviceAxisCharacterizationV1.model_validate(document)
    assert characterization.passed
    assert characterization.manifest_state is CaptureState.DEGRADED

    overflow = characterization.model_dump(mode="json")
    overflow["streams"][0]["overflow_count"] = 1
    with pytest.raises(ValidationError, match="overflow or rejected refills"):
        ContiguousRateDeviceAxisCharacterizationV1.model_validate(overflow)

    unverified = characterization.model_dump(mode="json")
    unverified["physical_zero_verified"] = False
    with pytest.raises(ValidationError, match="pass flag disagrees"):
        ContiguousRateDeviceAxisCharacterizationV1.model_validate(unverified)


def test_v1_wire_shape_and_same_radio_inventory_semantics_are_unchanged(
    tmp_path: Path,
) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites_v1(manifest)
    document = prerequisites.model_dump(mode="json")
    usb = document["usb_control_arm"]

    assert set(document) == {
        "schema_version",
        "radio_safety",
        "native_ip_canaries",
        "usb_control_arm",
        "writer_benchmark",
    }
    assert document["schema_version"] == 1
    assert set(usb) == {
        "schema_version",
        "transport",
        "simultaneous",
        "duration_ns",
        "sample_rate_hz",
        "bandwidth_hz",
        "evidence_sha256",
        "radio_metrics",
        "passed",
    }
    assert usb["schema_version"] == 1
    assert [item["radio_id"] for item in usb["radio_metrics"]] == ["radio-a", "radio-b"]

    receipt = evaluate_contiguous_rate(
        _target_v1(manifest, prerequisites),
        (_trial(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )
    assert type(receipt) is ContiguousRateQualificationReceiptV1
    assert type(receipt.target) is ContiguousRateQualificationTargetV1
    assert receipt.schema_version == receipt.target.schema_version == 1
    serialized_receipt = receipt.model_dump(mode="json")
    assert set(serialized_receipt) == {
        "kind",
        "schema_version",
        "target",
        "target_digest",
        "created_utc_ns",
        "complete",
        "passed",
        "checks",
    }
    assert set(serialized_receipt["target"]) == {
        "schema_version",
        "qualification_id",
        "profile_revision_digest",
        "capture_plan_digest",
        "sample_rate_hz",
        "bandwidth_hz",
        "requested_sample_count",
        "expected_radios",
        "expected_host",
        "expected_producer",
        "pluto_plus_utils_revision",
        "libiio_version",
        "libiio_library_sha256",
        "python_iio_sha256",
        "native_network_interface",
        "native_source_address",
        "prerequisites",
        "policy",
    }
    assert (
        ContiguousRateQualificationReceiptV1.model_validate_json(receipt.model_dump_json())
        == receipt
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContiguousRateUsbControlArmEvidenceV1.model_validate({**usb, "radios": []})
    independent = prerequisites.model_dump(mode="json")
    independent["usb_control_arm"]["radio_metrics"][0]["radio_id"] = "usb-control-a"
    with pytest.raises(ValidationError, match="inventories or ordering differ"):
        ContiguousRatePrerequisitesV1.model_validate(independent)


def test_prerequisites_require_exact_two_radio_inventory_and_exact_control_modes(
    tmp_path: Path,
) -> None:
    manifest, _ = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites(manifest)

    document = prerequisites.model_dump(mode="json")
    document["radio_safety"] = document["radio_safety"][:1]
    with pytest.raises(ValidationError):
        ContiguousRatePrerequisitesV2.model_validate(document)

    canary = prerequisites.native_ip_canaries[0].model_dump(mode="json")
    canary["duration_ns"] = 999_999_999
    with pytest.raises(ValidationError, match="1000000000"):
        ContiguousRateNativeIpCanaryEvidenceV1.model_validate(canary)

    usb = prerequisites.usb_control_arm.model_dump(mode="json")
    usb["simultaneous"] = False
    with pytest.raises(ValidationError, match="True"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(usb)
    usb["simultaneous"] = True
    usb["duration_ns"] = 1_000_000_000
    with pytest.raises(ValidationError, match="60000000000"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(usb)


def test_usb_control_pair_rejects_duplicate_mismatched_or_non_usb_identity(
    tmp_path: Path,
) -> None:
    manifest, _ = _capture(tmp_path, sample_rate_hz=3_000_000)
    usb = _prerequisites(manifest).usb_control_arm.model_dump(mode="json")

    duplicate = {
        **usb,
        "radios": [usb["radios"][0], {**usb["radios"][1], "radio_id": "usb-control-a"}],
        "radio_metrics": [
            usb["radio_metrics"][0],
            {**usb["radio_metrics"][1], "radio_id": "usb-control-a"},
        ],
    }
    with pytest.raises(ValidationError, match="two unique exact radio identities"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(duplicate)

    mismatched = {**usb, "radio_metrics": list(reversed(usb["radio_metrics"]))}
    with pytest.raises(ValidationError, match="exact ordered control radios"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(mismatched)

    reordered_restoration = {
        **usb,
        "radio_restoration": list(reversed(usb["radio_restoration"])),
    }
    with pytest.raises(ValidationError, match="exact ordered control radios"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(reordered_restoration)

    reordered_intervals = {
        **usb,
        "capture_intervals": list(reversed(usb["capture_intervals"])),
    }
    with pytest.raises(ValidationError, match="exact ordered control radios"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(reordered_intervals)

    below_overlap = {
        **usb,
        "capture_intervals": [
            {
                **usb["capture_intervals"][0],
                "started_monotonic_ns": 0,
                "ended_monotonic_ns": 60_000_000_000,
            },
            {
                **usb["capture_intervals"][1],
                "started_monotonic_ns": 600_000_001,
                "ended_monotonic_ns": 60_600_000_001,
            },
        ],
    }
    with pytest.raises(ValidationError, match="overlap"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(below_overlap)

    exact_overlap = {
        **below_overlap,
        "capture_intervals": [
            below_overlap["capture_intervals"][0],
            {
                **below_overlap["capture_intervals"][1],
                "started_monotonic_ns": 600_000_000,
                "ended_monotonic_ns": 60_600_000_000,
            },
        ],
    }
    assert ContiguousRateUsbControlArmEvidenceV2.model_validate(exact_overlap).passed

    with pytest.raises(ValidationError, match="0.99"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(
            {**usb, "minimum_overlap_fraction": 0.98}
        )

    contradictory_restoration = {
        **usb["radio_restoration"][0],
        "rx_settings_restored": False,
    }
    with pytest.raises(ValidationError, match="pass flag disagrees"):
        ContiguousRateUsbRadioRestorationEvidenceV2.model_validate(contradictory_restoration)

    non_usb = {
        **usb,
        "radios": [{**usb["radios"][0], "uri": "ip:192.168.1.20"}, usb["radios"][1]],
    }
    with pytest.raises(ValidationError, match="exact usb: URI"):
        ContiguousRateUsbControlArmEvidenceV2.model_validate(non_usb)


def test_target_still_requires_exact_ordered_production_safety_and_native_pair(
    tmp_path: Path,
) -> None:
    manifest, _ = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites(manifest)

    reordered_safety = prerequisites.model_copy(
        update={"radio_safety": tuple(reversed(prerequisites.radio_safety))}
    )
    with pytest.raises(ValidationError, match="differ"):
        _target(manifest, prerequisites=reordered_safety)

    first_canary = prerequisites.native_ip_canaries[0]
    mismatched_metrics = first_canary.metrics.model_copy(update={"radio_id": "other-radio"})
    mismatched_canary = ContiguousRateNativeIpCanaryEvidenceV1(
        **{
            **first_canary.model_dump(exclude={"metrics"}),
            "metrics": mismatched_metrics,
        }
    )
    mismatched_native = prerequisites.model_copy(
        update={"native_ip_canaries": (mismatched_canary, prerequisites.native_ip_canaries[1])}
    )
    with pytest.raises(ValidationError, match="differ"):
        _target(manifest, prerequisites=mismatched_native)


def test_target_rejects_each_failed_prerequisite(tmp_path: Path) -> None:
    manifest, _ = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites(manifest)

    first_safety = prerequisites.radio_safety[0]
    failed_safety = ContiguousRateRadioSafetyEvidenceV1(
        **{
            **first_safety.model_dump(),
            "post_tx_safe": False,
            "passed": False,
        }
    )
    safety_failure = prerequisites.model_copy(
        update={"radio_safety": (failed_safety, prerequisites.radio_safety[1])}
    )

    first_canary = prerequisites.native_ip_canaries[0]
    failed_canary_metrics = first_canary.metrics.model_copy(
        update={"observed_sample_count": first_canary.metrics.observed_sample_count - 1}
    )
    failed_canary = ContiguousRateNativeIpCanaryEvidenceV1(
        **{
            **first_canary.model_dump(exclude={"metrics"}),
            "metrics": failed_canary_metrics,
            "passed": False,
        }
    )
    canary_failure = prerequisites.model_copy(
        update={"native_ip_canaries": (failed_canary, prerequisites.native_ip_canaries[1])}
    )

    usb_control = prerequisites.usb_control_arm
    failed_usb_metrics = usb_control.radio_metrics[0].model_copy(update={"observed_gap_count": 1})
    failed_usb_control = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"radio_metrics"}),
            "radio_metrics": (failed_usb_metrics, usb_control.radio_metrics[1]),
            "passed": False,
        }
    )
    usb_failure = prerequisites.model_copy(update={"usb_control_arm": failed_usb_control})

    failed_restoration = ContiguousRateUsbRadioRestorationEvidenceV2(
        **{
            **usb_control.radio_restoration[0].model_dump(
                exclude={"rx_settings_restored", "passed"}
            ),
            "rx_settings_restored": False,
            "passed": False,
        }
    )
    failed_restoration_arm = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"radio_restoration", "passed"}),
            "radio_restoration": (
                failed_restoration,
                usb_control.radio_restoration[1],
            ),
            "passed": False,
        }
    )
    restoration_failure = prerequisites.model_copy(
        update={"usb_control_arm": failed_restoration_arm}
    )

    late_interval = usb_control.capture_intervals[1].model_copy(
        update={
            "started_monotonic_ns": usb_control.capture_intervals[0].started_monotonic_ns
            + 1_000_000_000,
            "ended_monotonic_ns": usb_control.capture_intervals[0].ended_monotonic_ns
            + 1_000_000_000,
        }
    )
    failed_overlap_arm = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"capture_intervals", "passed"}),
            "capture_intervals": (usb_control.capture_intervals[0], late_interval),
            "passed": False,
        }
    )
    overlap_failure = prerequisites.model_copy(update={"usb_control_arm": failed_overlap_arm})

    writer_failure = prerequisites.model_copy(
        update={
            "writer_benchmark": ContiguousRateWriterBenchmarkEvidenceV1(
                evidence_sha256=_evidence_digest("slow-incompressible-writer"),
                uncompressed_bytes_written=71_999_999,
                elapsed_ns=1_000_000_000,
                sustained_bytes_per_second=71_999_999,
                passed=False,
            )
        }
    )

    for failed, message in (
        (safety_failure, "passing per-radio safety evidence"),
        (canary_failure, "passing native-IP canaries"),
        (usb_failure, "passing USB control arm"),
        (restoration_failure, "passing USB control arm"),
        (overlap_failure, "passing USB control arm"),
        (writer_failure, "passing 72 MB/s writer benchmark"),
    ):
        with pytest.raises(ValidationError, match=message):
            _target(manifest, prerequisites=failed)


def test_writer_benchmark_metrics_and_threshold_are_exact() -> None:
    with pytest.raises(ValidationError, match="throughput disagrees"):
        ContiguousRateWriterBenchmarkEvidenceV1(
            evidence_sha256=_evidence_digest("inconsistent-writer"),
            uncompressed_bytes_written=144_000_000,
            elapsed_ns=2_000_000_000,
            sustained_bytes_per_second=72_000_001,
            passed=True,
        )

    threshold = ContiguousRateWriterBenchmarkEvidenceV1(
        evidence_sha256=_evidence_digest("threshold-writer"),
        uncompressed_bytes_written=72_000_000,
        elapsed_ns=1_000_000_000,
        sustained_bytes_per_second=72_000_000,
        passed=True,
    )
    assert threshold.passed


def test_receipt_target_digest_binds_every_prerequisite_evidence(tmp_path: Path) -> None:
    manifest, manifest_digest = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites(manifest)

    changed_safety = prerequisites.radio_safety[0].model_copy(
        update={"pre_safety_evidence_sha256": _evidence_digest("changed-safety")}
    )
    changed_canary = prerequisites.native_ip_canaries[0].model_copy(
        update={"evidence_sha256": _evidence_digest("changed-canary")}
    )
    changed_writer_metrics = ContiguousRateWriterBenchmarkEvidenceV1(
        evidence_sha256=prerequisites.writer_benchmark.evidence_sha256,
        uncompressed_bytes_written=216_000_000,
        elapsed_ns=3_000_000_000,
        sustained_bytes_per_second=72_000_000,
        passed=True,
    )
    usb_control = prerequisites.usb_control_arm
    changed_usb_radio = usb_control.radios[0].model_copy(
        update={"firmware_version": "changed-usb-firmware"}
    )
    changed_usb_control = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"radios"}),
            "radios": (changed_usb_radio, usb_control.radios[1]),
        }
    )
    changed_restoration = usb_control.radio_restoration[0].model_copy(
        update={"post_settings_evidence_sha256": _evidence_digest("changed-usb-restoration")}
    )
    changed_restoration_control = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"radio_restoration"}),
            "radio_restoration": (changed_restoration, usb_control.radio_restoration[1]),
        }
    )
    changed_interval = usb_control.capture_intervals[0].model_copy(
        update={
            "started_monotonic_ns": usb_control.capture_intervals[0].started_monotonic_ns + 100,
            "ended_monotonic_ns": usb_control.capture_intervals[0].ended_monotonic_ns + 100,
        }
    )
    changed_interval_control = ContiguousRateUsbControlArmEvidenceV2(
        **{
            **usb_control.model_dump(exclude={"capture_intervals"}),
            "capture_intervals": (changed_interval, usb_control.capture_intervals[1]),
        }
    )
    variants = (
        prerequisites,
        prerequisites.model_copy(
            update={"radio_safety": (changed_safety, prerequisites.radio_safety[1])}
        ),
        prerequisites.model_copy(
            update={"native_ip_canaries": (changed_canary, prerequisites.native_ip_canaries[1])}
        ),
        prerequisites.model_copy(
            update={
                "usb_control_arm": prerequisites.usb_control_arm.model_copy(
                    update={"evidence_sha256": _evidence_digest("changed-usb-control")}
                )
            }
        ),
        prerequisites.model_copy(update={"usb_control_arm": changed_usb_control}),
        prerequisites.model_copy(update={"usb_control_arm": changed_restoration_control}),
        prerequisites.model_copy(update={"usb_control_arm": changed_interval_control}),
        prerequisites.model_copy(
            update={
                "writer_benchmark": prerequisites.writer_benchmark.model_copy(
                    update={"evidence_sha256": _evidence_digest("changed-writer")}
                )
            }
        ),
        prerequisites.model_copy(update={"writer_benchmark": changed_writer_metrics}),
    )

    receipts = tuple(
        evaluate_contiguous_rate(
            _target(manifest, prerequisites=item),
            (_trial(manifest, manifest_digest),),
            created_utc_ns=1_800_000_000_000_000_000,
        )
        for item in variants
    )

    assert all(receipt.passed for receipt in receipts)
    assert len({receipt.target_digest for receipt in receipts}) == len(variants)

    forged = receipts[0].model_dump(mode="json")
    forged["target_digest"] = _evidence_digest("forged-target")
    with pytest.raises(ValidationError, match="target digest does not match"):
        ContiguousRateQualificationReceiptV2.model_validate(forged)

    tampered_identity = receipts[0].model_dump(mode="json")
    tampered_identity["target"]["prerequisites"]["usb_control_arm"]["radios"][0][
        "firmware_version"
    ] = "tampered-after-seal"
    with pytest.raises(ValidationError, match="target digest does not match"):
        ContiguousRateQualificationReceiptV2.model_validate(tampered_identity)

    tampered_restoration = receipts[0].model_dump(mode="json")
    tampered_restoration["target"]["prerequisites"]["usb_control_arm"]["radio_restoration"][0][
        "post_settings_evidence_sha256"
    ] = _evidence_digest("tampered-restoration")
    with pytest.raises(ValidationError, match="target digest does not match"):
        ContiguousRateQualificationReceiptV2.model_validate(tampered_restoration)


def test_real_counter_gap_fails_strict_rate_gate_and_preserves_exact_reasons(
    tmp_path: Path,
) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000, gap_radio_a=True)

    receipt = evaluate_contiguous_rate(
        _target(manifest),
        (_trial(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    assert receipt.complete
    assert not receipt.passed
    errors = receipt.checks[0].errors
    assert "capture state is degraded, not committed" in errors
    assert any("radio-a: stream state is partial" in error for error in errors)
    assert any("radio-a: observed samples do not close" in error for error in errors)
    assert any("radio-a: counter gap count is nonzero" in error for error in errors)
    assert any(
        "radio-a: counter-proven missing sample count is nonzero" in error for error in errors
    )


def test_strict_rate_gate_rejects_unverified_or_headroom_mismatched_evidence(
    tmp_path: Path,
) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000)
    first = manifest.streams[0]
    assert first.applied_settings is not None
    forged_continuity = first.continuity.model_copy(
        update={
            "kernel_buffers": 2,
            "metadata_abi_version": 2,
            "queue_high_water_refills": 25,
        }
    )
    forged_applied = first.applied_settings.model_copy(update={"sample_rate_hz": 2_500_000})
    forged_stream = first.model_copy(
        update={
            "applied_settings": forged_applied,
            "continuity": forged_continuity,
        }
    )
    forged_manifest = manifest.model_copy(update={"streams": (forged_stream, manifest.streams[1])})

    receipt = evaluate_contiguous_rate(
        _target(manifest, required_tags=("CAPTURE_ONLY", "QUALIFICATION")),
        (_trial(forged_manifest, digest, digest_valid=False),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    errors = receipt.checks[0].errors
    assert not receipt.passed
    assert "bundle digest verification failed" in errors
    assert "capture lacks required tags: QUALIFICATION" in errors
    assert any("applied sample rate differs" in error for error in errors)
    assert any("kernel-buffer readback differs" in error for error in errors)
    assert any("metadata ABI differs" in error for error in errors)
    assert any("queue high-water exceeds" in error for error in errors)


def test_strict_rate_gate_cannot_pass_an_incomplete_campaign(tmp_path: Path) -> None:
    manifest, digest = _capture(tmp_path, sample_rate_hz=3_000_000)

    receipt = evaluate_contiguous_rate(
        _target(manifest, required_trial_count=2),
        (_trial(manifest, digest),),
        created_utc_ns=1_800_000_000_000_000_000,
    )

    assert not receipt.complete
    assert not receipt.passed
    assert receipt.checks[0].passed
