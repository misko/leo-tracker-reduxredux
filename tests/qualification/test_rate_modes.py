from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.acquisition import AcquisitionConfig, AcquisitionCoordinator
from leo.contracts.digests import canonical_digest
from leo.contracts.profile import CaptureProfileRevisionV2, CaptureProfileV2
from leo.contracts.radio import ReceiverGainV1
from leo.contracts.recording import HostIdentityV1, ProducerV1, RecordingManifestV2
from leo.contracts.states import ContinuityPolicy, GainMode, SourceType
from leo.domain.profiles import compile_capture_plan
from leo.qualification.rate_modes import (
    ContiguousRateNativeIpCanaryEvidenceV1,
    ContiguousRatePrerequisitesV1,
    ContiguousRateQualificationPolicyV1,
    ContiguousRateQualificationReceiptV1,
    ContiguousRateQualificationTargetV1,
    ContiguousRateRadioMetricsV1,
    ContiguousRateRadioSafetyEvidenceV1,
    ContiguousRateTrialEvidenceV1,
    ContiguousRateUsbControlArmEvidenceV1,
    ContiguousRateWriterBenchmarkEvidenceV1,
    contiguous_rate_qualification_target_digest,
    evaluate_contiguous_rate,
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


def _target(
    manifest: RecordingManifestV2,
    *,
    required_trial_count: int = 1,
    required_tags: tuple[str, ...] = ("CAPTURE_ONLY",),
    prerequisites: ContiguousRatePrerequisitesV1 | None = None,
) -> ContiguousRateQualificationTargetV1:
    profile = manifest.capture_plan.profile_revision.profile
    return ContiguousRateQualificationTargetV1(
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


def _prerequisites(manifest: RecordingManifestV2) -> ContiguousRatePrerequisitesV1:
    profile = manifest.capture_plan.profile_revision.profile
    radio_ids = (manifest.streams[0].radio.radio_id, manifest.streams[1].radio.radio_id)
    canary_metrics = (
        _radio_metrics(radio_ids[0], profile.sample_rate_hz),
        _radio_metrics(radio_ids[1], profile.sample_rate_hz),
    )
    usb_metrics = (
        _radio_metrics(radio_ids[0], profile.sample_rate_hz * 60),
        _radio_metrics(radio_ids[1], profile.sample_rate_hz * 60),
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

    return ContiguousRatePrerequisitesV1(
        radio_safety=(safety(radio_ids[0]), safety(radio_ids[1])),
        native_ip_canaries=(canary(canary_metrics[0]), canary(canary_metrics[1])),
        usb_control_arm=ContiguousRateUsbControlArmEvidenceV1(
            duration_ns=60_000_000_000,
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            evidence_sha256=_evidence_digest("simultaneous-usb-control"),
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
    assert receipt.target_digest == contiguous_rate_qualification_target_digest(receipt.target)
    assert all(
        canary.metrics.requested_sample_count == sample_rate_hz
        for canary in receipt.target.prerequisites.native_ip_canaries
    )
    assert all(
        metrics.requested_sample_count == sample_rate_hz * 60
        for metrics in receipt.target.prerequisites.usb_control_arm.radio_metrics
    )
    assert receipt.checks[0].passed
    assert receipt.checks[0].errors == ()


def test_prerequisites_require_exact_two_radio_inventory_and_exact_control_modes(
    tmp_path: Path,
) -> None:
    manifest, _ = _capture(tmp_path, sample_rate_hz=3_000_000)
    prerequisites = _prerequisites(manifest)

    document = prerequisites.model_dump(mode="json")
    document["radio_safety"] = document["radio_safety"][:1]
    with pytest.raises(ValidationError):
        ContiguousRatePrerequisitesV1.model_validate(document)

    canary = prerequisites.native_ip_canaries[0].model_dump(mode="json")
    canary["duration_ns"] = 999_999_999
    with pytest.raises(ValidationError, match="1000000000"):
        ContiguousRateNativeIpCanaryEvidenceV1.model_validate(canary)

    usb = prerequisites.usb_control_arm.model_dump(mode="json")
    usb["simultaneous"] = False
    with pytest.raises(ValidationError, match="True"):
        ContiguousRateUsbControlArmEvidenceV1.model_validate(usb)
    usb["simultaneous"] = True
    usb["duration_ns"] = 1_000_000_000
    with pytest.raises(ValidationError, match="60000000000"):
        ContiguousRateUsbControlArmEvidenceV1.model_validate(usb)


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
    failed_usb_control = ContiguousRateUsbControlArmEvidenceV1(
        **{
            **usb_control.model_dump(exclude={"radio_metrics"}),
            "radio_metrics": (failed_usb_metrics, usb_control.radio_metrics[1]),
            "passed": False,
        }
    )
    usb_failure = prerequisites.model_copy(update={"usb_control_arm": failed_usb_control})

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
        ContiguousRateQualificationReceiptV1.model_validate(forged)


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
